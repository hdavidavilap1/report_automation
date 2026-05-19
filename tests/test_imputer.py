import pytest
from pathlib import Path

from skills.imputation.imputer import ImputationSkill

SAMPLE_CSV = Path(__file__).parent.parent / "data" / "sample_air_quality_csv.csv"
skill = ImputationSkill()


@pytest.fixture(autouse=True)
def cleanup_parquet():
    yield
    parquet = SAMPLE_CSV.with_name(SAMPLE_CSV.stem + "_imputed.parquet")
    if parquet.exists():
        parquet.unlink()


class TestIngest:
    def test_returns_ok(self):
        result = skill.ingest(str(SAMPLE_CSV))
        assert result["status"] == "ok"

    def test_row_count(self):
        result = skill.ingest(str(SAMPLE_CSV))
        assert result["rows"] == 2160  # 720 h × 3 stations

    def test_stations_detected(self):
        result = skill.ingest(str(SAMPLE_CSV))
        assert result["stations"] == ["EST-01", "EST-02", "EST-03"]

    def test_nine_sensor_columns(self):
        result = skill.ingest(str(SAMPLE_CSV))
        assert len(result["sensor_columns"]) == 9

    def test_has_missing_values(self):
        result = skill.ingest(str(SAMPLE_CSV))
        assert result["overall_missing_pct"] > 0

    def test_date_range_april_2026(self):
        result = skill.ingest(str(SAMPLE_CSV))
        assert result["date_range"]["start"].startswith("2026-04-01")
        assert result["date_range"]["end"].startswith("2026-04-30")

    def test_missing_by_station_keys(self):
        result = skill.ingest(str(SAMPLE_CSV))
        assert set(result["missing_by_station"].keys()) == {"EST-01", "EST-02", "EST-03"}

    def test_rejects_wrong_extension(self):
        with pytest.raises(ValueError, match="Expected"):
            skill.ingest("data/sample.parquet")

    def test_rejects_missing_file(self):
        with pytest.raises(FileNotFoundError):
            skill.ingest("data/nonexistent.csv")


class TestImpute:
    def test_returns_ok(self):
        result = skill.impute(str(SAMPLE_CSV))
        assert result["status"] == "ok"

    def test_cells_filled_positive(self):
        result = skill.impute(str(SAMPLE_CSV))
        assert result["cells_filled"] > 0

    def test_output_parquet_created(self):
        result = skill.impute(str(SAMPLE_CSV))
        assert Path(result["output_path"]).exists()

    def test_no_missing_after_impute(self):
        result = skill.impute(str(SAMPLE_CSV))
        for col, stats in result["missing_after"].items():
            assert stats["missing"] == 0, f"{col} still has missing values after imputation"

    def test_explicit_method(self):
        result = skill.impute(str(SAMPLE_CSV), method="temporal")
        assert result["method_used"] == "temporal"
