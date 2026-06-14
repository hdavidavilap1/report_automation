from pathlib import Path

import pandas as pd
import pytest

from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw.memoria_raw import MemoriaRawSkill, _format_value

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
    return [line.split(";") for line in lines[5:] if line.strip()]


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

    def test_each_data_row_has_155_fields(self, processed_path):
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
            assert len(row) == 155

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
        assert lines[1].startswith("[Data;Type-Integration;value]")
        assert lines[2].startswith("[Save;Time-")
        assert lines[3].startswith("Date;Component1;Component2;Component3;Status;Caution;Alarm")

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

        caution_blocks = [row[27:91] for row in rows]
        calibration_rows = [i for i, c in enumerate(caution_blocks) if c[31] == "1"]
        assert len(calibration_rows) == 1
        # bit 32 -> index (64-1) - 32 = 31 from the start of the 64-bit caution block
        assert rows[calibration_rows[0]][:2] == [
            f"{pd.Timestamp(result['calibration_timestamp']).day}/"
            f"{pd.Timestamp(result['calibration_timestamp']).month:02d}/"
            f"{pd.Timestamp(result['calibration_timestamp']).year}",
            f"{pd.Timestamp(result['calibration_timestamp']).hour}:"
            f"{pd.Timestamp(result['calibration_timestamp']).minute:02d}:"
            f"{pd.Timestamp(result['calibration_timestamp']).second:02d}",
        ]
        # it's the very first row (start of padding_before)
        assert calibration_rows[0] == 0

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

        alarm_blocks = [row[91:155] for row in rows]
        alarmed_rows = [i for i, a in enumerate(alarm_blocks) if a[57] == "1"]
        # bit 6 -> index (64-1) - 6 = 57
        assert len(alarmed_rows) == result["alarmed_rows"]
        assert result["alarmed_rows"] >= 1

    def test_value_formatting_roundtrip(self, processed_path):
        result = skill.reconstruct(
            original_path=str(SAMPLE_CSV),
            processed_path=processed_path,
            component_columns=COMPONENT_COLUMNS,
            output_path=str(OUTPUT_CSV),
            station=STATION,
            random_state=42,
        )
        df = pd.read_parquet(processed_path)

        lines = _read_lines(OUTPUT_CSV)
        rows = _data_rows(lines)
        # first non-calibration row: compare component_1 value magnitude
        row = rows[1]
        value_str = row[4]
        parsed = float(value_str.replace(",", "."))
        # all values should be on the order of original * 1e6
        assert parsed > 0

    def test_format_value_edge_case(self):
        assert _format_value(1.645) == "1,65E+06"

    def test_format_value_zero(self):
        assert _format_value(0) == "0,00E+00"

    def test_save_datetime_after_last_memory(self, processed_path):
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
        assert save_ts > last_ts
        assert (save_ts.floor("h") - pd.Timedelta(hours=1)) == last_ts

    def test_rejects_when_no_padding_before(self, processed_path):
        # Use the original (un-extrapolated) data as both inputs so there's
        # no padding-before window for the calibration row.
        with pytest.raises(ValueError):
            skill.reconstruct(
                original_path=str(SAMPLE_CSV),
                processed_path=str(SAMPLE_CSV),
                component_columns=COMPONENT_COLUMNS,
                output_path=str(OUTPUT_CSV),
                station=STATION,
                random_state=42,
            )
