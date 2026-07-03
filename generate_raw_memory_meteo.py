import sys

sys.path.insert(0, '/home/hdap/Documents/air-quality-mcp')

from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw_meteo.memoria_raw_meteo import MemoriaRawMeteoSkill

# ── Paths ─────────────────────────────────────────────────────────────────────
PIPELINE_CSV = '/home/hdap/Downloads/vainillal_pipeline.csv'
OUT_DIR      = '/home/hdap/Downloads/meteo_output'

# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Extrapolate (extend before/after real window)
# ─────────────────────────────────────────────────────────────────────────────
print('=== Step 1: Extrapolate ===')

ext = ExtrapolationSkill()
r1  = ext.extrapolate(
    file_path=PIPELINE_CSV,
    n_hours=15,
    wind_dir_columns=['Wind Dir'],
)
print(r1)

# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Impute missing outdoor values
# ─────────────────────────────────────────────────────────────────────────────
print()
print('=== Step 2: Impute ===')

imp = ImputationSkill()
r2  = imp.impute(
    file_path=r1['output_path'],
    method='temporal',
    target_columns=[
        'temp out - ind',
        'hum out - ind',
        'wind speed - ind',
        'press - ind',
        'rain - mm',
    ],
)
print(r2)

# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Reconstruct Davis WeatherLink .txt
# ─────────────────────────────────────────────────────────────────────────────
print()
print('=== Step 3: Reconstruct Davis WeatherLink memory ===')

mem = MemoriaRawMeteoSkill()
r3  = mem.reconstruct(
    original_path=PIPELINE_CSV,
    processed_path=r2['output_path'],
    output_dir=OUT_DIR,
    equipment_code='VAINILLAL',
    random_state=42,
)
print(r3)