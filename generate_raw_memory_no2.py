import sys
from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw_no2.memoria_raw_no2 import MemoriaRawNO2Skill

src = '/home/hdap/Downloads/TRS_EMVARIAS_389_03.csv'
out = '/home/hdap/Downloads/TRS_EMVARIAS_389_03_raw_memory_no2.csv'

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
print('=== Step 3: Reconstruct memory (NO2 -> NO + NO2 + NOx) ===')
mem = MemoriaRawNO2Skill()
r3 = mem.reconstruct(
    original_path=src,
    processed_path=r2['output_path'],
    no2_column='trs ppb',
    output_path=out,
    station='s1',
    equipment_name='Equipment-1:APNA370',
    no2_slot=2,                                  # Component slot where NO2 (the real channel) is wired
    unit_digit=(1, 2),                           # (Unit, Digit) instrument metadata; Digit = decimal precision
    no_no2_ratio_range=(1.05, 1.15),             # NO = NO2 * ratio (ratio drawn once per run from this range)
    no_noise_pct=0.02,                           # ±2% hourly noise on top of the ratio-derived NO value
    calibration_component=1,                     # index (1-based) into component_columns=[no2_column] to calibrate
    calibration_values=[400, 300, 200, 100, 0],  # nominal calibration gas concentrations (ppb)
    calibration_offset_hours=2,                  # hours after padding-before start to place the calibration row
    random_state=42,
)
print(r3)
