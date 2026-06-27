from pathlib import Path

import pandas as pd
import pytest

from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw_no2.memoria_raw_no2 import MemoriaRawNO2Skill, NO_NO2_RATIO_RANGE

SAMPLE_CSV = Path(__file__).parent.parent / "data" / "sample_air_quality_csv.csv"
N_HOURS = 5
STATION = "EST-01"
NO2_COLUMN = "component_2"

skill = MemoriaRawNO2Skill()
extrapolator = ExtrapolationSkill()
imputer = ImputationSkill()

EXTRAPOLATED_PARQUET = SAMPLE_CSV.with_name(SAMPLE_CSV.stem + "_extrapolated.parquet")
IMPUTED_PARQUET = EXTRAPOLATED_PARQUET.with_name(EXTRAPOLATED_PARQUET.stem + "_imputed.parquet")
OUTPUT_CSV = Path(__file__).parent / "_memoria_raw_no2_output.csv"


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


class TestMemoriaRawNO2:
    def test_returns_ok_and_ratio_in_range(self, processed_path):
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            no2_column=NO2_COLUMN,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        assert result["status"] == "ok"
        assert NO_NO2_RATIO_RANGE[0] <= result["no_no2_ratio"] <= NO_NO2_RATIO_RANGE[1]

    def test_no_in_slot1_no2_in_slot2_nox_in_slot3(self, processed_path):
        skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            no2_column=NO2_COLUMN,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)
        for row in rows:
            no_val = float(row[3])
            no2_val = float(row[6])
            nox_val = float(row[9])
            assert no_val >= 0
            # Each value is independently rounded to Digit=2 decimals on write,
            # so the sum check needs slack for cumulative rounding error.
            assert nox_val == pytest.approx(no_val + no2_val, abs=0.03)

    def test_no2_slot_override_places_no2_in_slot1(self, processed_path):
        skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            no2_column=NO2_COLUMN,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            no2_slot=1,
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)
        # no2_slot=1 -> no_slot defaults to 2, nox_slot is the remaining slot (3)
        for row in rows:
            no2_val = float(row[3])
            no_val = float(row[6])
            nox_val = float(row[9])
            # Each value is independently rounded to Digit=2 decimals on write,
            # so the sum check needs slack for cumulative rounding error.
            assert nox_val == pytest.approx(no_val + no2_val, abs=0.03)

    def test_nox_equals_no_plus_no2_for_alarmed_rows_too(self, processed_path):
        # Rows with originally-missing NO2 (hot-deck filled) and the calibration
        # row must still satisfy NOx = NO + NO2, since both are derived from
        # whatever NO2 ended up being written.
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            no2_column=NO2_COLUMN,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        assert result["alarmed_rows"] >= 1
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)
        for row in rows:
            no_val, no2_val, nox_val = float(row[3]), float(row[6]), float(row[9])
            assert nox_val == pytest.approx(no_val + no2_val, abs=0.03)
