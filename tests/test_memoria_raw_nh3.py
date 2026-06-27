from pathlib import Path

import pytest

from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw_nh3.memoria_raw_nh3 import MemoriaRawNH3Skill, COMPONENT1_FRACTION_RANGE

SAMPLE_CSV = Path(__file__).parent.parent / "data" / "sample_air_quality_csv.csv"
N_HOURS = 5
STATION = "EST-01"
COMPONENT2_COLUMN = "component_2"

skill = MemoriaRawNH3Skill()
extrapolator = ExtrapolationSkill()
imputer = ImputationSkill()

EXTRAPOLATED_PARQUET = SAMPLE_CSV.with_name(SAMPLE_CSV.stem + "_extrapolated.parquet")
IMPUTED_PARQUET = EXTRAPOLATED_PARQUET.with_name(EXTRAPOLATED_PARQUET.stem + "_imputed.parquet")
OUTPUT_CSV = Path(__file__).parent / "_memoria_raw_nh3_output.csv"


@pytest.fixture(scope="module")
def processed_path():
    extrapolator.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
    result = imputer.impute(str(EXTRAPOLATED_PARQUET), method="knn")
    yield result["output_path"]

    for p in (EXTRAPOLATED_PARQUET, IMPUTED_PARQUET):
        if p.exists():
            p.unlink()


@pytest.fixture(autouse=True)
def cleanup_output_csv():
    yield
    if OUTPUT_CSV.exists():
        OUTPUT_CSV.unlink()


def _read_lines(path):
    return Path(path).read_text(encoding="utf-8").splitlines()


def _data_rows(lines):
    return [line.split(",") for line in lines[5:] if line.strip()]


class TestMemoriaRawNH3:
    def test_returns_ok_and_fraction_in_range(self, processed_path):
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component2_column=COMPONENT2_COLUMN,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        assert result["status"] == "ok"
        assert COMPONENT1_FRACTION_RANGE[0] <= result["component1_fraction"] <= COMPONENT1_FRACTION_RANGE[1]

    def test_component1_in_slot1_smaller_than_component2_in_slot2(self, processed_path):
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component2_column=COMPONENT2_COLUMN,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        assert result["alarmed_rows"] >= 1
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)
        for row in rows:
            c1_val = float(row[3])
            c2_val = float(row[6])
            assert 0 <= c1_val < c2_val
            # Component3 stays inactive (only 2 channels measured).
            assert row[7] == "-" and row[8] == "-" and row[9] == "--------------"

    def test_component2_slot_override_places_component2_in_slot1(self, processed_path):
        skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component2_column=COMPONENT2_COLUMN,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            component2_slot=1,
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)
        # component2_slot=1 -> component1_slot defaults to 2
        for row in rows:
            c2_val = float(row[3])
            c1_val = float(row[6])
            assert 0 <= c1_val < c2_val

    def test_rejects_invalid_fraction_range(self, processed_path):
        with pytest.raises(ValueError):
            skill.reconstruct(
                original_path=str(SAMPLE_CSV),
                processed_path=processed_path,
                component2_column=COMPONENT2_COLUMN,
                output_path=str(OUTPUT_CSV),
                station=STATION,
                component1_fraction_range=(0.5, 1.5),
                random_state=42,
            )
