import sys
import numpy as np
import pandas as pd

sys.path.insert(0, '/home/hdap/Documents/air-quality-mcp')

from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw_meteo.memoria_raw_meteo import (
    MemoriaRawMeteoSkill,
    _parse_davis_time,
    _DAVIS_COLS,
    _CARDINAL_DEG,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
SRC_DAVIS    = '/home/hdap/Downloads/Vainillal May 26.txt'
PIPELINE_CSV = '/home/hdap/Downloads/vainillal_pipeline.csv'
OUT_DIR      = '/home/hdap/Downloads/meteo_output'

# ─────────────────────────────────────────────────────────────────────────────
# Step 0 — Convert Davis .txt → pipeline-compatible CSV
# ─────────────────────────────────────────────────────────────────────────────
print('=== Step 0: Preprocess Davis file → pipeline CSV ===')

raw   = open(SRC_DAVIS, encoding='utf-8', errors='replace').read()
lines = raw.splitlines()

rows = []
for line in lines[2:]:
    if not line.strip():
        continue
    parts = line.split('\t')
    while len(parts) < len(_DAVIS_COLS):
        parts.append('---')
    rows.append([p.strip() for p in parts[:len(_DAVIS_COLS)]])

df_raw = pd.DataFrame(rows, columns=_DAVIS_COLS)

# Parse Davis date/time → Timestamp
def _parse_row_dt(row):
    try:
        d, m, y = row['Date'].split('/')
        hour = _parse_davis_time(row['Time'])
        return pd.Timestamp(year=2000 + int(y), month=int(m), day=int(d), hour=hour)
    except Exception:
        return pd.NaT

df_raw['_dt'] = df_raw.apply(_parse_row_dt, axis=1)
df_raw = df_raw.dropna(subset=['_dt']).sort_values('_dt').reset_index(drop=True)

def _to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.replace(['---', '------', ''], np.nan), errors='coerce')

# Wind direction: cardinal text → degrees (NaN where missing)
df_raw['_wd_deg'] = df_raw['Wind Dir'].map(_CARDINAL_DEG)

pipeline_df = pd.DataFrame({
    'date':             df_raw['_dt'].dt.strftime('%Y-%m-%d'),
    'time':             df_raw['_dt'].dt.strftime('%H:%M'),
    'Temp Out - Ind':   _to_num(df_raw['Temp Out']),
    'Hum Out - Ind':    _to_num(df_raw['Out Hum']),
    'Wind Speed - Ind': _to_num(df_raw['Wind Speed']),
    'Wind Dir':         df_raw['_wd_deg'],
    'Press - Ind':      _to_num(df_raw['Bar']),
    'Rain - mm':        _to_num(df_raw['Rain']),
})

pipeline_df.to_csv(PIPELINE_CSV, sep=';', index=False)
print(f'  → {PIPELINE_CSV}  ({len(pipeline_df)} rows, '
      f'{pipeline_df.isna().any(axis=1).sum()} rows with missing values)')

# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Extrapolate (extend before/after real window)
# ─────────────────────────────────────────────────────────────────────────────
print()
print('=== Step 1: Extrapolate ===')

ext = ExtrapolationSkill()
r1  = ext.extrapolate(
    file_path=PIPELINE_CSV,
    n_hours=6,
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
    original_path=SRC_DAVIS,
    processed_path=r2['output_path'],
    output_dir=OUT_DIR,
    equipment_code='VAINILLAL',
    random_state=42,
)
print(r3)