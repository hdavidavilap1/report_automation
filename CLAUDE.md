# Air Quality Report Automation

## Project overview

MCP server that automates air quality report generation for an environmental monitoring company.
It receives Excel files with sensor measurements, imputes missing data, generates standardized
figures (windrose, polar plot, timevariation, calendarplot, dispersion map), and assembles a
formal PDF report.

## Current status

**Phase 1 complete:** MCP server + imputation skill.
**Phase 2 pending:** Report generation skills (windrose, polar plot, timevariation, calendarplot, dispersion map).
**Phase 3 pending:** PDF assembler skill.
**Phase 4 pending:** R/OpenAir microservice (Docker + Plumber) for OpenAir-native figures.

## Architecture

```
Excel input
    │
    ▼
MCP server (server.py)          ← orchestrates the full pipeline
    │
    ├── skill: imputation        ← fills missing sensor values (sklearn)
    │
    ├── skill: windrose          ← Python windrose lib / R OpenAir fallback
    ├── skill: polar_plot        ← matplotlib / R OpenAir fallback
    ├── skill: timevariation     ← matplotlib / R OpenAir fallback
    ├── skill: calendarplot      ← matplotlib / R OpenAir fallback
    ├── skill: dispersion_map    ← matplotlib / R OpenAir fallback
    │
    └── skill: pdf_assembler     ← WeasyPrint, formal layout
```

## Project structure

```
air-quality-mcp/
├── server.py                        # MCP server, tool definitions and handlers
├── pyproject.toml                   # dependencies
├── CLAUDE.md                        # this file
└── skills/
    ├── __init__.py
    └── imputation/
        ├── __init__.py
        └── imputer.py               # ingest, impute, comparison_report
```

## Key technical decisions

- **Transport:** stdio (standard MCP pattern, works with Claude Desktop and Claude Code)
- **Intermediate format:** parquet (fast I/O, preserves dtypes, sits next to the original Excel)
- **Imputation method selection (auto mode):**
  - < 5% missing → `temporal` (time-aware linear interpolation)
  - 5–30% missing → `knn` (K-Nearest Neighbours, sklearn)
  - > 30% missing → `mice` (Iterative Imputer, sklearn)
- **OpenAir figures:** Python-native by default; R/OpenAir microservice activated via `USE_R_OPENAIR=true`
- **PDF assembly:** WeasyPrint (HTML → PDF, reliable pagination and layout)

## Data format

Input Excel files follow this structure (to be confirmed with client):
- One sheet per pollutant (PM2.5, NO2, O3, CO, SO2, NOx)
- Columns: `fecha` + one column per monitoring station (3 stations)
- Hourly measurements, ~8,760 rows per year
- Typical file size: 2–10 MB (not a memory concern)

The ingestion step normalises all sheets into a single long-format DataFrame:
`fecha | estacion | pm25 | no2 | o3 | co | so2 | nox | ws | wd`

## MCP tools (Phase 1)

| Tool | Input | Output |
|---|---|---|
| `ingest_excel` | `file_path` | summary: columns, date range, missing % per column, recommended imputation method |
| `impute_data` | `file_path`, `method`, `target_columns` | imputed parquet path, cells filled, before/after stats |
| `imputation_report` | `original_path`, `imputed_path` | side-by-side missing data comparison |

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

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `USE_R_OPENAIR` | `false` | Set to `true` to route figure generation through the R/OpenAir microservice |
| `OPENAIR_SERVICE_URL` | `http://localhost:8765` | Base URL of the R/Plumber microservice |

## Next steps

1. Receive sample Excel from client → confirm sheet/column structure
2. Adjust `imputer.ingest()` to handle multi-sheet format (one sheet per pollutant)
3. Implement report skills one by one, starting with `windrose`
4. Build R/OpenAir microservice (Dockerfile + Plumber endpoints)
5. Implement `pdf_assembler` skill with WeasyPrint