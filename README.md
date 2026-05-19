# Air Quality MCP — Phase 1: Imputation

MCP server that ingests air quality Excel files and fills missing sensor values.

## Estructura

```
air-quality-mcp/
├── server.py                      # MCP server, define tools
├── pyproject.toml                 # dependencias
└── skills/
    └── imputation/
        └── imputer.py             # lógica de ingesta e imputación
```

## Instalación

```bash
cd air-quality-mcp

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

# Instalar dependencias
pip install -e .
```

## Probar manualmente

```python
from skills.imputation.imputer import ImputationSkill

skill = ImputationSkill()

# 1. Inspeccionar el Excel
info = skill.ingest("datos/mediciones.xlsx")
print(info)

# 2. Imputar (método auto)
result = skill.impute("datos/mediciones.xlsx", method="auto")
print(result)
# → guarda datos/mediciones_imputed.parquet

# 3. Comparar antes/después
report = skill.comparison_report(
    original_path="datos/mediciones.xlsx",
    imputed_path=result["output_path"],
)
print(report)
```

## Conectar a Claude Desktop

Añade esto a tu `claude_desktop_config.json`:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "air-quality": {
      "command": "/ruta/absoluta/a/air-quality-mcp/.venv/bin/python",
      "args": ["/ruta/absoluta/a/air-quality-mcp/server.py"]
    }
  }
}
```

Reemplaza `/ruta/absoluta/a/` con la ruta real del proyecto.  
Reinicia Claude Desktop después de guardar el archivo.

## Tools disponibles

| Tool | Descripción |
|---|---|
| `ingest_excel` | Carga el Excel, valida estructura, devuelve estadísticas de datos faltantes |
| `impute_data` | Imputa valores faltantes, guarda parquet, devuelve estadísticas |
| `imputation_report` | Comparación antes/después de la imputación |

### Métodos de imputación

| Método | Cuándo usarlo |
|---|---|
| `auto` | Deja que el sistema elija (recomendado) |
| `temporal` | Series con < 5% faltantes, gaps cortos |
| `knn` | 5–30% faltantes, contaminantes correlacionados |
| `mice` | > 30% faltantes, fallas largas de sensor |
| `linear` | Alternativa simple a temporal |

## Próximos pasos

- [ ] Skill: windrose
- [ ] Skill: polar_plot  
- [ ] Skill: timevariation
- [ ] Skill: calendarplot
- [ ] Skill: dispersion_map
- [ ] Skill: pdf_assembler
- [ ] Microservicio R/OpenAir (Docker + Plumber)
