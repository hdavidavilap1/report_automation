# Air Quality Report Automation

## Project overview

MCP server that automates air quality report generation for an environmental monitoring company.
It receives Excel files with sensor measurements, imputes missing data, generates standardized
figures (windrose, polar plot, timevariation, calendarplot, dispersion map), and assembles a
formal PDF report.

## Current status

**Phase 1 complete:** MCP server + imputation skill.
**Phase 2 complete:** Report generation skills — `portada_generalidades`, `meteorologia`, `resultados_analisis`, `ica`, and `conclusiones` all done.
**Phase 3 complete:** PDF assembler skill — Chrome headless renderer (WeasyPrint fallback), now also merges the `portada_generalidades` section.
**Phase 4 discarded:** R/OpenAir microservice (Docker + Plumber) is not needed — the Python-native figures (windrose, timevariation) already cover the report's requirements.

## Report section skills (Phase 2)

The report is organised in five sections, each with its own skill:

| Section | Skill | Status | MCP tool |
|---|---|---|---|
| Portada + 1–4 (Datos Básicos, Introducción, Objetivos, Generalidades) | `skills/portada_generalidades/` | **Done** | `generate_portada` |
| 5. Meteorología | `skills/meteorologia/` | **Done** | `generate_meteorologia` |
| 6. Resultados del análisis | `skills/resultados_analisis/` | **Done** | `generate_resultados` |
| 7. ICA (Índice de Calidad del Aire) | `skills/ica/` | **Done** | `generate_ica` |
| 8. Conclusiones y recomendaciones | `skills/conclusiones/` | **Done** | `generate_conclusiones` |

### portada_generalidades skill outputs
`generate_report(config, output_dir)` returns a dict with:
- **`report_path`:** Single self-contained HTML file (`seccion1_4_portada_generalidades.html`) with cover page, control page (signatures/revisions), table of contents, lists of annexes/figures/tables/graphs, glossary, abbreviations, and Sections 1–4 (Datos Básicos, Introducción, Objetivos, Generalidades §4.1–§4.13), all embedded (images as base64)

The `config` dict carries all report metadata (client/final-client info, monitoring stations, emission sources, personnel, revision history, compliance/uncertainty/environmental-conditions tables, figure paths, etc.) — see `data/sample_portada_config.json` for the full structure.

### meteorologia skill outputs
`generate_report(file_path, output_dir)` returns a dict with:
- **`report_path`:** Single self-contained HTML file (`seccion5_meteorologia.html`) with all content embedded (images as base64)
- **`table_html`:** Raw HTML string for the color-coded daily summary table
- **`figure_timeseries`:** Path to 6-panel time-series PNG (Gráfica 1)
- **`figure_windrose_aggregate`:** Path to aggregate windrose PNG (Gráfica 2)
- **`figure_windrose_daily`:** Path to daily windrose grid PNG (Gráfica 3)
- **`texts`:** Dict with keys `temperatura`, `precipitacion`, `humedad_relativa`, `viento`

#### HTML report structure (`seccion5_meteorologia.html`)
The assembled report follows the company's standard format exactly:
- Section intro: institutional boilerplate explaining meteorological parameters and the color scale
- **Tabla 16** — color-coded daily summary (green→yellow→red per column, normalized to dataset range): T_max, T_min, T_prom, HR_max/min/prom, Prec total, WS_max/prom, Dir. Predominante (16-point Spanish compass)
- **Gráfica 1** — 6-panel time-series: temp (line), humidity (line), precipitation (bars), wind speed (line), wind direction (scatter, avoids 0/360 jump artifacts), solar radiation (line)
- **5.1 Temperatura** — institutional definition paragraph + auto-generated data summary
- **5.2 Precipitación** — institutional definition paragraph + auto-generated data summary
- **5.3 Humedad Relativa** — institutional definition paragraph + auto-generated data summary
- **5.4 Viento** — institutional paragraph on Colombian wind patterns + auto-generated data summary
- **Gráfica 2** — aggregate windrose (16 sectors, normed frequency, full period)
- **Gráfica 3** — daily windrose grid (4-column layout, one panel per day)

## Architecture

```
CSV/Excel input
    │
    ▼
MCP server (server.py)             ← orchestrates the full pipeline
    │
    ├── skill: extrapolation        ← extends time series beyond available data (retropolation + forecast, runs first)
    ├── skill: imputation           ← fills missing sensor values (sklearn)
    ├── skill: memoria_raw          ← reconstructs a lost raw-instrument memory dump (optional, data recovery only)
    │
    ├── skill: portada_generalidades ← cover/control/TOC/glossary + Secciones 1-4
    ├── skill: meteorologia         ← Table 16 + Gráficas 1-3 + narrative text
    ├── skill: resultados_analisis  ← per-pollutant tables + bar charts + box plots + timeVariation
    ├── skill: ica                  ← ICA calculation (Res. 2254/2017) + calendar heatmaps
    ├── skill: conclusiones         ← compliance narrative + recommendations
    │
    └── skill: pdf_assembler        ← WeasyPrint, formal layout
```

## Project structure

```
air-quality-mcp/
├── server.py                           # MCP server, tool definitions and handlers
├── pyproject.toml                      # dependencies
├── CLAUDE.md                           # this file
├── data/
│   ├── sample_meteo.csv                # semicolon-delimited; date;time + 7 meteo vars
│   ├── sample_pollutants.csv           # semicolon-delimited; date;time;station + 6 pollutants
│   └── sample_portada_config.json      # sample config dict for generate_portada (client, stations, sources, compliance, etc.)
└── skills/
    ├── __init__.py
    ├── imputation/
    │   ├── __init__.py
    │   └── imputer.py                  # ingest, impute, comparison_report
    ├── extrapolation/
    │   ├── __init__.py
    │   └── extrapolator.py             # retropolation + forecast via hot-deck, extrapolate()
    ├── memoria_raw/
    │   ├── __init__.py
    │   └── memoria_raw.py              # reconstructs a lost APNA-370 _HA.csv memory dump, reconstruct()
    ├── portada_generalidades/
    │   ├── __init__.py
    │   └── portada_generalidades.py     # cover/control/TOC/lists/glossary + Secciones 1-4, generate_report
    ├── meteorologia/
    │   ├── __init__.py
    │   └── meteo.py                    # load_meteo, daily_summary_table, figure_*, generate_text, generate_report
    ├── resultados_analisis/
    │   ├── __init__.py
    │   └── resultados.py               # load_pollutants, _rolling_8h, per-pollutant tables + figures, generate_report
    ├── ica/
    │   ├── __init__.py
    │   └── ica.py                      # compute_ica, per-pollutant ICA tables, calendar heatmaps, generate_report
    └── pdf_assembler/
        ├── __init__.py
        └── assembler.py                # merges section HTMLs (portada + 5-8) into one paginated PDF
```

## Key technical decisions

- **Transport:** stdio (standard MCP pattern, works with Claude Desktop and Claude Code)
- **Intermediate format:** parquet (fast I/O, preserves dtypes, sits next to the original Excel)
- **Imputation method selection (auto mode):**
  - < 5% missing → `temporal` (time-aware linear interpolation)
  - 5–30% missing → `knn` (K-Nearest Neighbours, sklearn)
  - > 30% missing → `mice` (Iterative Imputer, sklearn)
- **OpenAir figures:** Python-native (windrose, timevariation via matplotlib) — the R/OpenAir microservice was evaluated and discarded as unnecessary
- **PDF assembly:** WeasyPrint (HTML → PDF, reliable pagination and layout)

## Data format

Input Excel files follow this structure (to be confirmed with client):
- One sheet per pollutant (PM2.5, NO2, O3, CO, SO2, NOx)
- Columns: `fecha` + one column per monitoring station (3 stations)
- Hourly measurements, ~8,760 rows per year
- Typical file size: 2–10 MB (not a memory concern)

The ingestion step normalises all sheets into a single long-format DataFrame:
`fecha | estacion | pm25 | no2 | o3 | co | so2 | nox | ws | wd`

## MCP tools

| Tool | Input | Output |
|---|---|---|
| `ingest_excel` | `file_path` | summary: columns, date range, missing % per column, recommended imputation method |
| `extrapolate_data` | `file_path`, `n_hours?`, `wind_dir_columns?` | extended parquet path (retropolation + forecast via hot-deck); run before `impute_data` |
| `impute_data` | `file_path`, `method`, `target_columns` | imputed parquet path, cells filled, before/after stats |
| `imputation_report` | `original_path`, `imputed_path` | side-by-side missing data comparison |
| `reconstruct_memoria` | `original_path`, `processed_path`, `component_columns`, `output_path`, station/calibration/save_datetime options | reconstructed APNA-370 `_HA.csv` raw memory dump, with Alarm bit 6 ("V") flagging hot-deck-filled hours and Caution bit 32 ("DR") flagging the reconstructed calibration row; **data-recovery only** — for memory files that genuinely existed but were lost |
| `generate_portada` | `config`, `output_dir` | self-contained HTML report with cover, control page, TOC, lists, glossary, abbreviations and Sections 1–4 |
| `generate_meteorologia` | `file_path`, `output_dir` | self-contained HTML report + 3 PNG figure paths + table HTML + 4 narrative texts |
| `generate_resultados` | `file_path`, `output_dir` | self-contained HTML report with 6 pollutant sections × (table + 3 figures + text) |
| `generate_ica` | `file_path`, `output_dir` | self-contained HTML report with sections 7.1–7.6 (per-pollutant ICA tables + calendar heatmaps) + composite timeseries |
| `generate_conclusiones` | `resultados_result`, `ica_result`, `meteo_result`, `output_dir`, `location?` | self-contained HTML report with per-pollutant compliance bullets + ICA narrative |
| `assemble_pdf` | `output_dir`, `portada_html?`, `meteo_html?`, `resultados_html?`, `ica_html?`, `conclusiones_html?`, cover metadata | merged HTML + PDF via Chrome headless (WeasyPrint fallback); `portada_html` replaces the auto-generated cover with its own cover/control/TOC/glossary pages |

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
pip install -e .
```

## Running the MCP server locally

```bash
python server.py
```

## Connecting to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "air-quality": {
      "command": "/absolute/path/to/air-quality-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/air-quality-mcp/server.py"]
    }
  }
}
```

Restart Claude Desktop after saving.

## Data format

### Meteorological CSV (sample_meteo.csv)
Semicolon-delimited, one row per hour, single station:
`date;time;Temp Out - Ind;Hum Out - Ind;Wind Speed - Ind;Wind Dir;Press - Ind;Rain - mm;Radiacion Solar`

Loaded as columns: `temp | hum | ws | wd | press | rain | rad`

### Pollutants CSV (sample_pollutants.csv)
Semicolon-delimited, one row per hour per station (EST-01, EST-02, EST-03):
`date;time;station;SO2 ppb;PM10 µg/m3 std;PM2.5 µg/m3 std;NO2 ppb;CO ppm;O3 ppb`

## Next steps

The pipeline (Phases 1-3) is functionally complete. Remaining work is end-to-end
validation: run the full flow (`ingest_excel` → `extrapolate_data` → `impute_data` →
all section skills → `assemble_pdf`) against real client data and confirm the final
PDF matches the company's formal report format. `reconstruct_memoria` is a separate,
optional step for data-recovery cases (a raw instrument memory file that genuinely
existed but was lost) and is not part of the normal report pipeline.