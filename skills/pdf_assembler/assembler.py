"""
PDF Assembler — Phase 3
Merges the four section HTML reports into a single paginated PDF.

Rendering priority:
  1. Chrome / Chromium headless  (preferred — full CSS, base64 images, no extra deps)
  2. WeasyPrint                  (when pango is installed: `pip install weasyprint`)
  3. HTML only                   (merged HTML saved; user prints from browser)
"""

from __future__ import annotations

import datetime as _dt
import re
import subprocess
from pathlib import Path
from shutil import which

# ─────────────────────────────────────────────────────────────────────────────
# Spanish month names
# ─────────────────────────────────────────────────────────────────────────────

_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def _es_date(date_str: str) -> str:
    if not date_str:
        return ""
    d = _dt.date.fromisoformat(date_str)
    return f"{d.day} de {_MONTHS_ES[d.month]} de {d.year}"


# ─────────────────────────────────────────────────────────────────────────────
# HTML extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_body(html_path: str) -> str:
    text = Path(html_path).read_text(encoding="utf-8")
    m = re.search(r"<body[^>]*>(.*?)</body>", text, re.DOTALL)
    return m.group(1).strip() if m else text


def _extract_styles(html_path: str) -> str:
    text = Path(html_path).read_text(encoding="utf-8")
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.DOTALL))


# ─────────────────────────────────────────────────────────────────────────────
# Cover page
# ─────────────────────────────────────────────────────────────────────────────

def _cover_html(
    title: str,
    subtitle: str,
    period_start: str,
    period_end: str,
    location: str,
    company_name: str,
    report_number: str,
) -> str:
    period_str = ""
    if period_start and period_end:
        period_str = f"{_es_date(period_start)} al {_es_date(period_end)}"
    elif period_start:
        period_str = _es_date(period_start)

    today = _dt.date.today()
    today_str = f"{today.day} de {_MONTHS_ES[today.month]} de {today.year}"

    rows = []
    if period_str:
        rows.append(
            f'<p style="font-size:12pt;margin:8px 0">'
            f'<strong>Período:</strong> {period_str}</p>'
        )
    if location:
        rows.append(
            f'<p style="font-size:12pt;margin:8px 0">'
            f'<strong>Ubicación:</strong> {location}</p>'
        )
    if company_name:
        rows.append(
            f'<p style="font-size:11pt;color:#555;margin:8px 0">{company_name}</p>'
        )
    if report_number:
        rows.append(
            f'<p style="font-size:11pt;color:#555;margin:8px 0">'
            f'Ref: {report_number}</p>'
        )
    rows.append(
        f'<p style="font-size:10pt;color:#888;margin:24px 0 0">{today_str}</p>'
    )

    return f"""
<div style="
  width:100%;height:100vh;
  display:flex;flex-direction:column;
  justify-content:center;align-items:center;
  text-align:center;
  page-break-after:always;
">
  <div style="
    border-top:4px solid #1F4E79;
    border-bottom:4px solid #1F4E79;
    padding:40px 60px;
    max-width:600px;
  ">
    <h1 style="
      font-size:22pt;color:#1F4E79;
      margin:0 0 12px;letter-spacing:1px;
    ">{title}</h1>
    <h2 style="
      font-size:14pt;color:#2E75B6;
      font-weight:normal;margin:0 0 32px;
    ">{subtitle}</h2>
    {"".join(rows)}
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Merged HTML assembler
# ─────────────────────────────────────────────────────────────────────────────

_PRINT_CSS = """
@page {
  size: letter;
  margin: 1.8cm 1.8cm 2cm 1.8cm;
}
@media print {
  .section-break { page-break-before: always; }
  h1, h2, h3 { page-break-after: avoid; }
  figure, .table-wrap { page-break-inside: avoid; }
  tr { page-break-inside: avoid; }
}
body {
  font-family: Arial, Helvetica, sans-serif;
  font-size: 10pt;
  line-height: 1.6;
  color: #222;
  margin: 0;
  padding: 0;
}
img { max-width: 100%; height: auto; }
table { border-collapse: collapse; }
"""

# Applied AFTER extracted section styles to override per-section body constraints.
_PDF_OVERRIDES = """
body {
  max-width: none !important;
  width: 100% !important;
  margin: 0 !important;
  padding: 0 !important;
}
.section-break {
  max-width: none !important;
  width: 100% !important;
  box-sizing: border-box;
}
"""


def _build_merged_html(
    cover: str | None,
    sections: list[tuple[str, str]],  # [(section_id, body_html), ...]
    extra_styles: str = "",
) -> str:
    parts = []
    if cover:
        parts.append(f'<div id="cover">{cover}</div>')
    for sid, body in sections:
        parts.append(f'<div id="{sid}" class="section-break">{body}</div>')

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
{_PRINT_CSS}
{extra_styles}
{_PDF_OVERRIDES}
</style>
</head>
<body>
{"".join(parts)}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# PDF renderers
# ─────────────────────────────────────────────────────────────────────────────

_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
    "google-chrome-stable",
]


def _find_chrome() -> str | None:
    for c in _CHROME_PATHS:
        p = Path(c)
        if p.exists():
            return str(p)
        found = which(c)
        if found:
            return found
    return None


def _render_chrome(html_path: str, pdf_path: str, chrome: str) -> None:
    result = subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_path}",
            html_path,
        ],
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace")
        raise RuntimeError(f"Chrome exit {result.returncode}: {err[:400]}")


def _render_weasyprint(html_path: str, pdf_path: str) -> None:
    import weasyprint  # noqa: PLC0415
    weasyprint.HTML(filename=html_path).write_pdf(pdf_path)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(
    output_dir: str,
    portada_html: str | None = None,
    meteo_html: str | None = None,
    resultados_html: str | None = None,
    ica_html: str | None = None,
    conclusiones_html: str | None = None,
    title: str = "INFORME DE CALIDAD DEL AIRE",
    subtitle: str = "Campaña de Monitoreo de Calidad del Aire",
    company_name: str = "",
    report_number: str = "",
    period_start: str = "",
    period_end: str = "",
    location: str = "",
) -> dict:
    """Assemble all section HTML reports into a single PDF.

    Parameters
    ----------
    output_dir:
        Directory where the assembled HTML and PDF will be saved.
    portada_html:
        Path to ``seccion1_4_portada_generalidades.html`` (from ``generate_portada``).
        Already includes its own cover page, control page, table of contents,
        lists, glossary and Sections 1–4 — when provided, the auto-generated
        cover page below is skipped in favour of this one.
    meteo_html:
        Path to ``seccion5_meteorologia.html`` (from ``generate_meteorologia``).
    resultados_html:
        Path to ``seccion6_resultados.html`` (from ``generate_resultados``).
    ica_html:
        Path to ``seccion7_ica.html`` (from ``generate_ica``).
    conclusiones_html:
        Path to ``seccion8_conclusiones.html`` (from ``generate_conclusiones``).
    title:
        Main title on the cover page.
    subtitle:
        Subtitle on the cover page.
    company_name:
        Company / contractor name for the cover page.
    report_number:
        Report reference number (e.g. ``"CA.25420.I1"``).
    period_start / period_end:
        ISO date strings for the monitoring period shown on the cover page.
    location:
        Monitoring campaign location name shown on the cover page.

    Returns
    -------
    dict with keys:
        ``pdf_path``          — absolute path to the PDF (``None`` if rendering failed)
        ``html_path``         — absolute path to the merged HTML (always present)
        ``renderer``          — ``"chrome"``, ``"weasyprint"``, or ``"html_only"``
        ``sections_included`` — list of section IDs that were included
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # ── collect sections ──────────────────────────────────────────────────────
    section_map = [
        ("section-portada", portada_html,  "Portada, Generalidades y Secciones 1–4"),
        ("section-5",       meteo_html,       "Sección 5 — Meteorología"),
        ("section-6",       resultados_html,  "Sección 6 — Resultados del Análisis"),
        ("section-7",       ica_html,         "Sección 7 — ICA"),
        ("section-8",       conclusiones_html,"Sección 8 — Conclusiones"),
    ]

    sections: list[tuple[str, str]] = []
    extra_styles_parts: list[str] = []
    sections_included: list[str] = []

    for sid, path, label in section_map:
        if not path:
            continue
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"{label}: file not found at {path}")
        sections.append((sid, _extract_body(path)))
        extra_styles_parts.append(_extract_styles(path))
        sections_included.append(sid)

    if not sections:
        raise ValueError("No section HTML files provided.")

    # ── build cover (skipped when portada_html supplies its own) ──────────────
    cover = None
    if not portada_html:
        cover = _cover_html(
            title=title,
            subtitle=subtitle,
            period_start=period_start,
            period_end=period_end,
            location=location,
            company_name=company_name,
            report_number=report_number,
        )

    # ── merge ─────────────────────────────────────────────────────────────────
    merged_html = _build_merged_html(
        cover=cover,
        sections=sections,
        extra_styles="\n".join(extra_styles_parts),
    )
    html_path = out / "informe_completo.html"
    html_path.write_text(merged_html, encoding="utf-8")

    # ── render to PDF ─────────────────────────────────────────────────────────
    pdf_path_str: str | None = None
    renderer = "html_only"

    chrome = _find_chrome()
    if chrome:
        pdf_path = out / "informe_completo.pdf"
        try:
            _render_chrome(str(html_path), str(pdf_path), chrome)
            pdf_path_str = str(pdf_path)
            renderer = "chrome"
        except Exception as e:
            # leave pdf_path_str as None, html_only fallback
            renderer = f"html_only (chrome failed: {e})"
    else:
        try:
            _render_weasyprint(str(html_path), str(out / "informe_completo.pdf"))
            pdf_path_str = str(out / "informe_completo.pdf")
            renderer = "weasyprint"
        except Exception as e:
            renderer = f"html_only (weasyprint failed: {e})"

    return {
        "pdf_path": pdf_path_str,
        "html_path": str(html_path),
        "renderer": renderer,
        "sections_included": sections_included,
    }