from pathlib import Path

import pytest

from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw_mp.memoria_raw_mp import MemoriaRawMPSkill

SAMPLE_CSV = Path(__file__).parent.parent / "data" / "sample_pollutants.csv"
N_HOURS = 5
STATION = "EST-01"
PM10_COL = "pm10 µg/m3 std"
PM25_COL = "pm2.5 µg/m3 std"

skill = MemoriaRawMPSkill()
extrapolator = ExtrapolationSkill()
imputer = ImputationSkill()

EXTRAPOLATED_PARQUET = SAMPLE_CSV.with_name(SAMPLE_CSV.stem + "_extrapolated.parquet")
IMPUTED_PARQUET = EXTRAPOLATED_PARQUET.with_name(
    EXTRAPOLATED_PARQUET.stem + "_imputed.parquet"
)
OUTPUT_DIR = Path(__file__).parent / "_mp_output"


@pytest.fixture(scope="module")
def processed_path():
    extrapolator.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
    result = imputer.impute(str(EXTRAPOLATED_PARQUET), method="knn")
    yield result["output_path"]

    for p in (EXTRAPOLATED_PARQUET, IMPUTED_PARQUET):
        if p.exists():
            p.unlink()


@pytest.fixture(scope="module")
def reconstruction(processed_path):
    result = skill.reconstruct(
        original_path=str(SAMPLE_CSV),
        processed_path=processed_path,
        pm10_column=PM10_COL,
        pm25_column=PM25_COL,
        output_dir=str(OUTPUT_DIR),
        station=STATION,
        random_state=42,
    )
    yield result

    for p in OUTPUT_DIR.glob("*.dat"):
        p.unlink()
    if OUTPUT_DIR.exists():
        OUTPUT_DIR.rmdir()


def _data_lines(path: str) -> list[list[str]]:
    """Return tab-split data rows (after the column header line)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("[d&t"):
            return [l.split("\t") for l in lines[i + 1:] if l.strip()]
    return []


class TestMemoriaRawMP:
    def test_returns_ok(self, reconstruction):
        assert reconstruction["status"] == "ok"

    def test_at_least_one_segment(self, reconstruction):
        assert reconstruction["total_segments"] >= 1
        assert len(reconstruction["segments"]) == reconstruction["total_segments"]

    def test_all_segment_files_created(self, reconstruction):
        for seg in reconstruction["segments"]:
            assert Path(seg["m_path"]).exists()
            assert Path(seg["l_path"]).exists()

    def test_segment_filenames_contain_equipment_and_chunk(self, reconstruction):
        for i, seg in enumerate(reconstruction["segments"]):
            m_name = Path(seg["m_path"]).name
            assert "18A20020" in m_name
            assert f"{i + 1:03d}" in m_name
            assert m_name.endswith("-M.dat")
            l_name = Path(seg["l_path"]).name
            assert l_name.endswith("-L.dat")

    def test_segments_do_not_overlap(self, reconstruction):
        segs = reconstruction["segments"]
        for i in range(len(segs) - 1):
            assert segs[i]["end"] < segs[i + 1]["start"]

    def test_total_minutes_is_sum_of_segments(self, reconstruction):
        total = sum(s["minutes"] for s in reconstruction["segments"])
        assert total == reconstruction["total_minutes"]

    def test_each_segment_minutes_less_than_or_equal_hourly_rows_times_60(self, reconstruction):
        # Boundary hours are partial (random start/end minute), so total
        # minutes < hourly_rows * 60 for multi-hour segments, or <= for single-hour.
        for seg in reconstruction["segments"]:
            assert seg["minutes"] <= seg["hourly_rows"] * 60
            assert seg["minutes"] >= 1

    def test_m_row_count_per_segment(self, reconstruction):
        for seg in reconstruction["segments"]:
            rows = _data_lines(seg["m_path"])
            assert len(rows) == seg["minutes"]

    def test_l_row_count_per_segment(self, reconstruction):
        for seg in reconstruction["segments"]:
            rows = _data_lines(seg["l_path"])
            assert len(rows) == seg["minutes"]

    def test_m_pm1_always_zero(self, reconstruction):
        for seg in reconstruction["segments"]:
            for row in _data_lines(seg["m_path"]):
                assert float(row[3]) == 0.0

    def test_m_pm_values_nonnegative(self, reconstruction):
        for seg in reconstruction["segments"]:
            for row in _data_lines(seg["m_path"]):
                assert float(row[1]) >= 0.0
                assert float(row[2]) >= 0.0

    def test_l_first_row_p_is_PP_per_segment(self, reconstruction):
        for seg in reconstruction["segments"]:
            rows = _data_lines(seg["l_path"])
            assert rows[0][1] == "PP"

    def test_l_subsequent_rows_p_is_P(self, reconstruction):
        for seg in reconstruction["segments"]:
            for row in _data_lines(seg["l_path"])[1:]:
                assert row[1] == "P"

    def test_l_constants(self, reconstruction):
        # Field order: ts(0) P(1) Yr(2) Mo(3) D(4) H(5) Min(6)
        #   Loc(7) GF(8) Err(9) Qbatt(10) Im(11) UeL(12) UE4(13) UE3(14)
        #   UE2(15) UE1(16) IV(17)
        for seg in reconstruction["segments"]:
            for row in _data_lines(seg["l_path"]):
                assert row[7]  == "100"  # Loc
                assert row[8]  == "0"    # GF
                assert row[9]  == "130"  # Error
                assert row[12] == "134"  # UeL
                assert row[13] == "0"    # UE4
                assert row[14] == "0"    # UE3
                assert row[16] == "0"    # UE1
                assert row[17] == "0"    # IV

    def test_l_variable_fields_in_range(self, reconstruction):
        for seg in reconstruction["segments"]:
            for row in _data_lines(seg["l_path"]):
                assert 41 <= int(row[10]) <= 43   # Qbatt
                assert 41 <= int(row[11]) <= 44   # Im
                assert 59 <= int(row[15]) <= 124  # UE2

    def test_rejects_missing_column(self, processed_path):
        with pytest.raises(ValueError, match="not found"):
            skill.reconstruct(
                original_path=str(SAMPLE_CSV),
                processed_path=processed_path,
                pm10_column="nonexistent_column",
                pm25_column=PM25_COL,
                output_dir=str(OUTPUT_DIR),
                station=STATION,
                random_state=42,
            )