import sys
sys.path.insert(0, '/home/hdap/Documents/air-quality-mcp')
from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw.memoria_raw import MemoriaRawSkill

src = '/home/hdap/Downloads/ttrs_ppb_prueba.csv'
out = '/home/hdap/Downloads/ttrs_ppb_HA.csv'

print('=== Step 1: Extrapolate ===')
ext = ExtrapolationSkill()
r1 = ext.extrapolate(
    file_path=src,
    n_hours=6,                  # hours to retropolate/forecast before & after the real window
    wind_dir_columns=None,      # column names holding wind direction (circular hot-deck), if any
)
print(r1)

print()
print('=== Step 2: Impute ===')
imp = ImputationSkill()
r2 = imp.impute(
    file_path=r1['output_path'],
    method='temporal',          # 'auto' | 'temporal' | 'knn' | 'mice'
    target_columns=['trs ppb'], # sensor columns to impute
)
print(r2)

print()
print('=== Step 3: Reconstruct memory ===')
mem = MemoriaRawSkill()
r3 = mem.reconstruct(
    original_path=src,
    processed_path=r2['output_path'],
    component_columns=['trs ppb'],
    output_path=out,
    station='s1',
    equipment_name='Equipment-1:APNA370',
    calibration_component=1,                  # index (1-based) into component_columns to calibrate
    calibration_values=[400, 300, 200, 100, 0],  # nominal calibration gas concentrations (ppb)
    calibration_offset_hours=2,                # hours after padding-before start to place the calibration row
    unit_digit=(1, 2),                         # (Unit, Digit) instrument metadata; Digit = decimal precision
    random_state=42,
    component_slots = [2]
)
print(r3)
