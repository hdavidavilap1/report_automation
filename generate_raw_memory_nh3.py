import sys
sys.path.insert(0, '/home/hdap/Documents/air-quality-mcp')
from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw_nh3.memoria_raw_nh3 import MemoriaRawNH3Skill

src = '/home/hdap/Downloads/TRS_EMVARIAS_389_03.csv'
out = '/home/hdap/Downloads/TRS_EMVARIAS_389_03_raw_memory_nh3.csv'

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
print('=== Step 3: Reconstruct memory (Component2 -> Component1 < Component2) ===')
mem = MemoriaRawNH3Skill()
r3 = mem.reconstruct(
    original_path=src,
    processed_path=r2['output_path'],
    component2_column='trs ppb',
    output_path=out,
    station='s1',
    equipment_name='Equipment-1:APNA370',
    component2_slot=2,                           # Component slot where the real channel is wired
    unit_digit=(1, 2),                           # (Unit, Digit) instrument metadata; Digit = decimal precision
    component1_fraction_range=(0.3, 0.7),        # Component1 = Component2 * fraction (fraction drawn once per run)
    calibration_component=1,                     # index (1-based) into component_columns=[component2_column] to calibrate
    calibration_values=[400, 300, 200, 100, 0],  # nominal calibration gas concentrations (ppb)
    calibration_offset_hours=2,                  # hours after padding-before start to place the calibration row
    random_state=42,
)
print(r3)
