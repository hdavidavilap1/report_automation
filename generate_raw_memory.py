import sys
sys.path.insert(0, '/home/hdap/Documents/air-quality-mcp')
from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw.memoria_raw import MemoriaRawSkill

src = '/home/hdap/Downloads/ttrs_ppb_prueba.csv'
out = '/home/hdap/Downloads/ttrs_ppb_HA.csv'

print('=== Step 1: Extrapolate ===')
ext = ExtrapolationSkill()
r1 = ext.extrapolate(src, n_hours=6)
print(r1)

print()
print('=== Step 2: Impute ===')
imp = ImputationSkill()
r2 = imp.impute(r1['output_path'], method='temporal')
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
    calibration_offset_hours=2,
)
print(r3)