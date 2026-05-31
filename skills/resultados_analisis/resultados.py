"""Resultados del Análisis section skill — Section 6 of the air quality report.

Structure per pollutant (matching reference report CA.25420.I1):
  PM10/PM2.5:  daily combined table (all stations) → bar chart → box plot → timevariation
  SO2/NO2/CO/O3: daily summary table → bar/line chart → per-station hourly tables
                  → box plot → hourly time-series → timevariation

All concentration values are stored and displayed in µg/m³ (converted from native ppb/ppm).
"""

import base64
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Pollutant metadata and norms
# ─────────────────────────────────────────────────────────────────────────────

POLLUTANT_ORDER = ["pm10", "pm25", "so2", "no2", "co", "o3"]

POLLUTANT_META = {
    "pm10": {
        "col": "PM10 µg/m3 std", "conv": 1.0,
        "unit": "µg/m³", "label": "PM₁₀", "name": "Material Particulado PM₁₀",
        "table_type": "daily",
    },
    "pm25": {
        "col": "PM2.5 µg/m3 std", "conv": 1.0,
        "unit": "µg/m³", "label": "PM₂.₅", "name": "Material Particulado PM₂.₅",
        "table_type": "daily",
    },
    "so2": {
        "col": "SO2 ppb", "conv": 2.620,       # ppb → µg/m³
        "unit": "µg/m³", "label": "SO₂", "name": "Dióxido de Azufre SO₂",
        "table_type": "hourly",
    },
    "no2": {
        "col": "NO2 ppb", "conv": 1.880,       # ppb → µg/m³
        "unit": "µg/m³", "label": "NO₂", "name": "Dióxido de Nitrógeno NO₂",
        "table_type": "hourly",
    },
    "co": {
        "col": "CO ppm", "conv": 1145.0,       # ppm → µg/m³
        "unit": "µg/m³", "label": "CO", "name": "Monóxido de Carbono CO",
        "table_type": "hourly",
    },
    "o3": {
        "col": "O3 ppb", "conv": 1.960,        # ppb → µg/m³
        "unit": "µg/m³", "label": "O₃", "name": "Ozono O₃",
        "table_type": "hourly_8h",
    },
}

# Norms in µg/m³ per Res. 2254/2017 — (value, period_label, display_string)
NORMS = {
    "pm10": {"24h": (75.0,     "24 horas",  "75 µg/m³")},
    "pm25": {"24h": (37.0,     "24 horas",  "37 µg/m³")},
    "so2":  {"24h": (50.0,     "24 horas",  "50 µg/m³"),
              "1h":  (100.0,    "1 hora",    "100 µg/m³")},
    "no2":  {"1h":  (200.0,    "1 hora",    "200 µg/m³")},
    "co":   {"1h":  (35000.0,  "1 hora",    "35.000 µg/m³"),
              "8h":  (5000.0,   "8 horas",   "5.000 µg/m³")},
    "o3":   {"8h":  (100.0,    "8 horas",   "100 µg/m³")},
}

_SAFETY_ZONE = 0.95    # dashed line = norm × 0.95

_STATION_COLORS = ["#1F4E79", "#2E75B6", "#70AD47"]

_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

_DEFINITIONS = {
    "pm10": (
        "El material particulado con diámetro aerodinámico inferior a 10 micrómetros (PM₁₀) comprende "
        "partículas de origen natural y antropogénico, incluyendo polvo resuspendido, emisiones vehiculares, "
        "procesos industriales y quemas. Estas partículas pueden penetrar en el sistema respiratorio superior "
        "causando efectos adversos sobre la salud. La norma colombiana (Resolución 2254 de 2017) establece "
        "un nivel máximo permisible de 75 µg/m³ para un promedio de 24 horas."
    ),
    "pm25": (
        "El material particulado fino con diámetro aerodinámico inferior a 2.5 micrómetros (PM₂.₅) "
        "representa la fracción más peligrosa del material particulado por su capacidad de penetrar "
        "profundamente en los alvéolos pulmonares y pasar al torrente sanguíneo. Sus fuentes incluyen "
        "la combustión incompleta, emisiones vehiculares y reacciones fotoquímicas en la atmósfera. "
        "La norma colombiana (Resolución 2254 de 2017) establece un nivel máximo permisible de "
        "37 µg/m³ para un promedio de 24 horas."
    ),
    "so2": (
        "El dióxido de azufre (SO₂) es un gas incoloro con olor penetrante, producido principalmente "
        "en la combustión de combustibles fósiles con contenido de azufre y en procesos industriales. "
        "En la atmósfera puede oxidarse y combinarse con el vapor de agua para formar ácido sulfúrico, "
        "contribuyendo a la lluvia ácida. La norma colombiana (Resolución 2254 de 2017) establece "
        "niveles máximos permisibles de 50 µg/m³ para promedio de 24 horas y 100 µg/m³ para 1 hora."
    ),
    "no2": (
        "El dióxido de nitrógeno (NO₂) es un gas de color rojizo-marrón producido principalmente por "
        "la combustión a altas temperaturas en motores de vehículos y plantas de generación eléctrica. "
        "Participa en la formación del smog fotoquímico y del ozono troposférico. La norma colombiana "
        "(Resolución 2254 de 2017) establece un nivel máximo permisible de 200 µg/m³ para 1 hora."
    ),
    "co": (
        "El monóxido de carbono (CO) es un gas inodoro e incoloro producido por la combustión "
        "incompleta de combustibles fósiles. Es especialmente peligroso porque se une a la hemoglobina "
        "con mayor afinidad que el oxígeno, reduciendo la capacidad de transporte de oxígeno en la sangre. "
        "La norma colombiana (Resolución 2254 de 2017) establece niveles máximos permisibles de "
        "35.000 µg/m³ para 1 hora y 5.000 µg/m³ para promedio de 8 horas."
    ),
    "o3": (
        "El ozono troposférico (O₃) es un contaminante secundario formado por reacciones fotoquímicas "
        "entre óxidos de nitrógeno (NOₓ) y compuestos orgánicos volátiles (COVs) en presencia de "
        "radiación solar. La norma colombiana (Resolución 2254 de 2017) establece un nivel máximo "
        "permisible de 100 µg/m³ para un promedio móvil de 8 horas."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def load_pollutants(file_path: str) -> pd.DataFrame:
    """Load pollutants CSV and convert all values to µg/m³."""
    df = pd.read_csv(file_path, sep=";")
    df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"], dayfirst=False)
    df = df.drop(columns=["date", "time"]).set_index("datetime")
    for key, meta in POLLUTANT_META.items():
        col = meta["col"]
        if col in df.columns:
            df[key] = pd.to_numeric(df[col], errors="coerce") * meta["conv"]
    keep = ["station"] + [k for k in POLLUTANT_META if k in df.columns]
    return df[keep]


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _daily_avg(station_df: pd.DataFrame, pollutant: str) -> pd.Series:
    """24-hour daily mean per station."""
    return station_df[pollutant].groupby(station_df.index.date).mean()


def _rolling_8h(series: pd.Series) -> pd.Series:
    """8-hour rolling mean (min 6 valid hours)."""
    return series.rolling(8, min_periods=6).mean()


def _daily_8h_max(station_df: pd.DataFrame, pollutant: str) -> pd.Series:
    """Daily maximum of the 8-hour rolling mean per station."""
    roll = _rolling_8h(station_df[pollutant])
    return roll.groupby(roll.index.date).max()


# ─────────────────────────────────────────────────────────────────────────────
# Shared table helpers
# ─────────────────────────────────────────────────────────────────────────────

_TH = "padding:5px 7px;border:1px solid #aaa;text-align:center;vertical-align:middle"
_TD = "padding:4px 6px;border:1px solid #ccc;text-align:center"
_TD_L = "padding:4px 8px;border:1px solid #ccc;text-align:left"

def _comply_color(value: float, limit: float) -> str:
    if pd.isna(value):
        return "#F0F0F0"
    return "#92D050" if value <= limit else "#FF4444"


def _fmt(value, decimals: int = 2) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:,.{decimals}f}"


def _es_date(date) -> str:
    import datetime as _dt
    d = _dt.date.fromisoformat(str(date)) if not hasattr(date, "day") else date
    return f"{d.day} de {_MONTHS_ES[d.month]} de {d.year}"


def _stats_compliance_rows(
    values_per_station: dict,
    norm_value: float,
    norm_display: str,
    norm_period: str,
    total_cols: int | None = None,
) -> str:
    """Return HTML rows for Resumen Estadístico + Cumplimiento Normativo blocks.

    total_cols: full column count of the parent table (used for correct colspan).
                Defaults to n_stations + 1.
    """
    stations = list(values_per_station.keys())
    n = len(stations)
    header_span = total_cols if total_cols else (n + 1)
    label_span = max(1, header_span - n)
    rows = []

    # ── Resumen Estadístico ──────────────────────────────────────────────────
    rows.append(
        f'<tr style="background:#1F4E79;color:white;font-weight:bold">'
        f'<td colspan="{header_span}" style="{_TH}">Resumen Estadístico</td></tr>'
    )
    for label, fn in [
        ("Concentración Máxima - µg/m³", lambda s: s.max()),
        ("Concentración Mínima - µg/m³", lambda s: s.min()),
        ("Desviación Estándar σ - µg/m³", lambda s: s.std()),
        ("Promedio X̄ - µg/m³", lambda s: s.mean()),
    ]:
        rows.append("<tr>")
        rows.append(f'<td colspan="{label_span}" style="{_TD_L};font-style:italic">{label}</td>')
        for sta in stations:
            vals = values_per_station[sta].dropna()
            rows.append(f'<td style="{_TD}">{_fmt(fn(vals)) if len(vals) else "-"}</td>')
        rows.append("</tr>")

    # ── Cumplimiento Normativo ───────────────────────────────────────────────
    rows.append(
        f'<tr style="background:#1F4E79;color:white;font-weight:bold">'
        f'<td colspan="{header_span}" style="{_TH}">'
        f'Cumplimiento Normativo {norm_period} - Res 2254/2017 - {norm_display}'
        f'</td></tr>'
    )
    stats = []
    for sta in stations:
        vals = values_per_station[sta]
        n_total = len(vals)
        n_valid = int(vals.notna().sum())
        pct_valid = n_valid / n_total * 100 if n_total else 0
        n_exceed = int((vals.dropna() > norm_value).sum())
        pct_comply = (n_valid - n_exceed) / n_valid * 100 if n_valid else 0
        stats.append((n_valid, pct_valid, n_exceed, pct_comply))

    for label, idx, fmt_fn in [
        ("Numero de Muestras Válidas", 0, lambda x: f"{x:.0f}"),
        ("% Validez", 1, lambda x: f"{x:.2f}%"),
        ("Numero Excedencias", 2, lambda x: f"{x:.0f}"),
        ("% Cumplimiento", 3, lambda x: f"{x:.2f}%"),
    ]:
        rows.append("<tr>")
        rows.append(f'<td colspan="{label_span}" style="{_TD_L};font-style:italic">{label}</td>')
        for s in stats:
            rows.append(f'<td style="{_TD}">{fmt_fn(s[idx])}</td>')
        rows.append("</tr>")

    rows.append(
        f'<tr><td colspan="{header_span}" style="{_TD_L};font-size:8pt;color:#555">'
        "* Las casillas con color rojo representan dato que excede a la norma. "
        "*Las casillas con (-), representan datos no válidos.</td></tr>"
    )
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Table 1: daily combined (PM10, PM2.5)
# ─────────────────────────────────────────────────────────────────────────────

def daily_combined_table(df: pd.DataFrame, pollutant: str, table_num: int) -> str:
    """Color-coded daily 24h table with all stations + stats + compliance block."""
    norm_value, norm_period, norm_display = NORMS[pollutant]["24h"]
    meta = POLLUTANT_META[pollutant]
    stations = sorted(df["station"].unique())

    daily = {sta: _daily_avg(df[df["station"] == sta], pollutant) for sta in stations}
    all_dates = sorted(set().union(*[set(s.index) for s in daily.values()]))

    # Header
    sta_labels = [f"Est {i+1} - CA-{i+1}" for i in range(len(stations))]
    rows = [
        f'<table style="border-collapse:collapse;font-family:Arial;font-size:8.5pt;width:100%">',
        f'<thead>',
        f'<tr style="background:#1F4E79;color:white">',
        f'<td colspan="{len(stations) + 3}" style="{_TH};font-weight:bold">'
        f'Material Particulado - {meta["label"]} - µg/m³ - 24 horas</td></tr>',
        f'<tr style="background:#2E75B6;color:white">',
        f'<th style="{_TH}">Fecha</th>',
        f'<th style="{_TH}">Hora Inicio</th>',
        f'<th style="{_TH}">Hora Fin</th>',
    ]
    for lbl in sta_labels:
        rows.append(f'<th style="{_TH}">{lbl}</th>')
    rows.append("</tr></thead><tbody>")

    for date in all_dates:
        rows.append("<tr>")
        rows.append(f'<td style="{_TD}">{date}</td>')
        rows.append(f'<td style="{_TD}">0:00</td>')
        rows.append(f'<td style="{_TD}">23:00</td>')
        for sta in stations:
            val = daily[sta].get(date, float("nan"))
            bg = _comply_color(val, norm_value)
            rows.append(f'<td style="{_TD};background:{bg}">{_fmt(val)}</td>')
        rows.append("</tr>")

    total_cols = len(stations) + 3   # Fecha + Hora Inicio + Hora Fin + stations
    rows.append(_stats_compliance_rows(daily, norm_value, norm_display, norm_period, total_cols))
    rows.append("</tbody></table>")
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Table 2: per-station hourly (SO2, NO2, CO 1h)
# ─────────────────────────────────────────────────────────────────────────────

def hourly_station_table(
    df: pd.DataFrame,
    pollutant: str,
    station: str,
    norm_key: str,
    table_num: int,
) -> str:
    """24-row × n_days hourly table for one station + stats + compliance block."""
    norm_value, norm_period, norm_display = NORMS[pollutant][norm_key]
    meta = POLLUTANT_META[pollutant]
    sta_label = f"Est {sorted(df['station'].unique()).index(station) + 1} - CA-{sorted(df['station'].unique()).index(station) + 1}"
    sdf = df[df["station"] == station][pollutant]
    dates = sorted(set(sdf.index.date))
    n_days = len(dates)

    rows = [
        f'<table style="border-collapse:collapse;font-family:Arial;font-size:7.5pt;width:100%">',
        f'<thead>',
        f'<tr style="background:#1F4E79;color:white">',
        f'<td colspan="{n_days + 1}" style="{_TH};font-weight:bold">'
        f'Resultados {meta["label"]} - {meta["unit"]} - 1h | {sta_label}</td></tr>',
        f'<tr style="background:#2E75B6;color:white">',
        f'<th style="{_TH}">Hora</th>',
    ]
    for i, d in enumerate(dates):
        rows.append(f'<th style="{_TH}">Día {i+1}<br>{d}</th>')
    rows.append("</tr></thead><tbody>")

    valid_counts = [0] * n_days
    for hour in range(24):
        rows.append("<tr>")
        rows.append(f'<td style="{_TD}">{hour:02d}:00</td>')
        for j, date in enumerate(dates):
            try:
                ts = pd.Timestamp(f"{date} {hour:02d}:00")
                val = sdf.get(ts, float("nan"))
            except Exception:
                val = float("nan")
            if not pd.isna(val):
                valid_counts[j] += 1
            bg = _comply_color(val, norm_value)
            rows.append(f'<td style="{_TD};background:{bg}">{_fmt(val)}</td>')
        rows.append("</tr>")

    # Validity row
    rows.append('<tr style="background:#F0F0F0;font-weight:bold">')
    rows.append(f'<td style="{_TD_L}">Muestras Válidas</td>')
    for vc in valid_counts:
        rows.append(f'<td style="{_TD}">{vc}</td>')
    rows.append("</tr>")
    rows.append('<tr style="background:#F0F0F0">')
    rows.append(f'<td style="{_TD_L}">% Validez</td>')
    for vc in valid_counts:
        rows.append(f'<td style="{_TD}">{vc/24*100:.2f}%</td>')
    rows.append("</tr>")

    # Stats + compliance block (use all-day values)
    all_vals = pd.Series(
        [sdf.get(pd.Timestamp(f"{d} {h:02d}:00"), float("nan"))
         for d in dates for h in range(24)]
    )
    total_cols = n_days + 1   # Hora + one column per day
    rows.append(_stats_compliance_rows({sta_label: all_vals}, norm_value, norm_display, norm_period, total_cols))
    rows.append("</tbody></table>")
    return "\n".join(rows)


def hourly_8h_station_table(
    df: pd.DataFrame,
    pollutant: str,
    station: str,
    norm_key: str,
    table_num: int,
) -> str:
    """8-hour rolling mean table for one station + stats + compliance block."""
    norm_value, norm_period, norm_display = NORMS[pollutant][norm_key]
    meta = POLLUTANT_META[pollutant]
    stations_sorted = sorted(df["station"].unique())
    sta_idx = stations_sorted.index(station) + 1
    sta_label = f"Est {sta_idx} - CA-{sta_idx}"
    sdf = df[df["station"] == station][pollutant]
    roll = _rolling_8h(sdf)
    dates = sorted(set(d.date() if hasattr(d, 'date') else d for d in roll.index))
    n_days = len(dates)

    rows = [
        f'<table style="border-collapse:collapse;font-family:Arial;font-size:7.5pt;width:100%">',
        f'<thead>',
        f'<tr style="background:#1F4E79;color:white">',
        f'<td colspan="{n_days + 1}" style="{_TH};font-weight:bold">'
        f'Resultados {meta["label"]} - {meta["unit"]} - 8h | {sta_label}</td></tr>',
        f'<tr style="background:#2E75B6;color:white">',
        f'<th style="{_TH}">Hora</th>',
    ]
    for i, d in enumerate(dates):
        rows.append(f'<th style="{_TH}">Día {i+1}<br>{d}</th>')
    rows.append("</tr></thead><tbody>")

    valid_counts = [0] * n_days
    for hour in range(24):
        rows.append("<tr>")
        rows.append(f'<td style="{_TD}">{hour:02d}:00</td>')
        for j, date in enumerate(dates):
            try:
                ts = pd.Timestamp(f"{date} {hour:02d}:00")
                val = roll.get(ts, float("nan"))
            except Exception:
                val = float("nan")
            if not pd.isna(val):
                valid_counts[j] += 1
            bg = _comply_color(val, norm_value)
            rows.append(f'<td style="{_TD};background:{bg}">{_fmt(val)}</td>')
        rows.append("</tr>")

    rows.append('<tr style="background:#F0F0F0;font-weight:bold">')
    rows.append(f'<td style="{_TD_L}">Muestras Válidas</td>')
    for vc in valid_counts:
        rows.append(f'<td style="{_TD}">{vc}</td>')
    rows.append("</tr>")

    all_vals = roll.reset_index(drop=True)
    total_cols = n_days + 1   # Hora + one column per day
    rows.append(_stats_compliance_rows({sta_label: all_vals}, norm_value, norm_display, norm_period, total_cols))
    rows.append("</tbody></table>")
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────────────

def _add_norm_lines(ax, norm_value: float, label_norm: str):
    """Draw norm line and safety zone on an axes."""
    ax.axhline(norm_value, color="#C0392B", linewidth=1.5, linestyle="-",
               label=f"Lim Res 2254/2017 ({label_norm})", zorder=3)
    ax.axhline(norm_value * _SAFETY_ZONE, color="#C0392B", linewidth=1.2,
               linestyle="--", alpha=0.7, label="Zona de Seguridad", zorder=3)


def figure_bar_chart(df: pd.DataFrame, pollutant: str, output_path: str) -> str:
    """Grouped bar chart — daily 24h averages per station with norm + safety zone."""
    norm_value, _, norm_display = NORMS[pollutant].get("24h", list(NORMS[pollutant].values())[0])
    meta = POLLUTANT_META[pollutant]
    stations = sorted(df["station"].unique())
    daily = {sta: _daily_avg(df[df["station"] == sta], pollutant) for sta in stations}
    all_dates = sorted(set().union(*[set(s.index) for s in daily.values()]))

    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(all_dates))
    w = 0.25
    offsets = np.linspace(-(len(stations)-1)/2, (len(stations)-1)/2, len(stations)) * w

    for i, (sta, offset) in enumerate(zip(stations, offsets)):
        vals = [daily[sta].get(d, np.nan) for d in all_dates]
        lbl = f"Est {i+1} - CA-{i+1}"
        ax.bar(x + offset, vals, width=w * 0.9, color=_STATION_COLORS[i],
               label=lbl, alpha=0.85, edgecolor="white", linewidth=0.4)

    _add_norm_lines(ax, norm_value, norm_display)
    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"Día {i+1}\n{d}" for i, d in enumerate(all_dates)],
        rotation=30, ha="right", fontsize=7.5,
    )
    ax.set_ylabel(f"{meta['label']} ({meta['unit']})", fontsize=9)
    ax.set_title(
        f"{meta['name']} — concentraciones diarias (24 h)",
        fontsize=10, fontweight="bold",
    )
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)
    ax.set_xlim(x[0] - 0.5, x[-1] + 0.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def figure_timeseries_hourly(
    df: pd.DataFrame, pollutant: str, norm_key: str, output_path: str
) -> str:
    """Hourly time-series line chart (all stations) with norm + safety zone."""
    norm_value, _, norm_display = NORMS[pollutant][norm_key]
    meta = POLLUTANT_META[pollutant]
    stations = sorted(df["station"].unique())

    fig, ax = plt.subplots(figsize=(13, 4.5))
    for i, sta in enumerate(stations):
        sdf = df[df["station"] == sta][pollutant]
        if norm_key == "8h":
            sdf = _rolling_8h(sdf)
        lbl = f"Est {i+1} - CA-{i+1}"
        ax.plot(sdf.index, sdf.values, color=_STATION_COLORS[i],
                linewidth=0.9, label=lbl, alpha=0.85)

    _add_norm_lines(ax, norm_value, norm_display)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(f"{meta['label']} ({meta['unit']})", fontsize=9)
    period_label = "1 hora" if norm_key == "1h" else "8 horas"
    ax.set_title(
        f"{meta['name']} — concentraciones horarias ({period_label})",
        fontsize=10, fontweight="bold",
    )
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.25, linewidth=0.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def figure_boxplot(df: pd.DataFrame, pollutant: str, output_path: str) -> str:
    """Box plot showing hourly distribution per station with norm line."""
    norm_key = list(NORMS[pollutant].keys())[-1]
    norm_value, _, norm_display = NORMS[pollutant][norm_key]
    meta = POLLUTANT_META[pollutant]
    stations = sorted(df["station"].unique())
    sta_labels = [f"Est {i+1} - CA-{i+1}" for i in range(len(stations))]
    data = []
    for sta in stations:
        sdf = df[df["station"] == sta][pollutant]
        if norm_key == "8h":
            sdf = _rolling_8h(sdf)
        data.append(sdf.dropna().values)

    fig, ax = plt.subplots(figsize=(6, 4.5))
    bp = ax.boxplot(data, tick_labels=sta_labels, patch_artist=True,
                    medianprops={"color": "black", "linewidth": 1.5},
                    whiskerprops={"linewidth": 1}, capprops={"linewidth": 1})
    for patch, color in zip(bp["boxes"], _STATION_COLORS):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    _add_norm_lines(ax, norm_value, norm_display)
    ax.set_ylabel(f"{meta['label']} ({meta['unit']})", fontsize=9)
    ax.set_title(f"Distribución — {meta['name']}", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def figure_timevariation(df: pd.DataFrame, pollutant: str, output_path: str) -> str:
    """3-panel time-variation: by hour of day, by day of week, by date."""
    meta = POLLUTANT_META[pollutant]
    stations = sorted(df["station"].unique())
    WEEKDAYS_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    fig.suptitle(f"Perfil Temporal — {meta['name']}", fontsize=10, fontweight="bold")

    for i, sta in enumerate(stations):
        sdf = df[df["station"] == sta][pollutant].dropna()
        lbl = f"Est {i+1} - CA-{i+1}"
        color = _STATION_COLORS[i]

        # Panel 1: by hour of day
        by_hour = sdf.groupby(sdf.index.hour)
        means = by_hour.mean()
        sems  = by_hour.sem()
        axes[0].plot(means.index, means.values, color=color, linewidth=1.5, label=lbl)
        axes[0].fill_between(means.index, means - sems, means + sems,
                             color=color, alpha=0.15)

        # Panel 2: by day of week (0=Monday)
        by_dow = sdf.groupby(sdf.index.dayofweek)
        means_dow = by_dow.mean()
        if not means_dow.empty:
            axes[1].plot(means_dow.index, means_dow.values, color=color,
                         linewidth=1.5, marker="o", markersize=4, label=lbl)

        # Panel 3: daily trend
        by_date = sdf.groupby(sdf.index.date).mean()
        axes[2].plot(
            [pd.Timestamp(str(d)) for d in by_date.index],
            by_date.values,
            color=color, linewidth=1.5, marker="o", markersize=4, label=lbl,
        )

    axes[0].set_xlabel("Hora del día", fontsize=8)
    axes[0].set_ylabel(f"{meta['label']} ({meta['unit']})", fontsize=8)
    axes[0].set_title("Variación horaria promedio", fontsize=8.5, fontweight="bold")
    axes[0].set_xticks(range(0, 24, 3))
    axes[0].grid(alpha=0.3)
    axes[0].legend(fontsize=7.5)

    axes[1].set_xlabel("Día de la semana", fontsize=8)
    axes[1].set_title("Variación por día de semana", fontsize=8.5, fontweight="bold")
    axes[1].set_xticks(range(7))
    axes[1].set_xticklabels(WEEKDAYS_ES, fontsize=7.5)
    axes[1].grid(alpha=0.3)
    axes[1].legend(fontsize=7.5)

    axes[2].set_title("Tendencia diaria por estación", fontsize=8.5, fontweight="bold")
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    axes[2].xaxis.set_major_locator(mdates.DayLocator())
    plt.setp(axes[2].get_xticklabels(), rotation=30, ha="right", fontsize=7.5)
    axes[2].grid(alpha=0.3)
    axes[2].legend(fontsize=7.5)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Auto-generated analysis text
# ─────────────────────────────────────────────────────────────────────────────

def generate_pollutant_text(df: pd.DataFrame, pollutant: str, norm_key: str) -> str:
    norm_value, norm_period, norm_display = NORMS[pollutant][norm_key]
    meta = POLLUTANT_META[pollutant]
    stations = sorted(df["station"].unique())

    all_vals = df[pollutant].dropna()
    overall_max = all_vals.max()
    overall_min = all_vals.min()
    overall_mean = all_vals.mean()

    # Station with highest max
    max_by_sta = {
        sta: df[df["station"] == sta][pollutant].max() for sta in stations
    }
    highest_sta = max(max_by_sta, key=max_by_sta.get)
    highest_idx = sorted(stations).index(highest_sta) + 1
    highest_val = max_by_sta[highest_sta]
    highest_ts = df[df["station"] == highest_sta][pollutant].idxmax()

    # Exceedances
    if norm_key in ("24h",):
        daily = {sta: _daily_avg(df[df["station"] == sta], pollutant) for sta in stations}
        exceed = [(f"CA-{sorted(stations).index(s)+1}", int((daily[s].dropna() > norm_value).sum()))
                  for s in stations if (daily[s].dropna() > norm_value).sum() > 0]
    elif norm_key == "8h":
        exceed = [(f"CA-{sorted(stations).index(s)+1}", int((_daily_8h_max(df[df["station"] == s], pollutant).dropna() > norm_value).sum()))
                  for s in stations if (_daily_8h_max(df[df["station"] == s], pollutant).dropna() > norm_value).sum() > 0]
    else:
        exceed = [(f"CA-{sorted(stations).index(s)+1}", int((df[df["station"] == s][pollutant].dropna() > norm_value).sum()))
                  for s in stations if (df[df["station"] == s][pollutant].dropna() > norm_value).sum() > 0]

    if exceed:
        compliance_str = (
            f"Se registraron superaciones del límite máximo permisible en: "
            + ", ".join(f"estación {s} ({n} evento(s))" for s, n in exceed) + "."
        )
    else:
        compliance_str = (
            f"Las concentraciones de {meta['label']} en todas las estaciones de monitoreo "
            f"se mantuvieron por debajo del límite máximo permisible ({norm_display}) "
            f"durante todo el período de evaluación, representando un cumplimiento pleno."
        )

    period = f"{_es_date(df.index[0].date())} al {_es_date(df.index[-1].date())}"
    ts_str = highest_ts.strftime("%d de %B de %Y a las %H:%M") if hasattr(highest_ts, "strftime") else str(highest_ts)

    return (
        f"En la gráfica se muestran los resultados del contaminante {meta['name']} en las "
        f"estaciones de monitoreo durante el período comprendido entre el {period}. "
        f"La estación CA-{highest_idx} registró las concentraciones más elevadas con un máximo de "
        f"{highest_val:,.2f} {meta['unit']}, registrado el {ts_str}. "
        f"{compliance_str}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML report assembler
# ─────────────────────────────────────────────────────────────────────────────

def _img_b64(path: str) -> str:
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def build_report_html(pollutant_blocks: list, period: str) -> str:
    sections_html = []
    table_num = 17
    fig_num = 4

    for block in pollutant_blocks:
        p = block["pollutant"]
        meta = POLLUTANT_META[p]
        subsec_num = POLLUTANT_ORDER.index(p) + 1

        sec_html = [f'<h2>6.{subsec_num} {meta["name"]}</h2>']
        sec_html.append(f'<p>{_DEFINITIONS[p]}</p>')

        # ── daily combined table (PM10, PM2.5) ────────────────────────────
        if meta["table_type"] == "daily":
            norm_v, norm_per, norm_disp = NORMS[p]["24h"]
            sec_html.append(
                f'<p class="caption">Tabla {table_num}. Resumen Estadístico {meta["name"]} — '
                f'período {period}</p>'
            )
            sec_html.append(f'<div class="table-wrap">{block["table_daily"]}</div>')
            table_num += 1

            bar_b64 = _img_b64(block["fig_bar"])
            sec_html.append(f"""<figure>
  <img src="{bar_b64}" alt="Concentraciones diarias {meta['label']}">
  <p class="caption-fig">Gráfica {fig_num}. Resultados {meta['name']} tiempo de exposición 24 horas.</p>
</figure>""")
            fig_num += 1

            sec_html.append(f'<p>{block["text_daily"]}</p>')

            box_b64 = _img_b64(block["fig_box"])
            sec_html.append(f"""<figure>
  <img class="half" src="{box_b64}" alt="Diagrama de cajas {meta['label']}">
  <p class="caption-fig">Gráfica {fig_num}. Diagrama de Cajas {meta['name']}.</p>
</figure>""")
            fig_num += 1

            tv_b64 = _img_b64(block["fig_tv"])
            sec_html.append(f"""<figure>
  <img src="{tv_b64}" alt="Perfil temporal {meta['label']}">
  <p class="caption-fig">Gráfica {fig_num}. Perfil Temporal {meta['name']}.</p>
</figure>""")
            fig_num += 1

        # ── gaseous pollutants (SO2, NO2, CO, O3) ─────────────────────────
        else:
            norm_key_daily = "24h" if "24h" in NORMS[p] else ("1h" if "1h" in NORMS[p] else "8h")
            norm_v, norm_per, norm_disp = NORMS[p][norm_key_daily]

            # Daily summary table
            sec_html.append(
                f'<p class="caption">Tabla {table_num}. Resumen Estadístico {meta["name"]} — '
                f'promedio {norm_per} — período {period}</p>'
            )
            sec_html.append(f'<div class="table-wrap">{block["table_daily"]}</div>')
            table_num += 1

            # Bar chart (daily)
            bar_b64 = _img_b64(block["fig_bar"])
            sec_html.append(f"""<figure>
  <img src="{bar_b64}" alt="Concentraciones diarias {meta['label']}">
  <p class="caption-fig">Gráfica {fig_num}. Resultados {meta['name']} tiempo de exposición {norm_per}.</p>
</figure>""")
            fig_num += 1
            sec_html.append(f'<p>{block["text_daily"]}</p>')

            # Per-station hourly tables
            for sta_idx, (sta, tbl) in enumerate(block["tables_hourly"].items()):
                sta_lbl = f"Est {sta_idx+1} CA-{sta_idx+1}"
                sec_html.append(
                    f'<p class="caption">Tabla {table_num}. Resultados {meta["label"]} — '
                    f'1h — {sta_lbl} — período {period}</p>'
                )
                sec_html.append(f'<div class="table-wrap">{tbl}</div>')
                table_num += 1

            # 8h tables (CO and O3)
            for sta_idx, (sta, tbl) in enumerate(block.get("tables_8h", {}).items()):
                sta_lbl = f"Est {sta_idx+1} CA-{sta_idx+1}"
                sec_html.append(
                    f'<p class="caption">Tabla {table_num}. Resultados {meta["label"]} — '
                    f'8h — {sta_lbl} — período {period}</p>'
                )
                sec_html.append(f'<div class="table-wrap">{tbl}</div>')
                table_num += 1

            # Box plot
            box_b64 = _img_b64(block["fig_box"])
            sec_html.append(f"""<figure>
  <img class="half" src="{box_b64}" alt="Diagrama de cajas {meta['label']}">
  <p class="caption-fig">Gráfica {fig_num}. Diagrama de Cajas {meta['name']}.</p>
</figure>""")
            fig_num += 1

            # Hourly time-series
            for norm_k, path in block.get("figs_ts", {}).items():
                ts_b64 = _img_b64(path)
                period_lbl = "1 hora" if norm_k == "1h" else "8 horas"
                sec_html.append(f"""<figure>
  <img src="{ts_b64}" alt="Serie de tiempo {meta['label']} {period_lbl}">
  <p class="caption-fig">Gráfica {fig_num}. Resultados {meta['name']} tiempo de exposición {period_lbl}.</p>
</figure>""")
                fig_num += 1

            sec_html.append(f'<p>{block["text_hourly"]}</p>')

            # Time variation
            tv_b64 = _img_b64(block["fig_tv"])
            sec_html.append(f"""<figure>
  <img src="{tv_b64}" alt="Perfil temporal {meta['label']}">
  <p class="caption-fig">Gráfica {fig_num}. Perfil Temporal {meta['name']}.</p>
</figure>""")
            fig_num += 1

        sections_html.append("\n".join(sec_html))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>6. Resultados del Análisis</title>
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
  .caption {{ font-size: 9pt; font-weight: bold; margin-bottom: 5px; margin-top: 1em; }}
  .caption-fig {{ font-size: 9pt; font-weight: bold; text-align: center; margin-top: 6px; }}
  figure {{ margin: 1.2em 0 1.6em; text-align: center; page-break-inside: avoid; }}
  img {{ max-width: 100%; height: auto; }}
  img.half {{ max-width: 55%; }}
  .table-wrap {{ margin: 0.5em 0 1.4em; overflow-x: auto; }}
</style>
</head>
<body>

<h1>6. Resultados y Análisis</h1>

<p>
El presente capítulo se dividirá en tres secciones: la primera contiene los resultados de las concentraciones en un
periodo de exposición de 1 hora, 8 horas y 24 horas; estos comparados con los respectivos limites normativos por
contaminante medido, la segunda parte presenta los perfiles horarios de los diferentes contaminantes medidos, los
cuales indican las horas del día en que mayor concentración se registra y por ultimo un análisis estadístico de los
resultados de 18 días de medición por cada uno de los parámetros medidos.
</p>
<p>
El presente informe es complementado por el Anexo 1 donde se presentan el reporte de resultados, el Anexo 2 con
el certificado de acreditación de laboratorio del IDEAM., Anexo 3 calibraciones y certificaciones de los analizadores
empleados, en el Anexo 4 se muestran los resultados de velocidad y dirección de vientos, en el Anexo 5 las fichas
técnicas de campo, en el Anexo 6 se halla la Geo-data-base, fundada bajo los requisitos de la resolución 2182 de
2016 y en el Anexo 7 se presenta la cartográfica de las estaciones de monitoreo.
El desarrollo de actividades industriales genera emisiones de diferentes contaminantes a la atmósfera, con la intención
de evaluar, cuantificar y generar sistemas de gestión pertinentes es por esto por lo que se ha realizado un monitoreo
de calidad del aire, evaluando los contaminantes criterio, dados en la resolución 2254 de 2017 en tres (3) estaciones
en el área de influencia de la planta de la estación Chimita, ubicada en el municipio de Girón, departamento de
Santander. La campaña de monitoreo de calidad del aire se realizó durante una temporada seca, entre el 17 de
diciembre de 2025 al 03 de enero de 2026, durante 18 días, con mediciones diarias.
Se presentan los resultados obtenidos de cada contaminante en cada estación, así mismo, algunos datos estadísticos.
Los intervalos de confianza presentados se calcularon a partir de la distribución t-student (97,5%). Dicha distribución
resulta ser trascendental para aplicaciones inferenciales, en especial para aquellas en las que se desconoce la
varianza; dado que no depende de las varianzas de las variables que la integran. Los valores de esta distribución
están dados por: En función de los grados de libertad, se determina el cuartil en la tabla para el cálculo del intervalo
de confianza; el cuartil en este caso es de 97,5%.
</p>
<p>
La regla de decisión, seleccionada por Corola Ambiental es la “binaria” que se encuentra descrita en el documento
ILAC-G8:09/2019 “Guidelines on Decision Rules and Statements of Conformity”. Para los ensayos y/o monitoreos, se
aplica la regla de decisión basada en zona de seguridad (concentración en µg/m3 +/- incertidumbre expandida). Se
elige una zona de seguridad igual a la incertidumbre expandida (k = 2), tanto para el límite normativo como para el
dato de concentración medido de cada parámetro.
Por lo tanto, COROLA AMBIENTAL S.A.S., documenta una regla de decisión acorde a la normativa aplicada, al
resultado del monitoreo y ensayo reportado y la incertidumbre de medición.
</p>
<p>
Para la declaración de conformidad de los resultados Corola Ambiental SAS, implementa los conceptos de :
•Cumple/conforme: cuando el resultado ± incertidumbre de medición está dentro del límite de aceptación de la
normatividad aplicada según corresponda, generando una zona de aceptación o de seguridad la cual se calculó
restándole el valor de incertidumbre al límite normativo, además de aplicarle la incertidumbre a cada valor reportado
y cuando el resultado más la incertidumbre no se sobreponga a la zona de seguridad o esté por debajo, se declarará
el cumplimiento de la medición respecto al límite normativo correspondiente.
</p>
<p>
•No cumple/No conforme: cuando el resultado ± incertidumbre de medición está por encima del límite de aceptación
de la normatividad aplicada según corresponda, para esto se genera una zona de aceptación o de seguridad la cual
se calcula restándole el valor de incertidumbre al límite normativo, además de aplicarle la incertidumbre a cada valor
reportado y cuando el resultado más la incertidumbre se sobreponga a la zona de seguridad o esté por encima, se
declarará el incumplimiento de la medición respecto al límite normativo correspondiente.
Los resultados del presente informe solo hacen referencia a las muestras tomadas en campo para el cliente en
mención, de acuerdo con la información descrita en las fechas y locaciones establecidas del presente documento.
Prohibida la reproducción parcial o total del presente informe sin la aprobación escrita del laboratorio.

<p>
En las tablas de resultados, las casillas con color <strong style="color:#27AE60">verde</strong>
representan concentraciones por debajo del límite normativo y las casillas con color
<strong style="color:#C0392B">rojo</strong> representan datos que exceden la norma.
Las casillas con (-) representan datos no válidos.
</p>

{"<hr>".join(sections_html)}

</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(file_path: str, output_dir: str) -> dict:
    """Generate Section 6 — Resultados del Análisis as a self-contained HTML report."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = load_pollutants(file_path)
    stations = sorted(df["station"].unique())
    period = f"{_es_date(df.index[0].date())} al {_es_date(df.index[-1].date())}"

    pollutant_blocks = []
    all_figures = {}

    for pollutant in POLLUTANT_ORDER:
        if pollutant not in df.columns:
            continue
        p_out = out / pollutant
        p_out.mkdir(exist_ok=True)
        meta = POLLUTANT_META[pollutant]
        block = {"pollutant": pollutant}

        # ── daily summary table (all pollutants) ──────────────────────────
        if meta["table_type"] == "daily":
            block["table_daily"] = daily_combined_table(df, pollutant, 0)
        else:
            # for gaseous: build a combined daily table using the primary norm
            norm_key = "24h" if "24h" in NORMS[pollutant] else ("1h" if "1h" in NORMS[pollutant] else "8h")
            norm_value, norm_period, norm_display = NORMS[pollutant][norm_key]
            if norm_key == "24h":
                daily_vals = {sta: _daily_avg(df[df["station"] == sta], pollutant) for sta in stations}
            elif norm_key == "8h":
                daily_vals = {sta: _daily_8h_max(df[df["station"] == sta], pollutant) for sta in stations}
            else:
                daily_vals = {sta: df[df["station"] == sta][pollutant].groupby(df[df["station"] == sta].index.date).mean() for sta in stations}

            all_dates = sorted(set().union(*[set(s.index) for s in daily_vals.values()]))
            sta_labels = [f"Est {i+1} - CA-{i+1}" for i in range(len(stations))]
            rows = [
                f'<table style="border-collapse:collapse;font-family:Arial;font-size:8.5pt;width:100%">',
                f'<thead><tr style="background:#1F4E79;color:white">',
                f'<td colspan="{len(stations)+3}" style="{_TH};font-weight:bold">'
                f'{meta["label"]} - µg/m³ - {norm_period}</td></tr>',
                f'<tr style="background:#2E75B6;color:white">',
                f'<th style="{_TH}">Fecha</th>',
                f'<th style="{_TH}">Hora Inicio</th>',
                f'<th style="{_TH}">Hora Fin</th>',
            ]
            for lbl in sta_labels:
                rows.append(f'<th style="{_TH}">{lbl}</th>')
            rows.append("</tr></thead><tbody>")
            h_end = "23:00" if norm_key == "24h" else ("-- (8h)",)
            for date in all_dates:
                rows.append("<tr>")
                rows.append(f'<td style="{_TD}">{date}</td>')
                rows.append(f'<td style="{_TD}">0:00</td>')
                rows.append(f'<td style="{_TD}">23:00</td>')
                for sta in stations:
                    val = daily_vals[sta].get(date, float("nan"))
                    bg = _comply_color(val, norm_value)
                    rows.append(f'<td style="{_TD};background:{bg}">{_fmt(val)}</td>')
                rows.append("</tr>")
            labeled_vals = {f"Est {i+1} - CA-{i+1}": daily_vals[sta]
                            for i, sta in enumerate(stations)}
            total_cols = len(stations) + 3   # Fecha + Hora Inicio + Hora Fin + stations
            rows.append(_stats_compliance_rows(labeled_vals, norm_value, norm_display, norm_period, total_cols))
            rows.append("</tbody></table>")
            block["table_daily"] = "\n".join(rows)

        # ── bar chart ─────────────────────────────────────────────────────
        block["fig_bar"] = figure_bar_chart(df, pollutant, str(p_out / "fig_bar.png"))

        # ── box plot ──────────────────────────────────────────────────────
        block["fig_box"] = figure_boxplot(df, pollutant, str(p_out / "fig_box.png"))

        # ── time variation ────────────────────────────────────────────────
        block["fig_tv"] = figure_timevariation(df, pollutant, str(p_out / "fig_tv.png"))

        # ── per-station hourly tables and time-series (gaseous only) ──────
        if meta["table_type"] in ("hourly", "hourly_8h"):
            block["tables_hourly"] = {}
            block["tables_8h"] = {}
            block["figs_ts"] = {}

            if meta["table_type"] == "hourly":
                # 1h tables
                for sta in stations:
                    block["tables_hourly"][sta] = hourly_station_table(
                        df, pollutant, sta, "1h", 0
                    )
                block["figs_ts"]["1h"] = figure_timeseries_hourly(
                    df, pollutant, "1h", str(p_out / "fig_ts_1h.png")
                )
                # 8h tables for CO
                if pollutant == "co":
                    for sta in stations:
                        block["tables_8h"][sta] = hourly_8h_station_table(
                            df, pollutant, sta, "8h", 0
                        )
                    block["figs_ts"]["8h"] = figure_timeseries_hourly(
                        df, pollutant, "8h", str(p_out / "fig_ts_8h.png")
                    )
            else:
                # O3 — only 8h tables
                for sta in stations:
                    block["tables_8h"][sta] = hourly_8h_station_table(
                        df, pollutant, sta, "8h", 0
                    )
                block["figs_ts"]["8h"] = figure_timeseries_hourly(
                    df, pollutant, "8h", str(p_out / "fig_ts_8h.png")
                )

        # ── auto-generated text ───────────────────────────────────────────
        primary_norm = "24h" if "24h" in NORMS[pollutant] else ("1h" if "1h" in NORMS[pollutant] else "8h")
        block["text_daily"] = generate_pollutant_text(df, pollutant, primary_norm)
        if meta["table_type"] != "daily":
            block["text_hourly"] = generate_pollutant_text(df, pollutant, primary_norm)

        pollutant_blocks.append(block)
        all_figures[pollutant] = {k: v for k, v in block.items() if k.startswith("fig")}

    report_html = build_report_html(pollutant_blocks, period)
    report_path = out / "seccion6_resultados.html"
    report_path.write_text(report_html, encoding="utf-8")

    return {
        "report_path": str(report_path),
        "pollutants": all_figures,
    }