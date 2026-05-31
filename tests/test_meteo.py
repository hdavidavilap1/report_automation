import os
import tempfile
from pathlib import Path

import pytest

from skills.meteorologia.meteo import (
    daily_summary_table,
    figure_timeseries,
    figure_windrose_aggregate,
    figure_windrose_daily,
    generate_report,
    generate_text,
    load_meteo,
)

SAMPLE_METEO = Path(__file__).parent.parent / "data" / "sample_meteo.csv"


@pytest.fixture(scope="module")
def df():
    return load_meteo(str(SAMPLE_METEO))


@pytest.fixture(scope="module")
def output_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


class TestLoadMeteo:
    def test_expected_columns(self, df):
        assert list(df.columns) == ["temp", "hum", "ws", "wd", "press", "rain", "rad"]

    def test_datetime_index(self, df):
        import pandas as pd
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_all_numeric(self, df):
        import pandas as pd
        for col in df.columns:
            assert pd.api.types.is_float_dtype(df[col])

    def test_7_days(self, df):
        assert len(set(df.index.date)) == 7

    def test_168_rows(self, df):
        assert len(df) == 168


class TestDailySummaryTable:
    def test_returns_html(self, df):
        html = daily_summary_table(df)
        assert html.strip().startswith("<table")
        assert "</table>" in html

    def test_7_data_rows(self, df):
        html = daily_summary_table(df)
        assert html.count("<tr>") == 7

    def test_color_cells_present(self, df):
        html = daily_summary_table(df)
        assert "background:#" in html or "background: #" in html or "#92D050" in html or "#FF4444" in html

    def test_prevailing_direction_in_table(self, df):
        html = daily_summary_table(df)
        compass = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                   "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
        assert any(d in html for d in compass)


class TestFigureTimeseries:
    def test_creates_png(self, df, output_dir):
        path = figure_timeseries(df, os.path.join(output_dir, "ts.png"))
        assert Path(path).exists()
        assert Path(path).stat().st_size > 10_000

    def test_returns_path(self, df, output_dir):
        path = figure_timeseries(df, os.path.join(output_dir, "ts2.png"))
        assert path.endswith(".png")


class TestFigureWindroseAggregate:
    def test_creates_png(self, df, output_dir):
        path = figure_windrose_aggregate(df, os.path.join(output_dir, "wr_agg.png"))
        assert Path(path).exists()
        assert Path(path).stat().st_size > 10_000


class TestFigureWindroseDaily:
    def test_creates_png(self, df, output_dir):
        path = figure_windrose_daily(df, os.path.join(output_dir, "wr_daily.png"))
        assert Path(path).exists()
        assert Path(path).stat().st_size > 20_000


class TestGenerateText:
    def test_returns_four_keys(self, df):
        texts = generate_text(df)
        assert set(texts.keys()) == {"temperatura", "precipitacion", "humedad_relativa", "viento"}

    def test_temperatura_mentions_degrees(self, df):
        texts = generate_text(df)
        assert "°C" in texts["temperatura"]

    def test_viento_mentions_direction(self, df):
        texts = generate_text(df)
        compass = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                   "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
        assert any(d in texts["viento"] for d in compass)

    def test_text_in_spanish(self, df):
        texts = generate_text(df)
        assert "período" in texts["temperatura"]
        assert "promedio" in texts["temperatura"]

    def test_numeric_values_in_text(self, df):
        texts = generate_text(df)
        import re
        assert re.search(r"\d+\.\d+", texts["temperatura"])


class TestGenerateReport:
    def test_all_keys_present(self, output_dir):
        result = generate_report(str(SAMPLE_METEO), output_dir)
        assert set(result.keys()) == {
            "report_path", "table_html", "figure_timeseries",
            "figure_windrose_aggregate", "figure_windrose_daily", "texts"
        }

    def test_all_figures_exist(self, output_dir):
        result = generate_report(str(SAMPLE_METEO), output_dir)
        for key in ("figure_timeseries", "figure_windrose_aggregate", "figure_windrose_daily"):
            assert Path(result[key]).exists(), f"Missing: {key}"

    def test_report_html_written(self, output_dir):
        result = generate_report(str(SAMPLE_METEO), output_dir)
        report = Path(result["report_path"])
        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "5. Meteorología" in content
        assert "Tabla 16" in content
        assert "Gráfica 1" in content
        assert "Gráfica 2" in content
        assert "Gráfica 3" in content
        assert "data:image/png;base64," in content

    def test_report_has_four_subsections(self, output_dir):
        result = generate_report(str(SAMPLE_METEO), output_dir)
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        for sub in ("5.1 Temperatura", "5.2 Precipitación", "5.3 Humedad Relativa", "5.4 Viento"):
            assert sub in content, f"Missing subsection: {sub}"

    def test_creates_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "subdir", "meteo_out")
            result = generate_report(str(SAMPLE_METEO), new_dir)
            assert Path(new_dir).exists()

    def test_table_html_not_empty(self, output_dir):
        result = generate_report(str(SAMPLE_METEO), output_dir)
        assert len(result["table_html"]) > 500