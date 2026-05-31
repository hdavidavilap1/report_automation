"""ICA (Índice de Calidad del Aire) — Section 7 of the air quality report.

Methodology: EPA linear interpolation with Colombian Res. 2254/2017 limits.
Averaging periods:
  PM10, PM2.5 → 24-hour daily average
  SO2, NO2    → 1-hour values; daily representative = max hourly ICA
  CO, O3      → 8-hour rolling mean; daily representative = max 8h ICA
"""

import base64
import calendar as _cal
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from skills.resultados_analisis.resultados import load_pollutants, _rolling_8h

# ─────────────────────────────────────────────────────────────────────────────
# ICA categories (Res. 2254/2017 colour scale)
# ─────────────────────────────────────────────────────────────────────────────

ICA_CATEGORIES = [
    (0,   50,  "Buena",                     "#00B050", "#000000"),
    (51,  100, "Aceptable",                 "#FFFF00", "#000000"),
    (101, 150, "Dañina a grupos sensibles", "#FF7F00", "#000000"),
    (151, 200, "Dañina a la salud",         "#FF0000", "#FFFFFF"),
    (201, 300, "Muy dañina a la salud",     "#8F3F97", "#FFFFFF"),
    (301, 500, "Peligrosa",                 "#7E0023", "#FFFFFF"),
]


def _ica_color(value: float) -> tuple:
    if pd.isna(value):
        return "#F0F0F0", "#000000"
    for lo, hi, _, bg, fg in ICA_CATEGORIES:
        if lo <= value <= hi:
            return bg, fg
    return "#7E0023", "#FFFFFF"


def _ica_category(value: float) -> str:
    if pd.isna(value):
        return "-"
    for lo, hi, label, _, _ in ICA_CATEGORIES:
        if lo <= value <= hi:
            return label
    return "Peligrosa"


# ─────────────────────────────────────────────────────────────────────────────
# Breakpoints — exact values from Figura 6, Res. 2254/2017
# Each entry: (c_lo, c_hi, i_lo, i_hi)
# ─────────────────────────────────────────────────────────────────────────────

ICA_BREAKPOINTS = {
    "pm10": [   # 24h average, µg/m³
        (0,   54,   0,  50),
        (55,  154,  51, 100),
        (155, 254, 101, 150),
        (255, 354, 151, 200),
        (355, 424, 201, 300),
        (425, 604, 301, 500),
    ],
    "pm25": [   # 24h average, µg/m³
        (0,   12,   0,  50),
        (13,  37,  51, 100),
        (38,  55, 101, 150),
        (56,  150, 151, 200),
        (151, 250, 201, 300),
        (251, 500, 301, 500),
    ],
    "so2": [    # 1h, µg/m³ (ppb × 2.620)
        (0,    93,   0,  50),
        (94,   197,  51, 100),
        (198,  486, 101, 150),
        (487,  797, 151, 200),
        (798, 1583, 201, 300),
        (1584, 2629, 301, 500),
    ],
    "no2": [    # 1h, µg/m³ (ppb × 1.880)
        (0,    100,   0,  50),
        (101,  189,  51, 100),
        (190,  677, 101, 150),
        (678, 1221, 151, 200),
        (1222, 2349, 201, 300),
        (2350, 3853, 301, 500),
    ],
    "co": [     # 8h rolling mean, µg/m³ (ppm × 1145)
        (0,     5094,   0,  50),
        (5095, 10819,  51, 100),
        (10820, 14254, 101, 150),
        (14255, 17688, 151, 200),
        (17689, 34862, 201, 300),
        (34863, 57703, 301, 500),
    ],
    "o3": [     # 8h rolling mean, µg/m³ (ppb × 1.960)
        (0,   106,   0,  50),
        (107, 138,  51, 100),
        (139, 167, 101, 150),
        (168, 207, 151, 200),
        (208, 393, 201, 300),
        (394, 980, 301, 500),
    ],
}

_LABELS = {
    "pm10": "PM₁₀", "pm25": "PM₂.₅", "so2": "SO₂",
    "no2": "NO₂",   "co":   "CO",     "o3":  "O₃",
}

_AVG_PERIOD = {
    "pm10": "promedio 24 h",  "pm25": "promedio 24 h",
    "so2":  "valor horario",  "no2":  "valor horario",
    "co":   "media móvil 8 h","o3":   "media móvil 8 h",
}

_SUBSECTION = {
    "pm10": "7.1", "pm25": "7.2", "so2": "7.3",
    "no2":  "7.4", "co":   "7.5", "o3":  "7.6",
}

# ─────────────────────────────────────────────────────────────────────────────
# ICA interpolation
# ─────────────────────────────────────────────────────────────────────────────

def _interpolate_ica(concentration: float, pollutant: str) -> float:
    if pd.isna(concentration) or concentration < 0:
        return float("nan")
    bps = ICA_BREAKPOINTS[pollutant]
    for c_lo, c_hi, i_lo, i_hi in bps:
        if c_lo <= concentration <= c_hi:
            if c_hi == c_lo:
                return float(i_lo)
            return ((i_hi - i_lo) / (c_hi - c_lo)) * (concentration - c_lo) + i_lo
    return 500.0


def _find_breakpoint_row(concentration: float, pollutant: str):
    """Return (c_lo, c_hi, i_lo, i_hi) for matching bracket, or None."""
    if pd.isna(concentration):
        return None
    for row in ICA_BREAKPOINTS[pollutant]:
        if row[0] <= concentration <= row[1]:
            return row
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Daily representative concentrations per pollutant
# ─────────────────────────────────────────────────────────────────────────────

def _daily_mean(s: pd.Series) -> pd.Series:
    return s.groupby(s.index.date).mean()

def _daily_max(s: pd.Series) -> pd.Series:
    return s.groupby(s.index.date).max()

def _daily_max_8h(s: pd.Series) -> pd.Series:
    roll = _rolling_8h(s)
    return roll.groupby(roll.index.date).max()

_AGG = {
    "pm10": _daily_mean,
    "pm25": _daily_mean,
    "so2":  _daily_max,
    "no2":  _daily_max,
    "co":   _daily_max_8h,
    "o3":   _daily_max_8h,
}


def compute_ica(df: pd.DataFrame) -> pd.DataFrame:
    """Daily ICA per pollutant and composite, indexed by (date, station)."""
    pollutants = [p for p in ICA_BREAKPOINTS if p in df.columns]
    stations = sorted(df["station"].unique())
    records = []

    for station in stations:
        concs = {}
        for p in pollutants:
            s = df[df["station"] == station][p]
            concs[p] = _AGG[p](s)

        all_dates = sorted(set().union(*[set(s.index) for s in concs.values()]))
        for date in all_dates:
            row = {"date": date, "station": station}
            ica_vals = []
            for p in pollutants:
                c = concs[p].get(date, float("nan"))
                ica = _interpolate_ica(c, p)
                row[f"ica_{p}"] = ica
                row[f"conc_{p}"] = c
                if not math.isnan(ica):
                    ica_vals.append(ica)
            row["ica_composite"] = max(ica_vals) if ica_vals else float("nan")
            records.append(row)

    result = pd.DataFrame(records)
    result["date"] = pd.to_datetime(result["date"])
    return result.set_index(["date", "station"])


# ─────────────────────────────────────────────────────────────────────────────
# HTML style constants
# ─────────────────────────────────────────────────────────────────────────────

_TH  = "padding:5px 7px;border:1px solid #aaa;text-align:center;vertical-align:middle"
_TD  = "padding:4px 6px;border:1px solid #ccc;text-align:center;vertical-align:middle"
_TD_L = "padding:4px 8px;border:1px solid #ccc;text-align:left"

_MONTHS_ES = {
    1:"enero", 2:"febrero", 3:"marzo",    4:"abril",
    5:"mayo",  6:"junio",   7:"julio",    8:"agosto",
    9:"septiembre", 10:"octubre", 11:"noviembre", 12:"diciembre",
}


def _fmt_ica(v) -> str:
    return f"{v:.0f}" if not (isinstance(v, float) and math.isnan(v)) else "-"

def _fmt_c(v, dec: int = 1) -> str:
    return f"{v:.{dec}f}" if not (isinstance(v, float) and math.isnan(v)) else "-"

def _es_date(d) -> str:
    if not hasattr(d, "day"):
        d = pd.Timestamp(d)
    return f"{d.day} de {_MONTHS_ES[d.month]} de {d.year}"


# ─────────────────────────────────────────────────────────────────────────────
# Legend table
# ─────────────────────────────────────────────────────────────────────────────

def ica_category_legend_table() -> str:
    EFFECTS = [
        "La calidad del aire es satisfactoria y la contaminación del aire presenta poco o ningún riesgo.",
        "La calidad del aire es aceptable. Sin embargo, puede haber un riesgo moderado para un número muy pequeño de personas.",
        "Los miembros de grupos sensibles pueden experimentar efectos en la salud.",
        "Todos pueden comenzar a experimentar efectos en la salud.",
        "Advertencias de emergencia sanitaria. Toda la población es más probable que resulte afectada.",
        "Alerta de emergencia de salud: todos son más propensos a ser afectados.",
    ]
    rows = [
        '<table style="border-collapse:collapse;font-family:Arial;font-size:8.5pt;width:100%">',
        f'<thead><tr style="background:#1F4E79;color:white">',
        f'<th style="{_TH}">Rango ICA</th>',
        f'<th style="{_TH}">Categoría</th>',
        f'<th style="{_TH}">Color</th>',
        f'<th style="{_TH}">Descripción</th>',
        "</tr></thead><tbody>",
    ]
    for (lo, hi, label, bg, fg), effect in zip(ICA_CATEGORIES, EFFECTS):
        rows.append(
            f'<tr>'
            f'<td style="{_TD}">{lo} – {hi}</td>'
            f'<td style="{_TD}">{label}</td>'
            f'<td style="{_TD};background:{bg};color:{fg};font-weight:bold">{label}</td>'
            f'<td style="{_TD_L};font-size:8pt">{effect}</td>'
            f'</tr>'
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# PM10 / PM2.5 — daily detail table (Fecha|Cp|PCalto|PCbajo|Ialto|Ibajo|ICA)
# ─────────────────────────────────────────────────────────────────────────────

def ica_pm_detail_table(df: pd.DataFrame, station: str, pollutant: str, table_num: int) -> str:
    s = df[df["station"] == station][pollutant]
    daily_conc = s.groupby(s.index.date).mean()
    dates = sorted(daily_conc.index)
    label = _LABELS[pollutant]

    rows = [
        '<table style="border-collapse:collapse;font-family:Arial;font-size:8.5pt;width:100%">',
        '<thead>',
        f'<tr style="background:#1F4E79;color:white">',
        f'<td colspan="7" style="{_TH};font-weight:bold">'
        f'Tabla {table_num}. ICA {label} (µg/m³, promedio 24 h) — {station}</td></tr>',
        f'<tr style="background:#2E75B6;color:white">',
        f'<th style="{_TH}">Fecha</th>',
        f'<th style="{_TH}">Cp<br>(µg/m³)</th>',
        f'<th style="{_TH}">PCalto<br>(µg/m³)</th>',
        f'<th style="{_TH}">PCbajo<br>(µg/m³)</th>',
        f'<th style="{_TH}">Ialto</th>',
        f'<th style="{_TH}">Ibajo</th>',
        f'<th style="{_TH}">ICA</th>',
        '</tr></thead><tbody>',
    ]

    for date in dates:
        cp = daily_conc.get(date, float("nan"))
        ica_val = _interpolate_ica(cp, pollutant)
        bp = _find_breakpoint_row(cp, pollutant)
        if bp:
            c_lo, c_hi, i_lo, i_hi = bp
        else:
            c_lo = c_hi = i_lo = i_hi = float("nan")
        bg, fg = _ica_color(ica_val)
        rows.append(
            f'<tr style="background:{bg};color:{fg}">'
            f'<td style="{_TD}">{pd.Timestamp(date).strftime("%Y-%m-%d")}</td>'
            f'<td style="{_TD}">{_fmt_c(cp)}</td>'
            f'<td style="{_TD}">{_fmt_c(c_hi, 0)}</td>'
            f'<td style="{_TD}">{_fmt_c(c_lo, 0)}</td>'
            f'<td style="{_TD}">{_fmt_c(i_hi, 0)}</td>'
            f'<td style="{_TD}">{_fmt_c(i_lo, 0)}</td>'
            f'<td style="{_TD};font-weight:bold">{_fmt_ica(ica_val)}</td>'
            f'</tr>'
        )

    rows.append("</tbody></table>")
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# SO2 / NO2 — hourly ICA matrix (24 rows × n_days columns)
# ─────────────────────────────────────────────────────────────────────────────

def ica_hourly_matrix_table(df: pd.DataFrame, station: str, pollutant: str, table_num: int) -> str:
    s = df[df["station"] == station][pollutant]
    conc_dict = {ts: v for ts, v in s.items() if pd.notna(v)}
    dates = sorted(set(s.index.date))
    n_days = len(dates)
    label = _LABELS[pollutant]

    rows = [
        '<table style="border-collapse:collapse;font-family:Arial;font-size:7.5pt;width:100%">',
        '<thead>',
        f'<tr style="background:#1F4E79;color:white">',
        f'<td colspan="{n_days + 1}" style="{_TH};font-weight:bold">'
        f'Tabla {table_num}. ICA {label} (µg/m³, valor horario) — {station}</td></tr>',
        f'<tr style="background:#2E75B6;color:white">',
        f'<th style="{_TH}">Hora</th>',
    ]
    for d in dates:
        rows.append(f'<th style="{_TH}">{pd.Timestamp(d).strftime("%d/%m")}</th>')
    rows.append('</tr></thead><tbody>')

    for hour in range(24):
        rows.append('<tr>')
        rows.append(f'<td style="{_TD};font-weight:bold;background:#EEF2F7">{hour:02d}:00</td>')
        for d in dates:
            ts = pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=hour)
            cp = conc_dict.get(ts, float("nan"))
            ica_val = _interpolate_ica(cp, pollutant)
            bg, fg = _ica_color(ica_val)
            rows.append(f'<td style="{_TD};background:{bg};color:{fg}">{_fmt_ica(ica_val)}</td>')
        rows.append('</tr>')

    rows.append('</tbody></table>')
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# CO / O3 — 8h rolling mean ICA matrix (24 rows × n_days columns)
# ─────────────────────────────────────────────────────────────────────────────

def ica_8h_matrix_table(df: pd.DataFrame, station: str, pollutant: str, table_num: int) -> str:
    s = df[df["station"] == station][pollutant]
    roll = _rolling_8h(s)
    roll_dict = {ts: v for ts, v in roll.items() if pd.notna(v)}
    dates = sorted(set(s.index.date))
    n_days = len(dates)
    label = _LABELS[pollutant]

    rows = [
        '<table style="border-collapse:collapse;font-family:Arial;font-size:7.5pt;width:100%">',
        '<thead>',
        f'<tr style="background:#1F4E79;color:white">',
        f'<td colspan="{n_days + 1}" style="{_TH};font-weight:bold">'
        f'Tabla {table_num}. ICA {label} (µg/m³, media móvil 8 h) — {station}</td></tr>',
        f'<tr style="background:#2E75B6;color:white">',
        f'<th style="{_TH}">Hora</th>',
    ]
    for d in dates:
        rows.append(f'<th style="{_TH}">{pd.Timestamp(d).strftime("%d/%m")}</th>')
    rows.append('</tr></thead><tbody>')

    for hour in range(24):
        rows.append('<tr>')
        rows.append(f'<td style="{_TD};font-weight:bold;background:#EEF2F7">{hour:02d}:00</td>')
        for d in dates:
            ts = pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=hour)
            cp = roll_dict.get(ts, float("nan"))
            ica_val = _interpolate_ica(cp, pollutant)
            bg, fg = _ica_color(ica_val)
            rows.append(f'<td style="{_TD};background:{bg};color:{fg}">{_fmt_ica(ica_val)}</td>')
        rows.append('</tr>')

    rows.append('</tbody></table>')
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Composite summary table (kept for backward-compat and test coverage)
# ─────────────────────────────────────────────────────────────────────────────

def ica_daily_table(ica_df: pd.DataFrame, station: str, table_num: int) -> str:
    """Summary daily ICA table with all pollutants + composite for one station."""
    pollutants = [p for p in ICA_BREAKPOINTS if f"ica_{p}" in ica_df.columns]
    sdf = ica_df.xs(station, level="station")
    dates = sorted(sdf.index)
    n_cols = len(pollutants) + 3  # Fecha + pollutants + Compuesto + Categoría

    rows = [
        '<table style="border-collapse:collapse;font-family:Arial;font-size:8.5pt;width:100%">',
        '<thead>',
        f'<tr style="background:#1F4E79;color:white">',
        f'<td colspan="{n_cols}" style="{_TH};font-weight:bold">'
        f'Tabla {table_num}. ICA Compuesto — {station}</td></tr>',
        f'<tr style="background:#2E75B6;color:white">',
        f'<th style="{_TH}">Fecha</th>',
    ]
    for p in pollutants:
        rows.append(f'<th style="{_TH}">{_LABELS[p]}</th>')
    rows.append(f'<th style="{_TH}">ICA<br>Compuesto</th>')
    rows.append(f'<th style="{_TH}">Categoría</th>')
    rows.append("</tr></thead><tbody>")

    for date in dates:
        row = sdf.loc[date]
        comp = row["ica_composite"]
        bg, fg = _ica_color(comp)
        rows.append("<tr>")
        rows.append(f'<td style="{_TD}">{pd.Timestamp(date).strftime("%Y-%m-%d")}</td>')
        for p in pollutants:
            v = row.get(f"ica_{p}", float("nan"))
            pbg, pfg = _ica_color(v)
            rows.append(f'<td style="{_TD};background:{pbg};color:{pfg}">{_fmt_ica(v)}</td>')
        rows.append(f'<td style="{_TD};background:{bg};color:{fg};font-weight:bold">{_fmt_ica(comp)}</td>')
        rows.append(f'<td style="{_TD};background:{bg};color:{fg}">{_ica_category(comp)}</td>')
        rows.append("</tr>")

    n_days = len(dates)
    composite_vals = [sdf.loc[d, "ica_composite"] for d in dates]
    rows.append(
        f'<tr style="background:#F0F0F0;font-weight:bold">'
        f'<td style="{_TD_L}" colspan="{n_cols}">Total días evaluados: {n_days}</td></tr>'
    )
    for lo, hi, label, bg, fg in ICA_CATEGORIES:
        count = sum(1 for v in composite_vals if not math.isnan(v) and lo <= v <= hi)
        if count:
            pct = count / n_days * 100
            rows.append(
                f'<tr><td style="{_TD_L};background:{bg};color:{fg}" colspan="{n_cols}">'
                f'{label}: {count} día(s) ({pct:.1f}%)</td></tr>'
            )

    rows.append("</tbody></table>")
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────────────

def figure_calendar_heatmap(
    ica_df: pd.DataFrame,
    station: str,
    output_path: str,
    pollutant: str = None,
) -> str:
    """Real month-calendar heatmap of daily ICA.

    If pollutant is given, shows that pollutant's ICA; otherwise shows composite.
    """
    sdf = ica_df.xs(station, level="station")
    dates = sorted(sdf.index)
    col = f"ica_{pollutant}" if pollutant else "ica_composite"
    date_val_map = {pd.Timestamp(d): sdf.loc[d, col] for d in dates}

    ts_dates = [pd.Timestamp(d) for d in dates]
    months = sorted({(d.year, d.month) for d in ts_dates})
    n_months = len(months)
    ncols = min(n_months, 2)
    nrows = math.ceil(n_months / ncols)

    fig_w = 5.5 * ncols
    fig_h = nrows * 4.2 + 1.2

    fig = plt.figure(figsize=(fig_w, fig_h))

    # Sunday-first weekday headers: D L M M J V S
    HEADERS = ["D", "L", "M", "M", "J", "V", "S"]

    for idx, (year, month) in enumerate(months):
        ax = fig.add_subplot(nrows, ncols, idx + 1)

        first_wd = _cal.weekday(year, month, 1)    # Mon=0, Sun=6
        first_wd_sun = (first_wd + 1) % 7          # convert to Sun=0
        n_days_month = _cal.monthrange(year, month)[1]
        n_weeks = math.ceil((first_wd_sun + n_days_month) / 7)

        ax.set_xlim(-0.5, 6.5)
        ax.set_ylim(-(n_weeks + 0.3), 1.3)
        ax.axis("off")

        month_name = _MONTHS_ES[month].capitalize()
        ax.text(3, 1.0, f"{month_name} {year}",
                ha="center", va="center", fontsize=10, fontweight="bold", color="#1F4E79")

        for wd, lbl in enumerate(HEADERS):
            ax.text(wd, 0.3, lbl, ha="center", va="center",
                    fontsize=8, color="#555", fontweight="bold")

        for day in range(1, n_days_month + 1):
            ts = pd.Timestamp(year=year, month=month, day=day)
            cell = first_wd_sun + day - 1
            week = cell // 7
            wd   = cell % 7
            val  = date_val_map.get(ts, float("nan"))
            bg, fg = _ica_color(val)

            rect = mpatches.FancyBboxPatch(
                (wd - 0.45, -week - 0.45), 0.9, 0.9,
                boxstyle="round,pad=0.05", linewidth=0.5,
                edgecolor="#aaa", facecolor=bg,
            )
            ax.add_patch(rect)
            ax.text(wd, -week + 0.2, str(day),
                    ha="center", va="center", fontsize=6.5, color=fg)
            if not (isinstance(val, float) and math.isnan(val)):
                ax.text(wd, -week - 0.15, f"{val:.0f}",
                        ha="center", va="center", fontsize=7.5, color=fg, fontweight="bold")

    # Hide unused axes
    for idx in range(n_months, nrows * ncols):
        row_i, col_i = divmod(idx, ncols)
        fig.add_subplot(nrows, ncols, idx + 1).axis("off")

    handles = [
        mpatches.Patch(facecolor=bg, edgecolor="#888", label=f"{lo}–{hi}: {label}")
        for lo, hi, label, bg, _ in ICA_CATEGORIES
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=7.5,
               bbox_to_anchor=(0.5, 0), framealpha=0.9)

    poll_label = _LABELS[pollutant] if pollutant else "Compuesto"
    fig.suptitle(f"ICA {poll_label} diario — {station}",
                 fontsize=10, fontweight="bold", y=1.0)
    fig.tight_layout(rect=[0, 0.12, 1, 1])
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def figure_ica_timeseries(ica_df: pd.DataFrame, output_path: str) -> str:
    """Composite ICA time series for all stations with category band background."""
    stations = sorted(ica_df.index.get_level_values("station").unique())
    COLORS = ["#1F4E79", "#2E75B6", "#70AD47"]

    fig, ax = plt.subplots(figsize=(13, 5))

    for i, sta in enumerate(stations):
        sdf = ica_df.xs(sta, level="station")
        dates = [pd.Timestamp(d) for d in sorted(sdf.index)]
        vals  = [sdf.loc[d, "ica_composite"] for d in sdf.index]
        ax.plot(dates, vals, color=COLORS[i % len(COLORS)], linewidth=1.8,
                marker="o", markersize=5, label=sta, zorder=4)

    x_left = ax.get_xlim()[0]
    for lo, hi, label, bg, _ in ICA_CATEGORIES:
        ax.axhspan(lo, hi, alpha=0.12, color=bg, linewidth=0, zorder=1)
        ax.axhline(lo, color="#aaa", linewidth=0.5, linestyle="--", zorder=2)
        ax.text(x_left, (lo + hi) / 2, f"  {label}",
                va="center", fontsize=6.5, color="#777", style="italic",
                transform=ax.get_yaxis_transform(), clip_on=True)

    y_max = ica_df["ica_composite"].dropna().max()
    ax.set_ylim(0, min(500, y_max * 1.3 + 20))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("ICA", fontsize=9)
    ax.set_title("Índice de Calidad del Aire (ICA) Compuesto — todas las estaciones",
                 fontsize=10, fontweight="bold")
    ax.legend(fontsize=8.5, loc="upper right")
    ax.grid(axis="y", alpha=0.25, linewidth=0.5)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def figure_ica_pollutant_bars(ica_df: pd.DataFrame, station: str, output_path: str) -> str:
    """Grouped bar chart of daily ICA per pollutant for one station."""
    pollutants = [p for p in ICA_BREAKPOINTS if f"ica_{p}" in ica_df.columns]
    sdf = ica_df.xs(station, level="station")
    dates = sorted(sdf.index)
    x = np.arange(len(dates))
    n_poll = len(pollutants)
    w = 0.8 / n_poll
    offsets = np.linspace(-(n_poll - 1) / 2, (n_poll - 1) / 2, n_poll) * w
    POLL_COLORS = ["#1F4E79", "#2E75B6", "#70AD47", "#FFC000", "#FF4444", "#8F3F97"]

    fig, ax = plt.subplots(figsize=(12, 5))
    for i, (p, offset) in enumerate(zip(pollutants, offsets)):
        vals = [sdf.loc[d, f"ica_{p}"] for d in dates]
        ax.bar(x + offset, vals, width=w * 0.9,
               color=POLL_COLORS[i % len(POLL_COLORS)],
               alpha=0.85, label=_LABELS[p], edgecolor="white", linewidth=0.4)

    for lo, _, label, bg, _ in ICA_CATEGORIES[1:]:
        ax.axhline(lo, color="#888", linewidth=0.7, linestyle="--", alpha=0.6)

    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"Día {i+1}\n{pd.Timestamp(d).strftime('%d/%m')}" for i, d in enumerate(dates)],
        rotation=30, ha="right", fontsize=7.5,
    )
    ax.set_ylabel("ICA", fontsize=9)
    ax.set_title(f"ICA por contaminante — {station}", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8, loc="upper right", ncol=3)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)
    ax.set_ylim(0, max(150, ica_df["ica_composite"].max() * 1.2))
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Image helper
# ─────────────────────────────────────────────────────────────────────────────

def _img_b64(path: str) -> str:
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


# ─────────────────────────────────────────────────────────────────────────────
# Per-pollutant HTML section builders
# ─────────────────────────────────────────────────────────────────────────────

_INTRO_PM = (
    "El ICA para {label} se calculó a partir del promedio aritmético de 24 horas de las "
    "concentraciones horarias medidas en cada estación de monitoreo, aplicando la fórmula "
    "de interpolación lineal de la EPA con los puntos de quiebre de la Resolución 2254 de "
    "2017 del Ministerio de Ambiente y Desarrollo Sostenible (MADS)."
)

_INTRO_1H = (
    "El ICA para {label} se calculó a partir de los valores horarios de concentración medidos "
    "en cada estación de monitoreo, aplicando la fórmula de interpolación lineal de la EPA "
    "con los puntos de quiebre de la Resolución 2254 de 2017 del MADS. "
    "Se presenta la matriz de valores ICA horarios (24 filas × n días columnas) para cada estación."
)

_INTRO_8H = (
    "El ICA para {label} se calculó a partir de la media móvil de 8 horas de las concentraciones "
    "horarias medidas en cada estación de monitoreo, aplicando la fórmula de interpolación lineal "
    "de la EPA con los puntos de quiebre de la Resolución 2254 de 2017 del MADS. "
    "Se presenta la matriz de valores ICA (24 filas × n días columnas) para cada estación."
)

_INTRO_TEMPLATE = {
    "pm10": _INTRO_PM, "pm25": _INTRO_PM,
    "so2":  _INTRO_1H, "no2":  _INTRO_1H,
    "co":   _INTRO_8H, "o3":   _INTRO_8H,
}


def _pollutant_section_html(
    df: pd.DataFrame,
    ica_df: pd.DataFrame,
    pollutant: str,
    stations: list,
    cal_paths: dict,
    table_start: int,
) -> tuple:
    """Build HTML for one pollutant subsection. Returns (html, next_table_num)."""
    label = _LABELS[pollutant]
    subsec = _SUBSECTION[pollutant]
    intro = _INTRO_TEMPLATE[pollutant].format(label=label)
    table_num = table_start
    parts = [
        f'<h2>{subsec} {label}</h2>',
        f'<p>{intro}</p>',
    ]

    for sta in stations:
        if pollutant in ("pm10", "pm25"):
            tbl = ica_pm_detail_table(df, sta, pollutant, table_num)
        elif pollutant in ("so2", "no2"):
            tbl = ica_hourly_matrix_table(df, sta, pollutant, table_num)
        else:
            tbl = ica_8h_matrix_table(df, sta, pollutant, table_num)

        cal_b64 = _img_b64(cal_paths[pollutant][sta])
        fig_num = table_num  # use same counter for figure numbering
        parts.append(f'<div class="table-wrap">{tbl}</div>')
        parts.append(
            f'<figure>'
            f'<img src="{cal_b64}" alt="Mapa calendario ICA {label} {sta}">'
            f'<p class="caption-fig">Gráfica {fig_num}. Mapa de calor ICA {label} — {sta}.</p>'
            f'</figure>'
        )
        table_num += 1

    return "\n".join(parts), table_num


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(file_path: str, output_dir: str) -> dict:
    """Generate Section 7 — ICA as a self-contained HTML report."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = load_pollutants(file_path)
    ica_df = compute_ica(df)
    stations = sorted(ica_df.index.get_level_values("station").unique())
    pollutants = [p for p in ICA_BREAKPOINTS if p in df.columns]

    period_start = _es_date(ica_df.index.get_level_values("date").min())
    period_end   = _es_date(ica_df.index.get_level_values("date").max())
    period = f"{period_start} al {period_end}"

    # ── Generate figures ─────────────────────────────────────────────────────
    fig_ts = str(out / "fig_ica_timeseries.png")
    figure_ica_timeseries(ica_df, fig_ts)

    # Calendar heatmaps: one per pollutant per station + composite per station
    cal_paths: dict = {p: {} for p in pollutants}
    for poll in pollutants:
        poll_dir = out / f"pol_{poll}"
        poll_dir.mkdir(exist_ok=True)
        for sta in stations:
            safe = sta.replace(" ", "_")
            path = str(poll_dir / f"cal_{safe}.png")
            figure_calendar_heatmap(ica_df, sta, path, pollutant=poll)
            cal_paths[poll][sta] = path

    # Composite calendar + bar charts per station (for return dict & summary section)
    sta_dirs: dict = {}
    all_figures: dict = {}
    for sta in stations:
        safe = sta.replace(" ", "_")
        sta_dir = out / safe
        sta_dir.mkdir(exist_ok=True)
        fig_cal  = str(sta_dir / "fig_calendar.png")
        fig_bars = str(sta_dir / "fig_bars.png")
        figure_calendar_heatmap(ica_df, sta, fig_cal)
        figure_ica_pollutant_bars(ica_df, sta, fig_bars)
        sta_dirs[sta] = sta_dir
        all_figures[sta] = {"fig_calendar": fig_cal, "fig_bars": fig_bars}

    # ── Build HTML ───────────────────────────────────────────────────────────
    legend_html = ica_category_legend_table()
    ts_b64 = _img_b64(fig_ts)

    # ICA summary narrative
    narrative_parts = []
    for sta in stations:
        sdf = ica_df.xs(sta, level="station")
        vals = sdf["ica_composite"].dropna()
        dominant = max(ICA_CATEGORIES, key=lambda c: sum(1 for v in vals if c[0] <= v <= c[1]))
        narrative_parts.append(
            f"En la estación <strong>{sta}</strong> la categoría predominante fue "
            f'<strong style="background:{dominant[3]};color:{dominant[4]};'
            f'padding:1px 6px;border-radius:3px">{dominant[2]}</strong> '
            f"con un ICA compuesto promedio de {vals.mean():.0f}."
        )

    # Per-pollutant subsections
    table_num = 25
    poll_sections_html = []
    for poll in pollutants:
        sect_html, table_num = _pollutant_section_html(
            df, ica_df, poll, stations, cal_paths, table_num
        )
        poll_sections_html.append(sect_html)

    # Composite summary tables per station
    summary_parts = [
        '<h2>Resumen ICA Compuesto</h2>',
        '<p>La siguiente tabla consolida el ICA compuesto diario por estación '
        '(valor máximo entre todos los contaminantes).</p>',
    ]
    for sta in stations:
        summary_parts.append(
            f'<div class="table-wrap">{ica_daily_table(ica_df, sta, table_num)}</div>'
        )
        bar_b64 = _img_b64(all_figures[sta]["fig_bars"])
        summary_parts.append(
            f'<figure>'
            f'<img src="{bar_b64}" alt="ICA por contaminante {sta}">'
            f'<p class="caption-fig">ICA diario por contaminante — {sta}.</p>'
            f'</figure>'
        )
        table_num += 1

    report_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>7. Índice de Calidad del Aire</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: Arial, sans-serif; font-size: 10pt; color: #000;
    max-width: 21cm; margin: 0 auto; padding: 2.5cm 2cm; line-height: 1.5;
  }}
  h1 {{
    font-size: 13pt; font-weight: bold; color: #1F4E79;
    text-transform: uppercase; border-bottom: 2px solid #1F4E79;
    padding-bottom: 5px; margin: 1.8em 0 0.8em;
  }}
  h2 {{
    font-size: 11pt; font-weight: bold; color: #1F4E79;
    margin: 1.6em 0 0.5em; border-bottom: 1px solid #D0D0D0; padding-bottom: 3px;
  }}
  p {{ text-align: justify; margin-bottom: 0.7em; }}
  .caption     {{ font-size: 9pt; font-weight: bold; margin-bottom: 5px; margin-top: 1em; }}
  .caption-fig {{ font-size: 9pt; font-weight: bold; text-align: center; margin-top: 6px; }}
  figure {{ margin: 1.2em 0 1.6em; text-align: center; page-break-inside: avoid; }}
  img {{ max-width: 100%; height: auto; }}
  .table-wrap {{ margin: 0.5em 0 1.4em; overflow-x: auto; }}
  hr {{ border: none; border-top: 1px solid #DDD; margin: 1.5em 0; }}
</style>
</head>
<body>

<h1>7. Índice de Calidad del Aire (ICA)</h1>

<p>
Teniendo en cuenta las Resolución 2254 de 2017 del MAVDT, los índices de calidad de aire se contemplan como una
herramienta de evaluación ambiental que permite tener una correlación de las concentraciones de algunos
contaminantes atmosféricos con los efectos en la salud.
Por ello la importancia de contemplarlos en el presente documento y categorizarlos a partir de la calificación
cuantitativa y cualitativa que se puede ver en la Figura 6.
</p>
<p style="text-align:center;font-style:italic;">
IP = ((I<sub>alto</sub> − I<sub>bajo</sub>) / (PC<sub>alto</sub> − PC<sub>bajo</sub>)) × (Cp − PC<sub>bajo</sub>) + I<sub>bajo</sub>
</p>
<p>Dónde:</p>
<ul style="margin:0.3em 0 0.8em 1.8em;line-height:1.7">
  <li><strong>IP</strong> = Índice para el contaminante p</li>
  <li><strong>CP</strong> = Concentración medida para el contaminante p</li>
  <li><strong>PC<sub>alto</sub></strong> = Punto de corte mayor o igual a CP</li>
  <li><strong>PC<sub>bajo</sub></strong> = Punto de corte menor o igual a CP</li>
  <li><strong>I<sub>alto</sub></strong> = Valor del Índice de Calidad del Aire correspondiente al BP<sub>Hi</sub></li>
  <li><strong>I<sub>bajo</sub></strong> = Valor del Índice de Calidad del Aire correspondiente al BP<sub>Lo</sub></li>
</ul>
<p>
El ICA será calculado a partir de la anterior ecuación, que corresponde a la metodología utilizada por la EPA para el
cálculo del AQI y será reportado el mayor valor que se obtenga del cálculo de cada uno de los contaminantes medidos.
</p>
<p>
{" ".join(narrative_parts)}
</p>

<p class="caption">Tabla de Escala de Colores ICA — Resolución 2254/2017</p>
<div class="table-wrap">{legend_html}</div>

<figure>
  <img src="{ts_b64}" alt="ICA compuesto todas las estaciones">
  <p class="caption-fig">ICA Compuesto diario — todas las estaciones.</p>
</figure>

{"<hr>".join(poll_sections_html)}

<hr>
{"".join(summary_parts)}

</body>
</html>"""

    report_path = out / "seccion7_ica.html"
    report_path.write_text(report_html, encoding="utf-8")

    ica_categories: dict = {}
    for sta in stations:
        sta_df = ica_df.xs(sta, level="station")
        ica_categories[sta] = {}
        for p in ICA_BREAKPOINTS:
            col = f"ica_{p}"
            if col not in sta_df.columns:
                continue
            counts: dict = {}
            for v in sta_df[col].dropna():
                cat = _ica_category(v)
                counts[cat] = counts.get(cat, 0) + 1
            ica_categories[sta][p] = counts
        comp_counts: dict = {}
        for v in sta_df["ica_composite"].dropna():
            cat = _ica_category(v)
            comp_counts[cat] = comp_counts.get(cat, 0) + 1
        ica_categories[sta]["composite"] = comp_counts

    return {
        "report_path": str(report_path),
        "stations": all_figures,
        "fig_timeseries": fig_ts,
        "ica_summary": {
            sta: {
                "mean_composite": float(ica_df.xs(sta, level="station")["ica_composite"].mean()),
                "max_composite":  float(ica_df.xs(sta, level="station")["ica_composite"].max()),
                "dominant_category": _ica_category(
                    ica_df.xs(sta, level="station")["ica_composite"].mean()
                ),
            }
            for sta in stations
        },
        "ica_categories": ica_categories,
    }