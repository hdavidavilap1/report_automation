"""
Air Quality MCP Server — Phase 1: Imputation
"""

import asyncio
import json
import logging
from pathlib import Path

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

from skills.imputation.imputer import ImputationSkill
from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.memoria_raw.memoria_raw import MemoriaRawSkill
from skills.ica.ica import generate_report as ica_generate_report
from skills.meteorologia.meteo import generate_report as meteo_generate_report
from skills.conclusiones.conclusiones import generate_report as conclusiones_generate_report
from skills.pdf_assembler.assembler import generate_report as pdf_generate_report
from skills.portada_generalidades.portada_generalidades import generate_report as portada_generate_report
from skills.resultados_analisis.resultados import generate_report as resultados_generate_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("air-quality-mcp")

app = Server("air-quality-reports")
imputer = ImputationSkill()
extrapolator = ExtrapolationSkill()
memoria_raw = MemoriaRawSkill()


# ─────────────────────────────────────────────────────────
# Tool registry
# ─────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="ingest_excel",
            description=(
                "Reads an Excel file with air quality measurements. "
                "Validates its structure and returns a summary of columns, "
                "date range, and missing-data statistics per column."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the .xlsx or .xls file.",
                    }
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="extrapolate_data",
            description=(
                "Extends a time series before its start (retropolation) and after its "
                "end (forecast) by n_hours, using a hot-deck strategy: for each new hour, "
                "draws a reference value from real measurements at the same hour-of-day "
                "and adds std-based perturbation (circular for wind direction). "
                "Saves the extended dataset as a parquet file next to the input. "
                "Run this before impute_data so any remaining gaps in the extended "
                "range are filled during imputation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the Excel, CSV, or parquet file.",
                    },
                    "n_hours": {
                        "type": "integer",
                        "default": 10,
                        "description": (
                            "Number of hours to extend before the start and after "
                            "the end of the time series."
                        ),
                    },
                    "wind_dir_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Explicit list of wind-direction columns (circular, "
                            "0-360°). If omitted, auto-detected from numeric columns "
                            "with range > 90°."
                        ),
                    },
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="impute_data",
            description=(
                "Fills missing sensor values using the chosen statistical method. "
                "Saves the cleaned dataset as a parquet file next to the original. "
                "Returns imputation statistics and the output path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the Excel or previously imputed parquet file.",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["auto", "mice", "knn", "temporal", "linear"],
                        "default": "auto",
                        "description": (
                            "Imputation method.\n"
                            "• auto     — picks the best method based on % missing\n"
                            "• temporal — time-aware linear interpolation (best for <5% missing)\n"
                            "• knn      — K-Nearest Neighbours (5–30% missing)\n"
                            "• mice     — Multiple Imputation by Chained Equations (>30% missing)\n"
                            "• linear   — simple column-wise linear interpolation"
                        ),
                    },
                    "target_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Specific columns to impute. "
                            "If omitted, all numeric columns are imputed."
                        ),
                    },
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="imputation_report",
            description=(
                "Returns a detailed comparison of missing-data statistics "
                "before and after imputation for a given parquet file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "original_path": {
                        "type": "string",
                        "description": "Path to the original Excel file.",
                    },
                    "imputed_path": {
                        "type": "string",
                        "description": "Path to the imputed parquet file.",
                    },
                },
                "required": ["original_path", "imputed_path"],
            },
        ),
        types.Tool(
            name="reconstruct_memoria",
            description=(
                "Reconstructs a lost APNA-370 raw memory-dump file (`_HA.csv`) from data that "
                "has already gone through extrapolate_data and impute_data, using the "
                "instrument's own Status/Caution/Alarm bit fields to mark which rows are "
                "reconstructed: rows in the real measurement window whose original reading was "
                "missing get Alarm bit 6 ('V') = 1, and the reconstructed calibration row "
                "(first padding-before hour, set to the average of the calibration gas "
                "concentrations) gets Caution bit 32 ('DR') = 1. Intended for data-recovery "
                "cases where the raw memory file genuinely existed but was lost; provenance of "
                "reconstructed rows stays auditable via these flags."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "original_path": {
                        "type": "string",
                        "description": (
                            "Path to the original (pre-imputation) data file — defines the real "
                            "measurement window and which cells were originally missing."
                        ),
                    },
                    "processed_path": {
                        "type": "string",
                        "description": (
                            "Path to the parquet produced by extrapolate_data → impute_data "
                            "(extended range, no NaNs)."
                        ),
                    },
                    "component_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "1-3 column names to map to Component1/2/3 in the raw file, in order."
                        ),
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Path where the reconstructed _HA.csv will be written.",
                    },
                    "station": {
                        "type": "string",
                        "description": "Station to select if the data contains multiple stations.",
                    },
                    "equipment_name": {
                        "type": "string",
                        "default": "Equipment-1:APNA",
                        "description": "Equipment identifier written in the first header line.",
                    },
                    "save_datetime": {
                        "type": "string",
                        "description": (
                            "ISO datetime of the memory download. If omitted, auto-derived as "
                            "last_memory_timestamp + 1h + random(minute, second)."
                        ),
                    },
                    "calibration_component": {
                        "type": "integer",
                        "default": 1,
                        "description": (
                            "1-3, which component_columns entry receives the calibration value "
                            "in the reconstructed calibration row."
                        ),
                    },
                    "calibration_values": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": (
                            "Calibration gas concentrations (ppb) whose average is written to "
                            "the calibration row. Defaults to [400, 300, 200, 100, 0]."
                        ),
                    },
                    "unit_digit": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Constant (Unit, Digit) pair written for each component. Defaults to (2, 3).",
                    },
                    "random_state": {
                        "type": "integer",
                        "description": "Optional seed for reproducible random save_datetime generation.",
                    },
                },
                "required": ["original_path", "processed_path", "component_columns", "output_path"],
            },
        ),
        types.Tool(
            name="generate_resultados",
            description=(
                "Generates Section 6 — Resultados del Análisis of the air quality report. "
                "For each of the six pollutants (SO2, PM10, PM2.5, NO2, CO, O3) produces: "
                "a color-coded daily compliance table vs. Resolución 2254/2017 norms, "
                "a grouped bar chart, a box plot, and a time-variation figure. "
                "Assembles all into a single self-contained HTML report."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Absolute path to the pollutants CSV file. "
                            "Expected semicolon-delimited columns: "
                            "date;time;station;SO2 ppb;PM10 µg/m3 std;PM2.5 µg/m3 std;"
                            "NO2 ppb;CO ppm;O3 ppb"
                        ),
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory where generated figures and the HTML report will be saved.",
                    },
                },
                "required": ["file_path", "output_dir"],
            },
        ),
        types.Tool(
            name="generate_ica",
            description=(
                "Generates Section 7 — Índice de Calidad del Aire (ICA) of the air quality report. "
                "Computes daily ICA per pollutant using EPA linear interpolation with Res. 2254/2017 "
                "breakpoints, determines the composite ICA per station (maximum across pollutants), "
                "and produces a colour-coded daily table, a calendar heatmap, and a per-pollutant "
                "bar chart per station, plus a composite time-series for all stations. "
                "Assembles all into a single self-contained HTML report."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Absolute path to the pollutants CSV file. "
                            "Same format as generate_resultados: semicolon-delimited columns: "
                            "date;time;station;SO2 ppb;PM10 µg/m3 std;PM2.5 µg/m3 std;"
                            "NO2 ppb;CO ppm;O3 ppb"
                        ),
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory where figures and the HTML report will be saved.",
                    },
                },
                "required": ["file_path", "output_dir"],
            },
        ),
        types.Tool(
            name="generate_conclusiones",
            description=(
                "Generates Section 8 — Conclusiones y Recomendaciones of the air quality report. "
                "Consumes the output dicts of generate_resultados, generate_ica, and "
                "generate_meteorologia to auto-produce a Spanish compliance narrative for each "
                "pollutant (PM10, PM2.5, SO2, NO2, CO, O3) and a summary ICA bullet. "
                "Outputs a single self-contained HTML file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "resultados_result": {
                        "type": "object",
                        "description": "Return dict from generate_resultados.",
                    },
                    "ica_result": {
                        "type": "object",
                        "description": "Return dict from generate_ica.",
                    },
                    "meteo_result": {
                        "type": "object",
                        "description": "Return dict from generate_meteorologia.",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory where the HTML report will be saved.",
                    },
                    "location": {
                        "type": "string",
                        "description": (
                            "Human-readable name of the monitoring campaign location, "
                            "e.g. 'la Planta de Beneficio Minero El Diamante'. "
                            "Defaults to 'la zona de estudio' if omitted."
                        ),
                    },
                },
                "required": ["resultados_result", "ica_result", "meteo_result", "output_dir"],
            },
        ),
        types.Tool(
            name="generate_portada",
            description=(
                "Generates the cover page, control page, table of contents, lists of "
                "annexes/figures/tables/graphs, glossary, abbreviations, and Sections "
                "1–4 (Datos Básicos, Introducción, Objetivos, Generalidades) of the air "
                "quality report. Produces a single self-contained HTML report."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "Full report configuration dict — report code/type, period, "
                            "client and final-client info, monitoring stations, emission "
                            "sources, personnel, revision history, compliance tables, "
                            "uncertainty and environmental-conditions tables, figure paths, "
                            "etc. See data/sample_portada_config.json for the full structure."
                        ),
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory where the HTML report will be saved.",
                    },
                },
                "required": ["config", "output_dir"],
            },
        ),
        types.Tool(
            name="assemble_pdf",
            description=(
                "Assembles the section HTML reports into a single paginated PDF. "
                "Accepts the report_path from each section's generate_* tool output. "
                "When portada_html is supplied, its own cover/control/TOC/glossary "
                "pages replace the auto-generated cover page. "
                "Uses Chrome headless for rendering (full CSS + base64 images). "
                "Falls back to WeasyPrint or saves merged HTML if Chrome is unavailable."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "output_dir": {
                        "type": "string",
                        "description": "Directory where the PDF and merged HTML will be saved.",
                    },
                    "portada_html": {
                        "type": "string",
                        "description": (
                            "Path to seccion1_4_portada_generalidades.html "
                            "(report_path from generate_portada). When provided, replaces "
                            "the auto-generated cover page with its own cover, control "
                            "page, TOC, lists, glossary and Sections 1–4."
                        ),
                    },
                    "meteo_html": {
                        "type": "string",
                        "description": "Path to seccion5_meteorologia.html (report_path from generate_meteorologia).",
                    },
                    "resultados_html": {
                        "type": "string",
                        "description": "Path to seccion6_resultados.html (report_path from generate_resultados).",
                    },
                    "ica_html": {
                        "type": "string",
                        "description": "Path to seccion7_ica.html (report_path from generate_ica).",
                    },
                    "conclusiones_html": {
                        "type": "string",
                        "description": "Path to seccion8_conclusiones.html (report_path from generate_conclusiones).",
                    },
                    "title": {
                        "type": "string",
                        "description": "Main title on the cover page. Defaults to 'INFORME DE CALIDAD DEL AIRE'.",
                    },
                    "subtitle": {
                        "type": "string",
                        "description": "Subtitle on the cover page.",
                    },
                    "company_name": {
                        "type": "string",
                        "description": "Company / contractor name shown on the cover page.",
                    },
                    "report_number": {
                        "type": "string",
                        "description": "Report reference number, e.g. 'CA.25420.I1'.",
                    },
                    "period_start": {
                        "type": "string",
                        "description": "ISO date string for the start of the monitoring period.",
                    },
                    "period_end": {
                        "type": "string",
                        "description": "ISO date string for the end of the monitoring period.",
                    },
                    "location": {
                        "type": "string",
                        "description": "Monitoring campaign location shown on the cover page.",
                    },
                },
                "required": ["output_dir"],
            },
        ),
        types.Tool(
            name="generate_meteorologia",
            description=(
                "Generates the Meteorología section of the air quality report. "
                "Produces a color-coded daily summary table (Table 16), a 6-panel "
                "time-series figure (Gráfica 1), an aggregate windrose (Gráfica 2), "
                "a daily windrose grid (Gráfica 3), and auto-generated Spanish "
                "narrative for each meteorological variable."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Absolute path to the meteorological CSV file. "
                            "Expected semicolon-delimited columns: "
                            "date;time;Temp Out - Ind;Hum Out - Ind;"
                            "Wind Speed - Ind;Wind Dir;Press - Ind;Rain - mm;Radiacion Solar"
                        ),
                    },
                    "output_dir": {
                        "type": "string",
                        "description": (
                            "Directory where generated figures (PNG) will be saved. "
                            "Created automatically if it does not exist."
                        ),
                    },
                },
                "required": ["file_path", "output_dir"],
            },
        ),
    ]


# ─────────────────────────────────────────────────────────
# Tool handlers
# ─────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "ingest_excel":
            result = imputer.ingest(arguments["file_path"])

        elif name == "extrapolate_data":
            result = extrapolator.extrapolate(
                file_path=arguments["file_path"],
                n_hours=arguments.get("n_hours", 10),
                wind_dir_columns=arguments.get("wind_dir_columns"),
            )

        elif name == "impute_data":
            result = imputer.impute(
                file_path=arguments["file_path"],
                method=arguments.get("method", "auto"),
                target_columns=arguments.get("target_columns"),
            )

        elif name == "imputation_report":
            result = imputer.comparison_report(
                original_path=arguments["original_path"],
                imputed_path=arguments["imputed_path"],
            )

        elif name == "reconstruct_memoria":
            unit_digit = arguments.get("unit_digit")
            result = memoria_raw.reconstruct(
                original_path=arguments["original_path"],
                processed_path=arguments["processed_path"],
                component_columns=arguments["component_columns"],
                output_path=arguments["output_path"],
                station=arguments.get("station"),
                equipment_name=arguments.get("equipment_name", "Equipment-1:APNA"),
                save_datetime=arguments.get("save_datetime"),
                calibration_component=arguments.get("calibration_component", 1),
                calibration_values=arguments.get("calibration_values"),
                unit_digit=tuple(unit_digit) if unit_digit else (2, 3),
                random_state=arguments.get("random_state"),
            )

        elif name == "generate_ica":
            result = ica_generate_report(
                file_path=arguments["file_path"],
                output_dir=arguments["output_dir"],
            )

        elif name == "generate_resultados":
            result = resultados_generate_report(
                file_path=arguments["file_path"],
                output_dir=arguments["output_dir"],
            )

        elif name == "generate_portada":
            result = portada_generate_report(
                config=arguments["config"],
                output_dir=arguments["output_dir"],
            )

        elif name == "assemble_pdf":
            result = pdf_generate_report(
                output_dir=arguments["output_dir"],
                portada_html=arguments.get("portada_html"),
                meteo_html=arguments.get("meteo_html"),
                resultados_html=arguments.get("resultados_html"),
                ica_html=arguments.get("ica_html"),
                conclusiones_html=arguments.get("conclusiones_html"),
                title=arguments.get("title", "INFORME DE CALIDAD DEL AIRE"),
                subtitle=arguments.get("subtitle", "Campaña de Monitoreo de Calidad del Aire"),
                company_name=arguments.get("company_name", ""),
                report_number=arguments.get("report_number", ""),
                period_start=arguments.get("period_start", ""),
                period_end=arguments.get("period_end", ""),
                location=arguments.get("location", ""),
            )

        elif name == "generate_conclusiones":
            result = conclusiones_generate_report(
                resultados_result=arguments["resultados_result"],
                ica_result=arguments["ica_result"],
                meteo_result=arguments["meteo_result"],
                output_dir=arguments["output_dir"],
                location=arguments.get("location", "la zona de estudio"),
            )

        elif name == "generate_meteorologia":
            result = meteo_generate_report(
                file_path=arguments["file_path"],
                output_dir=arguments["output_dir"],
            )

        else:
            result = {"error": f"Unknown tool: {name}"}

    except FileNotFoundError as e:
        result = {"error": "file_not_found", "detail": str(e)}
    except ValueError as e:
        result = {"error": "validation_error", "detail": str(e)}
    except Exception as e:
        logger.exception(f"Unhandled error in tool '{name}'")
        result = {"error": "internal_error", "detail": str(e)}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


# ─────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────

def main():
    asyncio.run(mcp.server.stdio.run(app))


if __name__ == "__main__":
    main()
