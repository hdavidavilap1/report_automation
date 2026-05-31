"""
Section 8 — Conclusiones y Recomendaciones
Auto-generates Spanish narrative from the outputs of the resultados, ICA, and
meteorología skills, following the structure of Resolución 2254 de 2017 reports.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

# ── Spanish month names ────────────────────────────────────────────────────────
_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

# ICA category order for narrative ordering
_CATEGORY_ORDER = [
    "Buena",
    "Aceptable",
    "Dañina a grupos sensibles",
    "Dañina a la salud",
    "Muy dañina a la salud",
    "Peligrosa",
]

# Norm display strings (must match resultados NORMS)
_NORM_DISPLAY = {
    "pm10": {"24h": "75 µg/m³ para promedio de 24 horas"},
    "pm25": {"24h": "37 µg/m³ para promedio de 24 horas"},
    "so2":  {"24h": "50 µg/m³ para promedio de 24 horas", "1h": "100 µg/m³ para 1 hora"},
    "no2":  {"1h":  "200 µg/m³ para 1 hora"},
    "co":   {"1h":  "35.000 µg/m³ para 1 hora", "8h": "10.000 µg/m³ para promedio de 8 horas"},
    "o3":   {"8h":  "100 µg/m³ para promedio de 8 horas"},
}

_POLL_LABEL = {
    "pm10": "Material Particulado PM₁₀",
    "pm25": "Material Particulado PM₂.₅",
    "so2":  "Dióxido de Azufre SO₂",
    "no2":  "Dióxido de Nitrógeno NO₂",
    "co":   "Monóxido de Carbono CO",
    "o3":   "Ozono troposférico O₃",
}

_POLL_ORDER = ["pm10", "pm25", "so2", "no2", "co", "o3"]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _es_date(date_str: str) -> str:
    d = _dt.date.fromisoformat(date_str)
    return f"{d.day} de {_MONTHS_ES[d.month]} de {d.year}"


def _sta_label(sta: str, stations: list[str]) -> str:
    idx = sorted(stations).index(sta)
    return f"CA-{idx + 1}"


def _fmt(value: float) -> str:
    return f"{value:,.2f}"


# ─────────────────────────────────────────────────────────────────────────────
# Per-pollutant bullet generators
# ─────────────────────────────────────────────────────────────────────────────

def _bullet_pm(pollutant: str, stats: dict, stations: list[str]) -> str:
    label = _POLL_LABEL[pollutant]
    norm_str = _NORM_DISPLAY[pollutant]["24h"]
    pst = stats.get(pollutant, {})
    max24 = pst.get("max_24h")
    exceeds = pst.get("exceeds_24h", False)

    if exceeds:
        compliance = (
            f"presentaron superaciones del nivel máximo permisible de {norm_str} "
            f"establecido en la Resolución 2254 de 2017 del MADS"
        )
    else:
        compliance = (
            f"presentaron pleno cumplimiento con el nivel máximo permisible de {norm_str} "
            f"establecido en la Resolución 2254 de 2017 del MADS "
            f"(Ministerio de Ambiente y Desarrollo Sostenible)"
        )

    tail = ""
    if max24:
        date_str = _es_date(max24["date"])
        sta_name = _sta_label(max24["station"], stations)
        tail = (
            f" La concentración diaria más alta registrada fue de "
            f"<strong>{_fmt(max24['value'])} µg/m³</strong> en la estación "
            f"<strong>{sta_name}</strong> el {date_str}."
        )

    return (
        f"Las concentraciones medidas del contaminante criterio {label} {compliance}.{tail}"
    )


def _bullet_so2(stats: dict, stations: list[str]) -> str:
    pst = stats.get("so2", {})
    max24 = pst.get("max_24h")
    max1h = pst.get("max_1h")
    exceeds_24h = pst.get("exceeds_24h", False)
    exceeds_1h = pst.get("exceeds_1h", False)
    exceeds = exceeds_24h or exceeds_1h

    if exceeds:
        compliance = (
            "presentaron superaciones de los niveles máximos permisibles "
            "de 50 µg/m³ para promedio de 24 horas y/o 100 µg/m³ para 1 hora "
            "establecidos en la Resolución 2254 de 2017 del MADS"
        )
    else:
        compliance = (
            "presentaron pleno cumplimiento con los niveles máximos permisibles "
            "de 50 µg/m³ para promedio de 24 horas y 100 µg/m³ para 1 hora "
            "establecidos en la Resolución 2254 de 2017 del MADS "
            "(Ministerio de Ambiente y Desarrollo Sostenible)"
        )

    parts = [
        f"Las concentraciones medidas del contaminante criterio {_POLL_LABEL['so2']} {compliance}."
    ]
    if max24:
        parts.append(
            f" La concentración diaria máxima fue de "
            f"<strong>{_fmt(max24['value'])} µg/m³</strong> en la estación "
            f"<strong>{_sta_label(max24['station'], stations)}</strong> "
            f"el {_es_date(max24['date'])}."
        )
    if max1h:
        parts.append(
            f" La concentración horaria máxima registrada fue de "
            f"<strong>{_fmt(max1h['value'])} µg/m³</strong> en la estación "
            f"<strong>{_sta_label(max1h['station'], stations)}</strong> "
            f"el {_es_date(max1h['date'])} a las {max1h['hour']}."
        )
    return "".join(parts)


def _bullet_no2(stats: dict, stations: list[str]) -> str:
    pst = stats.get("no2", {})
    max1h = pst.get("max_1h")
    exceeds = pst.get("exceeds_1h", False)

    if exceeds:
        compliance = (
            "presentaron superaciones del nivel máximo permisible de 200 µg/m³ para 1 hora "
            "establecido en la Resolución 2254 de 2017 del MADS"
        )
    else:
        compliance = (
            "presentaron pleno cumplimiento con el nivel máximo permisible de 200 µg/m³ para 1 hora "
            "establecido en la Resolución 2254 de 2017 del MADS "
            "(Ministerio de Ambiente y Desarrollo Sostenible)"
        )

    tail = ""
    if max1h:
        tail = (
            f" La concentración horaria más alta registrada fue de "
            f"<strong>{_fmt(max1h['value'])} µg/m³</strong> en la estación "
            f"<strong>{_sta_label(max1h['station'], stations)}</strong> "
            f"el {_es_date(max1h['date'])} a las {max1h['hour']}."
        )
    return (
        f"Las concentraciones medidas del contaminante criterio {_POLL_LABEL['no2']} {compliance}.{tail}"
    )


def _bullet_co(stats: dict, stations: list[str]) -> str:
    pst = stats.get("co", {})
    max8h = pst.get("max_8h")
    exceeds = pst.get("exceeds_8h", False)

    if exceeds:
        compliance = (
            "presentaron superaciones de los niveles máximos permisibles "
            "de 35.000 µg/m³ para 1 hora y/o 10.000 µg/m³ para promedio de 8 horas "
            "establecidos en la Resolución 2254 de 2017 del MADS"
        )
    else:
        compliance = (
            "presentaron pleno cumplimiento con los niveles máximos permisibles "
            "de 35.000 µg/m³ para 1 hora y 10.000 µg/m³ para promedio de 8 horas "
            "establecidos en la Resolución 2254 de 2017 del MADS "
            "(Ministerio de Ambiente y Desarrollo Sostenible)"
        )

    tail = ""
    if max8h:
        tail = (
            f" La concentración máxima de 8 horas registrada fue de "
            f"<strong>{_fmt(max8h['value'])} µg/m³</strong> en la estación "
            f"<strong>{_sta_label(max8h['station'], stations)}</strong> "
            f"el {_es_date(max8h['date'])}."
        )
    return (
        f"Las concentraciones medidas del contaminante criterio {_POLL_LABEL['co']} {compliance}.{tail}"
    )


def _bullet_o3(stats: dict, stations: list[str]) -> str:
    pst = stats.get("o3", {})
    max8h = pst.get("max_8h")
    exceeds = pst.get("exceeds_8h", False)

    if exceeds:
        compliance = (
            "presentaron superaciones del nivel máximo permisible de 100 µg/m³ "
            "para promedio de 8 horas establecido en la Resolución 2254 de 2017 del MADS"
        )
    else:
        compliance = (
            "presentaron pleno cumplimiento con el nivel máximo permisible de 100 µg/m³ "
            "para promedio de 8 horas establecido en la Resolución 2254 de 2017 del MADS "
            "(Ministerio de Ambiente y Desarrollo Sostenible)"
        )

    tail = ""
    if max8h:
        tail = (
            f" La concentración máxima de 8 horas registrada fue de "
            f"<strong>{_fmt(max8h['value'])} µg/m³</strong> en la estación "
            f"<strong>{_sta_label(max8h['station'], stations)}</strong> "
            f"el {_es_date(max8h['date'])} a las {max8h['hour']}."
        )
    return (
        f"Las concentraciones medidas del contaminante criterio {_POLL_LABEL['o3']} {compliance}.{tail}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ICA bullet
# ─────────────────────────────────────────────────────────────────────────────

def _bullet_ica(ica_result: dict, stations: list[str]) -> str:
    ica_cats = ica_result.get("ica_categories", {})

    # For each pollutant, find which stations had non-"Buena" days
    poll_labels = {
        "pm10": "PM₁₀",
        "pm25": "PM₂.₅",
        "so2":  "SO₂",
        "no2":  "NO₂",
        "co":   "CO",
        "o3":   "O₃",
    }

    # Identify pollutants that stayed "Buena" for all stations
    good_only: list[str] = []
    exceptions: list[str] = []

    for p in _POLL_ORDER:
        all_good = True
        exception_parts: list[str] = []
        for sta in sorted(stations):
            sta_cats = ica_cats.get(sta, {}).get(p, {})
            non_good = {cat: cnt for cat, cnt in sta_cats.items() if cat != "Buena"}
            if non_good:
                all_good = False
                sta_name = _sta_label(sta, stations)
                cat_strs = []
                for cat in _CATEGORY_ORDER:
                    if cat in non_good and cat != "Buena":
                        n = non_good[cat]
                        cat_strs.append(f"categoría \"{cat}\" {n} día(s) en {sta_name}")
                exception_parts.extend(cat_strs)

        if all_good:
            good_only.append(poll_labels.get(p, p.upper()))
        else:
            label = poll_labels.get(p, p.upper())
            exceptions.append(f"Para {label}: " + ", ".join(exception_parts) + ".")

    parts: list[str] = []
    parts.append(
        "El Índice de Calidad del Aire (ICA) fue calculado para los contaminantes "
        "criterio monitoreados durante el período de evaluación conforme a la "
        "metodología de la EPA adaptada a los puntos de corte de la Resolución 2254 de 2017."
    )

    if good_only:
        parts.append(
            f" Los contaminantes {', '.join(good_only)} presentaron categoría "
            f"<strong>\"Buena\"</strong> en todas las estaciones de monitoreo durante "
            f"todo el período de evaluación."
        )

    if exceptions:
        parts.append(" " + " ".join(exceptions))

    if not good_only and not exceptions:
        parts.append(
            " No se pudo calcular el ICA compuesto por falta de datos suficientes."
        )

    return "".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# HTML assembler
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
body{font-family:Arial,Helvetica,sans-serif;font-size:10pt;
     margin:2cm 2.5cm;color:#222;line-height:1.6}
h1{font-size:14pt;color:#1F4E79;border-bottom:2px solid #1F4E79;
   padding-bottom:4px;margin-top:1.5em}
ul{margin:0.8em 0 1em 1.5em}
li{margin-bottom:0.7em}
"""


def _build_html(bullets: list[str], period_start: str, period_end: str, location: str) -> str:
    period = f"{_es_date(period_start)} al {_es_date(period_end)}"
    opening = (
        "Teniendo en cuenta los resultados referentes a la evaluación de la campaña de "
        "monitoreo de calidad del aire para los contaminantes criterio Material Particulado "
        "PM<sub>10</sub> &amp; PM<sub>2.5</sub>, Dióxido de Azufre SO<sub>2</sub>, "
        "Dióxido de Nitrógeno NO<sub>2</sub>, Monóxido de Carbono CO y Ozono O<sub>3</sub>, "
        f"realizado entre el {period}, con mediciones diarias, en el área de influencia de "
        f"<em>{location}</em>, se puede establecer que:"
    )
    li_items = "\n".join(f"  <li>{b}</li>" for b in bullets)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Sección 8 — Conclusiones y Recomendaciones</title>
<style>{_CSS}</style>
</head>
<body>
<h1>8. CONCLUSIONES Y RECOMENDACIONES</h1>
<p>{opening}</p>
<ul>
{li_items}
</ul>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(
    resultados_result: dict,
    ica_result: dict,
    meteo_result: dict,
    output_dir: str,
    location: str = "la zona de estudio",
) -> dict:
    """Generate Section 8 — Conclusiones y Recomendaciones.

    Parameters
    ----------
    resultados_result:
        Return dict from ``skills.resultados_analisis.generate_report``.
        Must include ``pollutant_stats``, ``period_start``, ``period_end``,
        and ``stations`` keys (present in v2+ of that skill).
    ica_result:
        Return dict from ``skills.ica.generate_report``.
        Must include ``ica_categories`` key.
    meteo_result:
        Return dict from ``skills.meteorologia.generate_report``.
        (Currently used for context; may drive meteorological summary in future.)
    output_dir:
        Directory where the HTML report will be written.
    location:
        Human-readable name of the monitoring campaign location, e.g.
        "la Planta de Beneficio Minero El Diamante".

    Returns
    -------
    dict with keys:
        ``report_path``   — absolute path to the generated HTML file
        ``bullets``       — list of narrative strings (one per pollutant + ICA)
        ``period_start``  — ISO date string
        ``period_end``    — ISO date string
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    stats = resultados_result.get("pollutant_stats", {})
    period_start: str = resultados_result.get("period_start", "")
    period_end: str = resultados_result.get("period_end", "")
    stations: list[str] = resultados_result.get("stations", [])

    bullets: list[str] = [
        _bullet_pm("pm10", stats, stations),
        _bullet_pm("pm25", stats, stations),
        _bullet_so2(stats, stations),
        _bullet_no2(stats, stations),
        _bullet_co(stats, stations),
        _bullet_o3(stats, stations),
        _bullet_ica(ica_result, stations),
    ]

    html = _build_html(bullets, period_start, period_end, location)
    report_path = out / "seccion8_conclusiones.html"
    report_path.write_text(html, encoding="utf-8")

    return {
        "report_path": str(report_path),
        "bullets": bullets,
        "period_start": period_start,
        "period_end": period_end,
    }