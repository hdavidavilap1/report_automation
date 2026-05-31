"""Meteorologia section skill — generates Table 16, Gráficas 1-3, and descriptive text."""

import base64
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from windrose import WindroseAxes

# ---------------------------------------------------------------------------
# Spanish month names for narrative text
# ---------------------------------------------------------------------------
_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

# 16-point compass in Spanish (O = Oeste, not W)
_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_meteo(file_path: str) -> pd.DataFrame:
    """Parse the meteo CSV or imputed parquet into an indexed DataFrame.

    Expected columns (semicolon-delimited or parquet):
    date;time;Temp Out - Ind;Hum Out - Ind;Wind Speed - Ind;Wind Dir;Press - Ind;Rain - mm;Radiacion Solar
    Column names are matched case-insensitively so imputed parquet files work too.
    """
    p = Path(file_path)
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p, sep=";")
    date_col = next((c for c in df.columns if c.lower() == "date"), "date")
    time_col = next((c for c in df.columns if c.lower() == "time"), "time")
    df["datetime"] = pd.to_datetime(df[date_col] + " " + df[time_col], dayfirst=False)
    df = df.set_index("datetime").drop(columns=[date_col, time_col])
    df.columns = ["temp", "hum", "ws", "wd", "press", "rain", "rad"]
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prevailing_direction(wd_series: pd.Series) -> str:
    """Return the modal 16-point compass direction from a degree series."""
    valid = wd_series.dropna()
    if valid.empty:
        return "N/D"
    labels = valid.apply(lambda d: _COMPASS[round(d / 22.5) % 16])
    return labels.mode().iloc[0]


def _gyr_color(value: float, vmin: float, vmax: float, reverse: bool = False) -> str:
    """Map a value to a green→yellow→red hex color."""
    if pd.isna(value) or vmax == vmin:
        return "#FFFFFF"
    norm = (value - vmin) / (vmax - vmin)
    if reverse:
        norm = 1.0 - norm
    cmap = mcolors.LinearSegmentedColormap.from_list("gyr", ["#92D050", "#FFFF00", "#FF4444"])
    return mcolors.to_hex(cmap(float(np.clip(norm, 0, 1))))


def _fmt(value, decimals: int = 1) -> str:
    if pd.isna(value):
        return "N/D"
    return f"{value:.{decimals}f}"


def _es_date(date) -> str:
    """Format a date as '15 de abril de 2026'."""
    if hasattr(date, "day"):
        d, m, y = date.day, date.month, date.year
    else:
        import datetime as _dt
        d_obj = _dt.date.fromisoformat(str(date))
        d, m, y = d_obj.day, d_obj.month, d_obj.year
    return f"{d} de {_MONTHS_ES[m]} de {y}"


# ---------------------------------------------------------------------------
# Table 16 — daily meteorological summary (HTML)
# ---------------------------------------------------------------------------

def daily_summary_table(df: pd.DataFrame) -> str:
    """Return a color-coded HTML table with daily meteorological statistics."""
    grp = df.groupby(df.index.date)

    daily = grp.agg(
        T_max=("temp", "max"),
        T_min=("temp", "min"),
        T_prom=("temp", "mean"),
        HR_max=("hum", "max"),
        HR_min=("hum", "min"),
        HR_prom=("hum", "mean"),
        Prec=("rain", "sum"),
        WS_max=("ws", "max"),
        WS_prom=("ws", "mean"),
    )
    daily["WD_prev"] = [
        _prevailing_direction(df[df.index.date == d]["wd"]) for d in daily.index
    ]

    # (column_name, reverse_color_scale)
    # reverse=True means low value → red (e.g. T_min: colder = more extreme)
    _color_cfg = [
        ("T_max",   False),
        ("T_min",   True),
        ("T_prom",  False),
        ("HR_max",  False),
        ("HR_min",  True),
        ("HR_prom", False),
        ("Prec",    False),
        ("WS_max",  False),
        ("WS_prom", False),
    ]
    ranges = {col: (daily[col].min(), daily[col].max(), rev) for col, rev in _color_cfg}

    headers = [
        "Fecha",
        "T<sub>máx</sub><br>(°C)",
        "T<sub>mín</sub><br>(°C)",
        "T<sub>prom</sub><br>(°C)",
        "HR<sub>máx</sub><br>(%)",
        "HR<sub>mín</sub><br>(%)",
        "HR<sub>prom</sub><br>(%)",
        "Prec.<br>(mm)",
        "WS<sub>máx</sub><br>(m/s)",
        "WS<sub>prom</sub><br>(m/s)",
        "Dir.<br>Predominante",
    ]

    th_style = "padding:5px 7px;border:1px solid #aaa;text-align:center;vertical-align:middle"
    td_style = "padding:4px 6px;border:1px solid #ccc;text-align:center"

    rows = []
    rows.append(
        '<table style="border-collapse:collapse;font-family:Arial;font-size:8.5pt;width:100%">'
    )
    rows.append('<thead><tr style="background:#2E74B5;color:white">')
    for h in headers:
        rows.append(f'<th style="{th_style}">{h}</th>')
    rows.append("</tr></thead><tbody>")

    for date, row in daily.iterrows():
        rows.append("<tr>")
        rows.append(f'<td style="{td_style}">{date}</td>')
        for col, rev in _color_cfg:
            vmin, vmax, _ = ranges[col]
            bg = _gyr_color(row[col], vmin, vmax, rev)
            rows.append(
                f'<td style="{td_style};background:{bg}">{_fmt(row[col])}</td>'
            )
        rows.append(f'<td style="{td_style}">{row["WD_prev"]}</td>')
        rows.append("</tr>")

    rows.append("</tbody></table>")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Gráfica 1 — 6-panel time series
# ---------------------------------------------------------------------------

def figure_timeseries(df: pd.DataFrame, output_path: str) -> str:
    """Save a 6-panel time-series figure and return the file path."""
    panels = [
        ("temp",  "Temperatura (°C)",          "#D62728"),
        ("hum",   "Humedad Relativa (%)",       "#1F77B4"),
        ("rain",  "Precipitación (mm)",          "#2CA02C"),
        ("ws",    "Vel. Viento (m/s)",           "#FF7F0E"),
        ("wd",    "Dir. Viento (°)",             "#9467BD"),
        ("rad",   "Rad. Solar (W/m²)",           "#8C564B"),
    ]

    fig, axes = plt.subplots(len(panels), 1, figsize=(13, 14), sharex=True)
    fig.subplots_adjust(hspace=0.12, left=0.09, right=0.97, top=0.96, bottom=0.06)

    for ax, (col, label, color) in zip(axes, panels):
        ax.plot(df.index, df[col], color=color, linewidth=0.9, alpha=0.85)
        ax.set_ylabel(label, fontsize=8, labelpad=4)
        ax.grid(True, alpha=0.25, linewidth=0.5)
        ax.tick_params(axis="both", labelsize=7.5)
        ax.margins(x=0.01)

    # Precipitation as bar instead of line
    ax_rain = axes[2]
    ax_rain.clear()
    ax_rain.bar(df.index, df["rain"].fillna(0), color="#2CA02C", width=1/24, alpha=0.8)
    ax_rain.set_ylabel("Precipitación (mm)", fontsize=8, labelpad=4)
    ax_rain.grid(True, alpha=0.25, linewidth=0.5)
    ax_rain.tick_params(axis="both", labelsize=7.5)
    ax_rain.margins(x=0.01)

    # Wind direction as scatter (to avoid connecting jumps across 0/360)
    ax_wd = axes[4]
    ax_wd.clear()
    wd_valid = df["wd"].dropna()
    ax_wd.scatter(wd_valid.index, wd_valid.values, s=2, color="#9467BD", alpha=0.6)
    ax_wd.set_ylim(0, 360)
    ax_wd.set_yticks([0, 90, 180, 270, 360])
    ax_wd.set_yticklabels(["N", "E", "S", "O", "N"], fontsize=7)
    ax_wd.set_ylabel("Dir. Viento (°)", fontsize=8, labelpad=4)
    ax_wd.grid(True, alpha=0.25, linewidth=0.5)
    ax_wd.margins(x=0.01)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    axes[-1].xaxis.set_major_locator(mdates.DayLocator())
    plt.setp(axes[-1].get_xticklabels(), rotation=30, ha="right", fontsize=8)

    fig.suptitle("Comportamiento de variables meteorológicas", fontsize=10, fontweight="bold")

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# Gráfica 2 — aggregate windrose
# ---------------------------------------------------------------------------

def figure_windrose_aggregate(df: pd.DataFrame, output_path: str) -> str:
    """Save the aggregate windrose and return the file path."""
    valid = df[["ws", "wd"]].dropna()
    if valid.empty:
        _save_empty_fig(output_path, "Sin datos de viento disponibles")
        return output_path

    fig = plt.figure(figsize=(7, 7))
    ax = WindroseAxes.from_ax(fig=fig)
    ax.bar(valid["wd"], valid["ws"], normed=True, opening=0.8, edgecolor="white", nsector=16)
    ax.set_legend(title="Vel. (m/s)", loc="lower right")
    ax.set_title("Rosa de Vientos — Período completo", fontsize=10, fontweight="bold", pad=14)

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# Gráfica 3 — daily windrose grid
# ---------------------------------------------------------------------------

def figure_windrose_daily(df: pd.DataFrame, output_path: str) -> str:
    """Save a grid of daily windroses and return the file path."""
    dates = sorted(set(df.index.date))
    n = len(dates)
    ncols = 4
    nrows = math.ceil(n / ncols)

    margin = 0.04
    w_cell = (1.0 - margin * (ncols + 1)) / ncols
    h_cell = (1.0 - margin * (nrows + 1)) / nrows

    fig = plt.figure(figsize=(4 * ncols, 4.2 * nrows))

    for i, date in enumerate(dates):
        row = i // ncols
        col = i % ncols
        left = margin + col * (w_cell + margin)
        bottom = 1.0 - margin - (row + 1) * h_cell - row * margin

        rect = [left, bottom, w_cell, h_cell]
        day_df = df[df.index.date == date][["ws", "wd"]].dropna()

        ax = WindroseAxes(fig, rect)
        fig.add_axes(ax)

        if len(day_df) >= 3:
            ax.bar(day_df["wd"], day_df["ws"], normed=True, opening=0.8,
                   edgecolor="white", nsector=16)
        else:
            ax.text(0.5, 0.5, "N/D", ha="center", va="center",
                    transform=ax.transAxes, fontsize=10, color="gray")

        ax.set_title(str(date), fontsize=8.5, pad=3)

    fig.suptitle("Rosa de Vientos — Distribución diaria", fontsize=11,
                 fontweight="bold", y=1.002)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# Descriptive text generation
# ---------------------------------------------------------------------------

def generate_text(df: pd.DataFrame) -> dict[str, str]:
    """Return auto-generated Spanish narrative for each meteorological variable."""
    start = df.index[0]
    end = df.index[-1]
    period = f"{_es_date(start.date())} al {_es_date(end.date())}"

    # Temperature
    t = df["temp"].dropna()
    t_mean, t_max, t_min = t.mean(), t.max(), t.min()
    t_max_dt = df["temp"].idxmax()
    t_min_dt = df["temp"].idxmin()
    text_temp = (
        f"Durante el período evaluado ({period}), la temperatura del aire registró "
        f"un promedio de {t_mean:.1f}°C. El valor máximo fue de {t_max:.1f}°C, "
        f"registrado el {t_max_dt.strftime('%d/%m/%Y a las %H:%M')}, mientras que la "
        f"temperatura mínima fue de {t_min:.1f}°C el "
        f"{t_min_dt.strftime('%d/%m/%Y a las %H:%M')}. La amplitud térmica diaria "
        f"({t_max - t_min:.1f}°C) es característica del régimen climático de la zona de estudio."
    )

    # Precipitation
    rain_daily = df["rain"].fillna(0).groupby(df.index.date).sum()
    r_total = rain_daily.sum()
    n_rain_days = (rain_daily > 0).sum()
    r_max = rain_daily.max()
    r_max_date = rain_daily.idxmax()
    if n_rain_days == 0:
        text_prec = (
            f"No se registró precipitación durante el período evaluado ({period}). "
            f"Las condiciones se mantuvieron secas a lo largo del monitoreo."
        )
    else:
        text_prec = (
            f"La precipitación total acumulada durante el período ({period}) fue de "
            f"{r_total:.1f} mm, distribuida en {n_rain_days} día(s) con lluvia. "
            f"El día de mayor precipitación fue el {_es_date(r_max_date)}, con "
            f"{r_max:.1f} mm acumulados."
        )

    # Humidity
    h = df["hum"].dropna()
    h_mean, h_max, h_min = h.mean(), h.max(), h.min()
    text_hum = (
        f"La humedad relativa promedio durante el período fue de {h_mean:.1f}%, con "
        f"valores que oscilaron entre {h_min:.1f}% y {h_max:.1f}%. "
        f"Las condiciones de humedad son consistentes con el régimen hidrológico "
        f"de la región, influenciadas por los eventos de precipitación registrados."
    )

    # Wind
    ws = df["ws"].dropna()
    ws_mean, ws_max = ws.mean(), ws.max()
    ws_max_dt = df["ws"].idxmax()
    dir_prev = _prevailing_direction(df["wd"])
    text_viento = (
        f"La velocidad del viento presentó un promedio de {ws_mean:.1f} m/s durante "
        f"el período evaluado, con un máximo puntual de {ws_max:.1f} m/s registrado "
        f"el {ws_max_dt.strftime('%d/%m/%Y a las %H:%M')}. La dirección de viento "
        f"predominante fue del {dir_prev}, lo cual tiene implicaciones directas en "
        f"la dispersión de contaminantes en el área de influencia del proyecto."
    )

    return {
        "temperatura": text_temp,
        "precipitacion": text_prec,
        "humedad_relativa": text_hum,
        "viento": text_viento,
    }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _save_empty_fig(output_path: str, message: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=12, color="gray")
    ax.axis("off")
    fig.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# HTML report assembler
# ---------------------------------------------------------------------------

def _img_b64(path: str) -> str:
    """Return a base64 data URI for a PNG file."""
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def build_report_html(
    table_html: str,
    texts: dict,
    fig_timeseries: str,
    fig_windrose_aggregate: str,
    fig_windrose_daily: str,
    period: str,
) -> str:
    """Assemble the full Sección 5 — Meteorología as a self-contained HTML document."""
    ts = _img_b64(fig_timeseries)
    wr_agg = _img_b64(fig_windrose_aggregate)
    wr_day = _img_b64(fig_windrose_daily)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>5. Meteorología</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: Arial, sans-serif;
    font-size: 10pt;
    color: #000;
    max-width: 21cm;
    margin: 0 auto;
    padding: 2.5cm 2cm;
    line-height: 1.5;
  }}
  h1 {{
    font-size: 13pt;
    font-weight: bold;
    color: #1F497D;
    text-transform: uppercase;
    border-bottom: 2px solid #1F497D;
    padding-bottom: 5px;
    margin: 1.8em 0 0.8em;
  }}
  h2 {{
    font-size: 11pt;
    font-weight: bold;
    color: #1F497D;
    margin: 1.4em 0 0.5em;
  }}
  p {{
    text-align: justify;
    margin-bottom: 0.6em;
  }}
  .caption {{
    font-size: 9pt;
    font-weight: bold;
    margin-bottom: 5px;
  }}
  .caption-fig {{
    font-size: 9pt;
    font-weight: bold;
    text-align: center;
    margin-top: 6px;
  }}
  figure {{
    margin: 1.2em 0 1.6em;
    text-align: center;
    page-break-inside: avoid;
  }}
  img {{
    max-width: 100%;
    height: auto;
  }}
  img.windrose-agg {{
    max-width: 55%;
  }}
  .table-wrap {{
    margin: 0.5em 0 1.6em;
    overflow-x: auto;
  }}
</style>
</head>
<body>

<h1>5. Meteorología</h1>

<p>
Dado que los factores meteorológicos determinan el transporte y dispersión de los contaminantes en la atmósfera, los
parámetros meteorológicos con los cuales se debe contar como mínimo son: velocidad y dirección del viento con el
fin de establecer la dirección de los contaminantes y su dispersión en la atmósfera así como la temperatura ya que
ésta puede influir en la generación de sustancias; otros parámetros como precipitación, nubosidad, humedad y
radiación solar completan el panorama de los fenómenos meteorológicos. Con la anterior información se deben
establecer las condiciones predominantes de velocidad y dirección del viento con el fin de establecer la dirección de
los contaminantes y el grado de dispersión de estos. Los datos de meteorología específicos del sitio corresponden a
los datos de una estación meteorológica en el lugar o los datos derivados de modelos. Se podrán realizar el análisis
a partir de estaciones meteorológicas existentes en la zona siempre y cuando los datos sean representativos.</p>

<p>
En la tabla que se presenta a continuación, se muestra el promedio diario de cada una de las variables meteorológicas
monitoreadas, con una escala de colores que va desde el verde (bajo) pasando por el amarillo (medio) hasta el color
rojo (alto), el cual permite identificar de manera rápida la relación entre el dato diario, respecto a los demás días de
medición.
</p>

<p class="caption">Tabla 16. Resumen estadístico diario de variables meteorológicas — período {period}</p>
<div class="table-wrap">
{table_html}
</div>

<figure>
  <img src="{ts}" alt="Variables meteorológicas">
  <p class="caption-fig">Gráfica 1. Comportamiento de las variables meteorológicas durante el período de evaluación</p>
</figure>

<h2>5.1 Temperatura</h2>
<p>La temperatura superficial se refiere esencialmente a la temperatura del aire libre o temperatura ambiental cerca de
la superficie de la tierra. La superficie terrestre recibe energía proveniente del Sol, en forma de radiación solar emitida
en onda corta. A su vez, la Tierra, con su propia atmósfera, refleja alrededor del 55% de la radiación incidente y
absorbe el 45% restante, convirtiéndose, ese porcentaje en calor. Por otra parte, la tierra irradia energía, en onda
larga, conocida como radiación terrestre. Por lo tanto, el calor ganado de la radiación incidente debe ser igual al calor
perdido mediante la radiación terrestre. (Senamhi, 2008). La cantidad de energía solar recibida, en cualquier región
del planeta, varía con la hora del día, con la estación del año y con la latitud. Estas diferencias de radiación originan
las variaciones de temperatura. Por otro lado, la temperatura puede variar debido a la distribución de distintos tipos
de superficies y en función de la altura.</p>
<p>{texts["temperatura"]}</p>

<h2>5.2 Precipitación</h2>
<p>La precipitación es cualquier forma de hidrometeoro, conformado de partículas acuosas de forma sólida o líquida que
caen de las nubes y llegan al suelo. Existen varios tipos de precipitación dependiendo de la cantidad o forma en que
caen las partículas, el diámetro se halla generalmente comprendido entre 0,5 y 7 mm, (1 mm de precipitación es la
lámina que alcanzaría un litro de agua sobre una superficie de un metro cuadrado, sin que se evapore o percole), y
caen a una velocidad del orden de los 3 m/s. Dependiendo del tamaño de las gotas que lleguen al suelo y de cómo
caigan existen distintos tipos de precipitación líquida: llovizna (gotas pequeñas que caen uniformemente), chubasco
(gotas de mayor tamaño y que caen de forma violenta e intensa).</p>
<p>{texts["precipitacion"]}</p>

<h2>5.3 Humedad Relativa</h2>
<p>La humedad de una masa de aire no depende de la cantidad de agua por metro cúbico que contenga, eso es la
humedad absoluta y obedece a la evaporación, sino de la capacidad del aire para absorber agua. Esta capacidad
depende de la temperatura del aire, puesto que esta absorción de agua necesita energía calorífica. A esta capacidad
se le llama humedad relativa y se mide en tantos por ciento. Para una misma humedad absoluta, la humedad relativa
aumenta cuando desciende la temperatura. Para el clima lo más interesante es la humedad relativa ya que una masa
de aire saturada, o cercana a la saturación,</p>
<p>{texts["humedad_relativa"]}</p>

<h2>5.4 Viento</h2>
<p>El comportamiento de los vientos en Colombia responde al flujo de los alisios del Noreste y Sudeste, los cuales
confluyen en la región tropical formando una zona de baja presión (ZCIT), que al desplazarse sobre el territorio debido
al cambio relativo de la incidencia solar sobre la tierra provoca las temporadas de lluvia en el país. De vez en cuando
la circulación de los vientos alisios se ve trastornada por anomalías en el balance de energía provocando serios
disturbios en la distribución espacial y temporal de las lluvias, tal es el caso del fenómeno del Niño. Otro aspecto que
influye depende de las condiciones orográficas; las diferencias horizontales de temperatura en una montaña producen
alteraciones locales del viento que genéricamente se llaman brisas. La brisa terrestre, llamada circulación valle-
montaña, montaña-valle, se debe a diferencias de temperatura entre las montañas y el aire libre que las rodea, en la
mañana se presenta una brisa soplando junto al suelo desde los valles y llanuras hacia las laderas que están
recibiendo el Sol (solana), remontándolas. De noche desciende una brisa desde las montañas a los valles y llanuras</p>
<p>{texts["viento"]}</p>

<figure>
  <img class="windrose-agg" src="{wr_agg}" alt="Rosa de vientos — período completo">
  <p class="caption-fig">Gráfica 2. Rosa de vientos — período completo</p>
</figure>

<figure>
  <img src="{wr_day}" alt="Rosa de vientos — distribución diaria">
  <p class="caption-fig">Gráfica 3. Rosa de vientos — distribución diaria</p>
</figure>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_report(file_path: str, output_dir: str) -> dict:
    """Generate the Meteorología section as a complete self-contained HTML report.

    Also saves the individual figures as PNGs in output_dir.

    Returns a dict with keys:
    - report_path: str — path to the assembled HTML report (Sección 5 completa)
    - table_html: str — raw HTML for the color-coded daily summary table
    - figure_timeseries: str — path to 6-panel time-series PNG (Gráfica 1)
    - figure_windrose_aggregate: str — path to aggregate windrose PNG (Gráfica 2)
    - figure_windrose_daily: str — path to daily windrose grid PNG (Gráfica 3)
    - texts: dict — keys temperatura, precipitacion, humedad_relativa, viento
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = load_meteo(file_path)

    table_html = daily_summary_table(df)
    fig_ts = figure_timeseries(df, str(out / "fig_timeseries.png"))
    fig_wr_agg = figure_windrose_aggregate(df, str(out / "fig_windrose_aggregate.png"))
    fig_wr_day = figure_windrose_daily(df, str(out / "fig_windrose_daily.png"))
    texts = generate_text(df)

    period = (
        f"{_es_date(df.index[0].date())} al {_es_date(df.index[-1].date())}"
    )
    report_html = build_report_html(
        table_html=table_html,
        texts=texts,
        fig_timeseries=fig_ts,
        fig_windrose_aggregate=fig_wr_agg,
        fig_windrose_daily=fig_wr_day,
        period=period,
    )

    report_path = out / "seccion5_meteorologia.html"
    report_path.write_text(report_html, encoding="utf-8")

    return {
        "report_path": str(report_path),
        "table_html": table_html,
        "figure_timeseries": fig_ts,
        "figure_windrose_aggregate": fig_wr_agg,
        "figure_windrose_daily": fig_wr_day,
        "texts": texts,
    }
