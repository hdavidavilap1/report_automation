import math
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from skills.ica.ica import (
    ICA_BREAKPOINTS,
    ICA_CATEGORIES,
    _ica_category,
    _ica_color,
    _interpolate_ica,
    compute_ica,
    figure_calendar_heatmap,
    figure_ica_pollutant_bars,
    figure_ica_timeseries,
    generate_report,
    ica_category_legend_table,
    ica_daily_table,
)

SAMPLE_POLL = Path(__file__).parent.parent / "data" / "sample_pollutants.csv"


@pytest.fixture(scope="module")
def df_raw():
    from skills.resultados_analisis.resultados import load_pollutants
    return load_pollutants(str(SAMPLE_POLL))


@pytest.fixture(scope="module")
def ica_df(df_raw):
    return compute_ica(df_raw)


@pytest.fixture(scope="module")
def output_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


# ─────────────────────────────────────────────────────────────────────────────
# Breakpoints and categories
# ─────────────────────────────────────────────────────────────────────────────

class TestConstants:
    def test_all_pollutants_have_breakpoints(self):
        for p in ("pm10", "pm25", "so2", "no2", "co", "o3"):
            assert p in ICA_BREAKPOINTS

    def test_six_categories(self):
        assert len(ICA_CATEGORIES) == 6

    def test_categories_start_at_zero(self):
        assert ICA_CATEGORIES[0][0] == 0

    def test_categories_end_at_500(self):
        assert ICA_CATEGORIES[-1][1] == 500


# ─────────────────────────────────────────────────────────────────────────────
# ICA interpolation
# ─────────────────────────────────────────────────────────────────────────────

class TestInterpolateICA:
    def test_zero_concentration_gives_zero(self):
        assert _interpolate_ica(0.0, "pm10") == pytest.approx(0.0)

    def test_nan_returns_nan(self):
        assert math.isnan(_interpolate_ica(float("nan"), "pm10"))

    def test_pm10_at_norm_boundary(self):
        # PM10 55 µg/m³ → ICA ~51
        ica = _interpolate_ica(55.0, "pm10")
        assert 50 <= ica <= 55

    def test_pm25_moderate_range(self):
        # PM2.5 = 20 µg/m³ → moderate range (51-100)
        ica = _interpolate_ica(20.0, "pm25")
        assert 51 <= ica <= 100

    def test_beyond_max_returns_500(self):
        ica = _interpolate_ica(10000.0, "pm10")
        assert ica == 500.0

    @pytest.mark.parametrize("pollutant", list(ICA_BREAKPOINTS.keys()))
    def test_monotone_increasing(self, pollutant):
        bps = ICA_BREAKPOINTS[pollutant]
        c_mid = [(c_lo + c_hi) / 2 for c_lo, c_hi, _, _ in bps]
        ica_vals = [_interpolate_ica(c, pollutant) for c in c_mid]
        for a, b in zip(ica_vals, ica_vals[1:]):
            assert a < b


# ─────────────────────────────────────────────────────────────────────────────
# ICA color and category helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_ica_color_good(self):
        bg, fg = _ica_color(25)
        assert bg == "#00B050"

    def test_ica_color_nan(self):
        bg, _ = _ica_color(float("nan"))
        assert bg == "#F0F0F0"

    def test_ica_category_good(self):
        assert _ica_category(25) == "Buena"

    def test_ica_category_acceptable(self):
        assert _ica_category(75) == "Aceptable"

    def test_ica_category_nan(self):
        assert _ica_category(float("nan")) == "-"


# ─────────────────────────────────────────────────────────────────────────────
# compute_ica
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeICA:
    def test_returns_dataframe(self, ica_df):
        assert isinstance(ica_df, pd.DataFrame)

    def test_multiindex_date_station(self, ica_df):
        assert ica_df.index.names == ["date", "station"]

    def test_three_stations(self, ica_df):
        stations = ica_df.index.get_level_values("station").unique()
        assert len(stations) == 3

    def test_seven_days(self, ica_df):
        dates = ica_df.index.get_level_values("date").unique()
        assert len(dates) == 7

    def test_ica_columns_present(self, ica_df):
        for p in ICA_BREAKPOINTS:
            assert f"ica_{p}" in ica_df.columns

    def test_composite_column_present(self, ica_df):
        assert "ica_composite" in ica_df.columns

    def test_composite_is_max_across_pollutants(self, ica_df):
        for idx, row in ica_df.iterrows():
            poll_icas = [row[f"ica_{p}"] for p in ICA_BREAKPOINTS if f"ica_{p}" in ica_df.columns]
            valid = [v for v in poll_icas if not math.isnan(v)]
            if valid:
                assert row["ica_composite"] == pytest.approx(max(valid), abs=1e-6)

    def test_all_ica_values_in_range(self, ica_df):
        for p in ICA_BREAKPOINTS:
            col = f"ica_{p}"
            if col in ica_df.columns:
                valid = ica_df[col].dropna()
                assert (valid >= 0).all() and (valid <= 500).all()


# ─────────────────────────────────────────────────────────────────────────────
# HTML tables
# ─────────────────────────────────────────────────────────────────────────────

class TestTables:
    def test_legend_table_returns_html(self):
        html = ica_category_legend_table()
        assert "<table" in html and "</table>" in html

    def test_legend_has_six_categories(self):
        html = ica_category_legend_table()
        assert html.count("Buena") >= 1
        assert html.count("Peligrosa") >= 1

    def test_daily_table_returns_html(self, ica_df):
        station = sorted(ica_df.index.get_level_values("station").unique())[0]
        html = ica_daily_table(ica_df, station, table_num=25)
        assert "<table" in html and "</table>" in html

    def test_daily_table_has_composite_column(self, ica_df):
        station = sorted(ica_df.index.get_level_values("station").unique())[0]
        html = ica_daily_table(ica_df, station, table_num=25)
        assert "ICA" in html and "Compuesto" in html

    def test_daily_table_shows_category(self, ica_df):
        station = sorted(ica_df.index.get_level_values("station").unique())[0]
        html = ica_daily_table(ica_df, station, table_num=25)
        assert "Buena" in html or "Aceptable" in html


# ─────────────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────────────

class TestFigures:
    def test_timeseries_creates_png(self, ica_df, output_dir):
        path = os.path.join(output_dir, "ts.png")
        result = figure_ica_timeseries(ica_df, path)
        assert Path(result).exists()
        assert Path(result).stat().st_size > 10_000

    def test_calendar_heatmap_creates_png(self, ica_df, output_dir):
        station = sorted(ica_df.index.get_level_values("station").unique())[0]
        path = os.path.join(output_dir, f"cal_{station}.png")
        result = figure_calendar_heatmap(ica_df, station, path)
        assert Path(result).exists()
        assert Path(result).stat().st_size > 5_000

    def test_pollutant_bars_creates_png(self, ica_df, output_dir):
        station = sorted(ica_df.index.get_level_values("station").unique())[0]
        path = os.path.join(output_dir, f"bars_{station}.png")
        result = figure_ica_pollutant_bars(ica_df, station, path)
        assert Path(result).exists()
        assert Path(result).stat().st_size > 5_000

    def test_all_stations_get_calendar(self, ica_df, output_dir):
        for sta in sorted(ica_df.index.get_level_values("station").unique()):
            path = os.path.join(output_dir, f"cal2_{sta}.png")
            figure_calendar_heatmap(ica_df, sta, path)
            assert Path(path).exists()


# ─────────────────────────────────────────────────────────────────────────────
# Full report generation
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateReport:
    def test_returns_report_path(self, output_dir):
        r = generate_report(str(SAMPLE_POLL), output_dir)
        assert "report_path" in r
        assert Path(r["report_path"]).exists()

    def test_report_is_self_contained(self, output_dir):
        r = generate_report(str(SAMPLE_POLL), output_dir)
        content = Path(r["report_path"]).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "data:image/png;base64," in content

    def test_report_mentions_resolution(self, output_dir):
        r = generate_report(str(SAMPLE_POLL), output_dir)
        content = Path(r["report_path"]).read_text(encoding="utf-8")
        assert "2254" in content

    def test_returns_three_stations(self, output_dir):
        r = generate_report(str(SAMPLE_POLL), output_dir)
        assert len(r["stations"]) == 3

    def test_station_figures_exist(self, output_dir):
        r = generate_report(str(SAMPLE_POLL), output_dir)
        for sta, figs in r["stations"].items():
            for key, path in figs.items():
                assert Path(path).exists(), f"Missing {sta}/{key}"

    def test_timeseries_figure_exists(self, output_dir):
        r = generate_report(str(SAMPLE_POLL), output_dir)
        assert Path(r["fig_timeseries"]).exists()

    def test_ica_summary_structure(self, output_dir):
        r = generate_report(str(SAMPLE_POLL), output_dir)
        for sta, summary in r["ica_summary"].items():
            assert "mean_composite" in summary
            assert "max_composite" in summary
            assert "dominant_category" in summary
            assert 0 <= summary["mean_composite"] <= 500
            assert summary["max_composite"] >= summary["mean_composite"]

    def test_creates_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "sub", "ica")
            generate_report(str(SAMPLE_POLL), new_dir)
            assert Path(new_dir).exists()