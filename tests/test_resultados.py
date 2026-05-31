import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from skills.resultados_analisis.resultados import (
    NORMS,
    POLLUTANT_META,
    POLLUTANT_ORDER,
    _SAFETY_ZONE,
    daily_combined_table,
    figure_bar_chart,
    figure_boxplot,
    figure_timevariation,
    figure_timeseries_hourly,
    generate_pollutant_text,
    generate_report,
    hourly_station_table,
    hourly_8h_station_table,
    load_pollutants,
)

SAMPLE_POLL = Path(__file__).parent.parent / "data" / "sample_pollutants.csv"


@pytest.fixture(scope="module")
def df():
    return load_pollutants(str(SAMPLE_POLL))


@pytest.fixture(scope="module")
def output_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadPollutants:
    def test_expected_columns(self, df):
        for key in POLLUTANT_META:
            assert key in df.columns

    def test_station_column(self, df):
        assert "station" in df.columns

    def test_three_stations(self, df):
        assert set(df["station"].unique()) == {"EST-01", "EST-02", "EST-03"}

    def test_datetime_index(self, df):
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_504_rows(self, df):
        assert len(df) == 504

    def test_all_numeric(self, df):
        for col in POLLUTANT_META:
            assert pd.api.types.is_float_dtype(df[col])

    def test_values_converted_to_ugm3(self, df):
        # ppb columns should be scaled up by their conversion factors
        raw = pd.read_csv(str(SAMPLE_POLL), sep=";")
        so2_raw_max = pd.to_numeric(raw["SO2 ppb"], errors="coerce").max()
        assert df["so2"].max() == pytest.approx(so2_raw_max * 2.620, rel=1e-4)

    def test_co_in_ugm3_range(self, df):
        # CO ppm * 1145 should yield values in µg/m³ range (>>1 ppm)
        assert df["co"].dropna().mean() > 100


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

class TestConstants:
    def test_pollutant_order(self):
        assert POLLUTANT_ORDER == ["pm10", "pm25", "so2", "no2", "co", "o3"]

    def test_norms_keys(self):
        for p in POLLUTANT_ORDER:
            assert p in NORMS

    def test_safety_zone_factor(self):
        assert _SAFETY_ZONE == pytest.approx(0.95)

    def test_pm10_24h_norm(self):
        assert NORMS["pm10"]["24h"][0] == 75.0

    def test_pm25_24h_norm(self):
        assert NORMS["pm25"]["24h"][0] == 37.0

    def test_so2_has_two_norms(self):
        assert "24h" in NORMS["so2"] and "1h" in NORMS["so2"]

    def test_co_has_two_norms(self):
        assert "1h" in NORMS["co"] and "8h" in NORMS["co"]

    def test_o3_8h_norm(self):
        assert NORMS["o3"]["8h"][0] == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Table: daily combined (PM10, PM2.5)
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyCombinedTable:
    @pytest.mark.parametrize("pollutant", ["pm10", "pm25"])
    def test_returns_html_table(self, df, pollutant):
        html = daily_combined_table(df, pollutant, table_num=1)
        assert "<table" in html and "</table>" in html

    def test_compliance_colors(self, df):
        html = daily_combined_table(df, "pm10", table_num=1)
        assert "#92D050" in html or "#FF4444" in html

    def test_norm_value_in_table(self, df):
        html = daily_combined_table(df, "pm10", table_num=1)
        assert "75" in html

    def test_stations_in_header(self, df):
        html = daily_combined_table(df, "pm10", table_num=1)
        assert "Est 1" in html and "Est 2" in html and "Est 3" in html

    def test_resumen_estadistico_block(self, df):
        html = daily_combined_table(df, "pm10", table_num=1)
        assert "Resumen Estadístico" in html

    def test_cumplimiento_normativo_block(self, df):
        html = daily_combined_table(df, "pm10", table_num=1)
        assert "Cumplimiento Normativo" in html
        assert "% Validez" in html
        assert "Numero Excedencias" in html


# ─────────────────────────────────────────────────────────────────────────────
# Table: per-station hourly (SO2, NO2, CO)
# ─────────────────────────────────────────────────────────────────────────────

class TestHourlyStationTable:
    @pytest.mark.parametrize("pollutant,norm_key", [
        ("so2", "1h"), ("no2", "1h"), ("co", "1h"),
    ])
    def test_returns_html_table(self, df, pollutant, norm_key):
        station = sorted(df["station"].unique())[0]
        html = hourly_station_table(df, pollutant, station, norm_key, table_num=1)
        assert "<table" in html and "</table>" in html

    def test_24_hour_rows(self, df):
        station = sorted(df["station"].unique())[0]
        html = hourly_station_table(df, "so2", station, "1h", table_num=1)
        # each row has HH:00 format
        assert "00:00" in html and "23:00" in html

    def test_stats_block_present(self, df):
        station = sorted(df["station"].unique())[0]
        html = hourly_station_table(df, "no2", station, "1h", table_num=1)
        assert "Resumen Estadístico" in html and "% Cumplimiento" in html


class TestHourly8hTable:
    @pytest.mark.parametrize("pollutant,norm_key", [
        ("co", "8h"), ("o3", "8h"),
    ])
    def test_returns_html_table(self, df, pollutant, norm_key):
        station = sorted(df["station"].unique())[0]
        html = hourly_8h_station_table(df, pollutant, station, norm_key, table_num=1)
        assert "<table" in html and "</table>" in html

    def test_stats_block_present(self, df):
        station = sorted(df["station"].unique())[0]
        html = hourly_8h_station_table(df, "o3", station, "8h", table_num=1)
        assert "Resumen Estadístico" in html


# ─────────────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────────────

class TestFigures:
    @pytest.mark.parametrize("pollutant", POLLUTANT_ORDER)
    def test_bar_chart_creates_png(self, df, output_dir, pollutant):
        path = figure_bar_chart(df, pollutant, os.path.join(output_dir, f"bar_{pollutant}.png"))
        assert Path(path).exists()
        assert Path(path).stat().st_size > 5_000

    @pytest.mark.parametrize("pollutant", POLLUTANT_ORDER)
    def test_boxplot_creates_png(self, df, output_dir, pollutant):
        path = figure_boxplot(df, pollutant, os.path.join(output_dir, f"box_{pollutant}.png"))
        assert Path(path).exists()
        assert Path(path).stat().st_size > 5_000

    @pytest.mark.parametrize("pollutant", POLLUTANT_ORDER)
    def test_timevariation_creates_png(self, df, output_dir, pollutant):
        path = figure_timevariation(df, pollutant, os.path.join(output_dir, f"tv_{pollutant}.png"))
        assert Path(path).exists()
        assert Path(path).stat().st_size > 10_000

    @pytest.mark.parametrize("pollutant,norm_key", [
        ("so2", "1h"), ("no2", "1h"), ("co", "1h"), ("co", "8h"), ("o3", "8h"),
    ])
    def test_timeseries_creates_png(self, df, output_dir, pollutant, norm_key):
        path = figure_timeseries_hourly(
            df, pollutant, norm_key,
            os.path.join(output_dir, f"ts_{pollutant}_{norm_key}.png"),
        )
        assert Path(path).exists()
        assert Path(path).stat().st_size > 5_000


# ─────────────────────────────────────────────────────────────────────────────
# Auto-generated text
# ─────────────────────────────────────────────────────────────────────────────

class TestGeneratePollutantText:
    @pytest.mark.parametrize("pollutant,norm_key", [
        ("pm10", "24h"), ("pm25", "24h"), ("so2", "24h"),
        ("no2", "1h"), ("co", "8h"), ("o3", "8h"),
    ])
    def test_returns_string(self, df, pollutant, norm_key):
        text = generate_pollutant_text(df, pollutant, norm_key)
        assert isinstance(text, str) and len(text) > 100

    def test_mentions_norm_value(self, df):
        text = generate_pollutant_text(df, "pm10", "24h")
        assert "2254" in text or "75" in text

    def test_mentions_station_id(self, df):
        text = generate_pollutant_text(df, "so2", "24h")
        assert "CA-" in text

    def test_in_spanish(self, df):
        text = generate_pollutant_text(df, "pm25", "24h")
        assert "período" in text or "concentraci" in text


# ─────────────────────────────────────────────────────────────────────────────
# Full report generation
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateReport:
    def test_returns_report_path(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        assert "report_path" in result
        assert Path(result["report_path"]).exists()

    def test_returns_pollutants_dict(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        assert "pollutants" in result
        assert set(result["pollutants"].keys()) == set(POLLUTANT_ORDER)

    def test_report_is_self_contained(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "data:image/png;base64," in content

    def test_all_six_pollutant_sections(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        for name in ["PM₁₀", "PM₂", "SO₂", "NO₂", "CO", "O₃"]:
            assert name in content, f"Missing section for {name}"

    def test_section_numbering_6_1_to_6_6(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        for sec in ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"]:
            assert sec in content

    def test_norm_reference_in_report(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        assert "2254" in content

    def test_resumen_estadistico_in_report(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        assert "Resumen Estadístico" in content

    def test_cumplimiento_normativo_in_report(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        assert "Cumplimiento Normativo" in content

    def test_all_figure_files_exist(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        for pollutant, figs in result["pollutants"].items():
            for fig_key, fig_val in figs.items():
                if isinstance(fig_val, str):
                    assert Path(fig_val).exists(), f"Missing: {pollutant}/{fig_key}"
                elif isinstance(fig_val, dict):
                    for k, p in fig_val.items():
                        assert Path(p).exists(), f"Missing: {pollutant}/{fig_key}/{k}"

    def test_creates_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "sub", "resultados")
            generate_report(str(SAMPLE_POLL), new_dir)
            assert Path(new_dir).exists()

    def test_co_has_hourly_and_8h_figures(self, output_dir):
        result = generate_report(str(SAMPLE_POLL), output_dir)
        co_figs = result["pollutants"]["co"]
        assert "figs_ts" in co_figs
        assert "1h" in co_figs["figs_ts"]
        assert "8h" in co_figs["figs_ts"]

    def test_pm10_no_hourly_tables(self, output_dir):
        # PM10 is daily — no per-station hourly tables in result
        result = generate_report(str(SAMPLE_POLL), output_dir)
        pm10_figs = result["pollutants"]["pm10"]
        assert "tables_hourly" not in pm10_figs