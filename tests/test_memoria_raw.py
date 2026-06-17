from pathlib import Path

import pandas as pd
import pytest

from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw.memoria_raw import (
    MemoriaRawSkill, WORKING_HOUR_START, WORKING_HOUR_END, _format_value,
    ALARM_BITS_CALIBRATION, STATUS_BIT_MISSING, N_STATUS_BITS,
)

SAMPLE_CSV = Path(__file__).parent.parent / "data" / "sample_air_quality_csv.csv"
N_HOURS = 5
STATION = "EST-01"
COMPONENT_COLUMNS = ["component_1", "component_2", "component_3"]

skill = MemoriaRawSkill()
extrapolator = ExtrapolationSkill()
imputer = ImputationSkill()

EXTRAPOLATED_PARQUET = SAMPLE_CSV.with_name(SAMPLE_CSV.stem + "_extrapolated.parquet")
IMPUTED_PARQUET = EXTRAPOLATED_PARQUET.with_name(EXTRAPOLATED_PARQUET.stem + "_imputed.parquet")
OUTPUT_CSV = Path(__file__).parent / "_memoria_raw_output.csv"


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


class TestReconstruct:
    def test_returns_ok(self, processed_path):
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        assert result["status"] == "ok"

    def test_output_csv_created(self, processed_path):
        skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        assert OUTPUT_CSV.exists()

    def test_row_count_matches_segments(self, processed_path):
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)
        assert len(rows) == result["rows_written"]
        assert result["rows_written"] == (
            result["padding_before_rows"]
            + result["real_window_rows"]
            + result["padding_after_rows"]
        )

    def test_each_data_row_has_154_fields(self, processed_path):
        skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        for row in _data_rows(lines):
            assert len(row) == 154

    def test_header_lines(self, processed_path):
        skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            equipment_name="Equipment-1:APNA",
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        assert lines[0].startswith("[Equipment-1:APNA]")
        assert lines[1].startswith("[Data Type-Integration value]")
        assert lines[2].startswith("[Save Time-")
        assert lines[3].startswith("Date,Component1")
        # Column-header line ends at "Alarm" (91 fields); sub-header has all 154
        assert len(lines[3].split(",")) == 91
        assert len(lines[4].split(",")) == 154

    def test_exactly_one_calibration_row(self, processed_path):
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)

        # Alarm block: cols 90-153 (64 bits). Calibration sets ALARM_BITS_CALIBRATION.
        from skills.memoria_raw.memoria_raw import N_ALARM_BITS
        cal_indices = [(N_ALARM_BITS - 1) - b for b in ALARM_BITS_CALIBRATION]
        alarm_blocks = [row[90:154] for row in rows]
        calibration_rows = [i for i, a in enumerate(alarm_blocks) if all(a[idx] == "1" for idx in cal_indices)]
        assert len(calibration_rows) == 1

        ts = pd.Timestamp(result["calibration_timestamp"])
        expected_dt = ts.strftime("%Y/%m/%d %H:%M:%S")
        assert rows[calibration_rows[0]][0] == expected_dt
        # Calibration row must be within the padding-before window (not necessarily first)
        assert calibration_rows[0] < result["padding_before_rows"]

    def test_alarmed_rows_match_missing_cells(self, processed_path):
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)

        # Status block: cols 10-25 (16 bits). Imputed rows set STATUS_BIT_MISSING.
        status_idx = (N_STATUS_BITS - 1) - STATUS_BIT_MISSING
        status_blocks = [row[10:26] for row in rows]
        alarm_blocks = [row[90:154] for row in rows]
        flagged_rows = [i for i, s in enumerate(status_blocks) if s[status_idx] == "1"]
        assert len(flagged_rows) == result["alarmed_rows"]
        assert result["alarmed_rows"] >= 1
        # Imputed rows must have all-zero Alarm block (only Status is flagged for missing data).
        for idx in flagged_rows:
            assert all(b == "0" for b in alarm_blocks[idx])

    def test_inactive_components_use_dashes(self, processed_path):
        skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=["component_1"],
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)
        # Component2 and Component3 inactive: cols 4-9 should be "-","-","--------------" twice
        for row in rows:
            assert row[4] == "-"
            assert row[5] == "-"
            assert row[6] == "--------------"

    def test_value_formatting_roundtrip(self, processed_path):
        skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)
        # first non-calibration row: Value1 is at col 3 (combined datetime at 0, Unit at 1, Digit at 2)
        row = rows[1]
        value_str = row[3]
        parsed = float(value_str)
        assert parsed > 0

    def test_format_value_edge_case(self):
        assert _format_value(1.645) == "+1.645000E+000"

    def test_format_value_zero(self):
        assert _format_value(0) == "+0.000000E+000"

    def test_save_datetime_in_working_hours(self, processed_path):
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        save_ts = pd.Timestamp(result["save_datetime"])
        last_ts = pd.Timestamp(result["last_memory_timestamp"])
        assert save_ts >= last_ts + pd.Timedelta(hours=1)
        assert WORKING_HOUR_START <= save_ts.hour < WORKING_HOUR_END

    def test_rejects_when_no_padding_before(self, processed_path):
        with pytest.raises(ValueError):
            skill.reconstruct(
                original_path=str(SAMPLE_CSV),
                processed_path=str(SAMPLE_CSV),
                component_columns=COMPONENT_COLUMNS,
                output_path=str(OUTPUT_CSV),
                station=STATION,
                random_state=42,
            )
