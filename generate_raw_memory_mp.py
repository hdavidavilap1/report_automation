import sys
sys.path.insert(0, '/home/hdap/Documents/air-quality-mcp')
from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw_mp.memoria_raw_mp import MemoriaRawMPSkill

src     = '/home/hdap/Downloads/TRS_EMVARIAS_389_03_mp.csv'
out_dir = '/home/hdap/Downloads/mp_output'

print('=== Step 1: Extrapolate ===')
ext = ExtrapolationSkill()
r1 = ext.extrapolate(
    file_path=src,
    n_hours=6,
    wind_dir_columns=None,
)
print(r1)

print()
print('=== Step 2: Impute ===')
imp = ImputationSkill()
r2 = imp.impute(
    file_path=r1['output_path'],
    method='temporal',
    target_columns=['pm10 ppb', 'pm2.5 ppb'],
)
print(r2)

print()
print('=== Step 3: Reconstruct PM memory (hourly → per-minute M + L .dat files) ===')
mem = MemoriaRawMPSkill()
r3 = mem.reconstruct(
    original_path=src,
    processed_path=r2['output_path'],
    pm10_column='pm10 ppb',
    pm25_column='pm2.5 ppb',
    output_dir=out_dir,
    station='s1',
    equipment_code='18A20020',
    station_id='001',
    serial_no='8HG20020',
    noise_std=0.15,
    random_state=42,
)
print(r3)