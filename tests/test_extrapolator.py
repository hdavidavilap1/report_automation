import pandas as pd
import pytest
from pathlib import Path

from skills.extrapolation.extrapolator import ExtrapolationSkill

SAMPLE_CSV = Path(__file__).parent.parent / "data" / "sample_air_quality_csv.csv"
skill = ExtrapolationSkill()
N_HOURS = 10
N_STATIONS = 3


@pytest.fixture(autouse=True)
def cleanup_parquet():
    yield
    parquet = SAMPLE_CSV.with_name(SAMPLE_CSV.stem + "_extrapolated.parquet")
    if parquet.exists():
        parquet.unlink()


class TestExtrapolate:
    def test_returns_ok(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        assert result["status"] == "ok"

    def test_rows_added(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        assert result["rows_added"] == 2 * N_HOURS * N_STATIONS

    def test_total_rows(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        assert result["total_rows"] == result["original_rows"] + result["rows_added"]

    def test_stations_present(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        assert result["stations"] == ["EST-01", "EST-02", "EST-03"]

    def test_retropolated_range_before_data(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        retro_end = pd.Timestamp(result["retropolated_range"]["end"])
        data_start = pd.Timestamp("2026-04-01 00:00")
        assert retro_end < data_start

    def test_forecast_range_after_data(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        fore_start = pd.Timestamp(result["forecast_range"]["start"])
        data_end = pd.Timestamp("2026-04-30 23:00")
        assert fore_start > data_end

    def test_retropolated_span(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        start = pd.Timestamp(result["retropolated_range"]["start"])
        end = pd.Timestamp(result["retropolated_range"]["end"])
        assert int((end - start).total_seconds() / 3600) == N_HOURS - 1

    def test_forecast_span(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        start = pd.Timestamp(result["forecast_range"]["start"])
        end = pd.Timestamp(result["forecast_range"]["end"])
        assert int((end - start).total_seconds() / 3600) == N_HOURS - 1

    def test_output_parquet_created(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        assert Path(result["output_path"]).exists()

    def test_parquet_readable(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        df = pd.read_parquet(result["output_path"])
        assert len(df) == result["total_rows"]

    def test_no_negatives_in_non_wind_dir_cols(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        df = pd.read_parquet(result["output_path"])
        wd_cols = result["wind_dir_columns"]
        sensor_cols = [c for c in df.select_dtypes("number").columns if c not in wd_cols]
        for col in sensor_cols:
            assert df[col].dropna().min() >= 0, f"{col} has negative values"

    def test_wind_dir_in_valid_range(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        df = pd.read_parquet(result["output_path"])
        for col in result["wind_dir_columns"]:
            vals = df[col].dropna()
            assert vals.min() >= 0 and vals.max() < 360, f"{col} out of [0, 360)"

    def test_auto_detects_wind_dir(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS)
        assert len(result["wind_dir_columns"]) >= 1

    def test_explicit_wind_dir_columns_respected(self):
        result = skill.extrapolate(str(SAMPLE_CSV), n_hours=N_HOURS, wind_dir_columns=["component_9"])
        assert result["wind_dir_columns"] == ["component_9"]

    def test_rejects_missing_file(self):
        with pytest.raises(FileNotFoundError):
            skill.extrapolate("data/nonexistent.csv")
