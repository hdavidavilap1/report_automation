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
from skills.ica.ica import generate_report as ica_generate_report
from skills.meteorologia.meteo import generate_report as meteo_generate_report
from skills.resultados_analisis.resultados import generate_report as resultados_generate_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("air-quality-mcp")

app = Server("air-quality-reports")
imputer = ImputationSkill()


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
