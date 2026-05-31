import os
import tempfile
from pathlib import Path

import pytest

from skills.conclusiones.conclusiones import generate_report

SAMPLE_POLL = Path(__file__).parent.parent / "data" / "sample_pollutants.csv"


@pytest.fixture(scope="module")
def resultados_result():
    from skills.resultados_analisis.resultados import generate_report as rgen
    with tempfile.TemporaryDirectory() as tmp:
        yield rgen(str(SAMPLE_POLL), tmp)


@pytest.fixture(scope="module")
def ica_result():
    from skills.ica.ica import generate_report as igen
    with tempfile.TemporaryDirectory() as tmp:
        yield igen(str(SAMPLE_POLL), tmp)


@pytest.fixture(scope="module")
def meteo_result():
    from skills.meteorologia.meteo import generate_report as mgen
    meteo_csv = Path(__file__).parent.parent / "data" / "sample_meteo.csv"
    with tempfile.TemporaryDirectory() as tmp:
        yield mgen(str(meteo_csv), tmp)


@pytest.fixture(scope="module")
def output_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture(scope="module")
def report(resultados_result, ica_result, meteo_result, output_dir):
    return generate_report(resultados_result, ica_result, meteo_result, output_dir)


# ─────────────────────────────────────────────────────────────────────────────
# resultados_result now includes pollutant_stats
# ─────────────────────────────────────────────────────────────────────────────

class TestResultadosStats:
    def test_pollutant_stats_present(self, resultados_result):
        assert "pollutant_stats" in resultados_result

    def test_period_keys_present(self, resultados_result):
        assert "period_start" in resultados_result
        assert "period_end" in resultados_result

    def test_stations_key_present(self, resultados_result):
        assert "stations" in resultados_result
        assert len(resultados_result["stations"]) == 3

    def test_pm10_max_24h(self, resultados_result):
        pst = resultados_result["pollutant_stats"]["pm10"]
        assert "max_24h" in pst
        m = pst["max_24h"]
        assert "value" in m and "station" in m and "date" in m
        assert 0 < m["value"] <= 1000

    def test_so2_has_1h_max(self, resultados_result):
        pst = resultados_result["pollutant_stats"]["so2"]
        assert "max_1h" in pst

    def test_co_has_8h_max(self, resultados_result):
        pst = resultados_result["pollutant_stats"]["co"]
        assert "max_8h" in pst

    def test_o3_has_8h_max(self, resultados_result):
        pst = resultados_result["pollutant_stats"]["o3"]
        assert "max_8h" in pst


# ─────────────────────────────────────────────────────────────────────────────
# ica_result now includes ica_categories
# ─────────────────────────────────────────────────────────────────────────────

class TestICACategories:
    def test_ica_categories_present(self, ica_result):
        assert "ica_categories" in ica_result

    def test_three_stations(self, ica_result):
        assert len(ica_result["ica_categories"]) == 3

    def test_pollutant_keys(self, ica_result):
        from skills.ica.ica import ICA_BREAKPOINTS
        for sta, cats in ica_result["ica_categories"].items():
            for p in ICA_BREAKPOINTS:
                assert p in cats, f"Missing pollutant {p} for station {sta}"

    def test_composite_key(self, ica_result):
        for sta, cats in ica_result["ica_categories"].items():
            assert "composite" in cats

    def test_category_counts_positive(self, ica_result):
        for sta, cats in ica_result["ica_categories"].items():
            for p, counts in cats.items():
                for cat, n in counts.items():
                    assert n > 0, f"Zero count for {sta}/{p}/{cat}"


# ─────────────────────────────────────────────────────────────────────────────
# generate_report (Section 8)
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateReport:
    def test_returns_report_path(self, report):
        assert "report_path" in report
        assert Path(report["report_path"]).exists()

    def test_html_structure(self, report):
        content = Path(report["report_path"]).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "CONCLUSIONES" in content

    def test_mentions_resolution(self, report):
        content = Path(report["report_path"]).read_text(encoding="utf-8")
        assert "2254" in content

    def test_seven_bullets(self, report):
        assert len(report["bullets"]) == 7

    def test_bullets_not_empty(self, report):
        for b in report["bullets"]:
            assert len(b) > 50

    def test_pm10_bullet_contains_value(self, report, resultados_result):
        pm10_bullet = report["bullets"][0]
        assert "PM" in pm10_bullet
        assert "µg/m³" in pm10_bullet

    def test_period_dates_in_output(self, report):
        assert report["period_start"] != ""
        assert report["period_end"] != ""

    def test_custom_location(self, resultados_result, ica_result, meteo_result):
        with tempfile.TemporaryDirectory() as tmp:
            r = generate_report(
                resultados_result, ica_result, meteo_result, tmp,
                location="la Planta Minera El Dorado"
            )
            content = Path(r["report_path"]).read_text(encoding="utf-8")
            assert "El Dorado" in content

    def test_ica_bullet_mentions_ica(self, report):
        ica_bullet = report["bullets"][-1]
        assert "ICA" in ica_bullet or "Índice" in ica_bullet

    def test_creates_output_dir(self, resultados_result, ica_result, meteo_result):
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "sub", "conclusiones")
            generate_report(resultados_result, ica_result, meteo_result, new_dir)
            assert Path(new_dir).exists()

    def test_compliance_language_pm(self, report):
        for i in range(2):
            assert "cumplimiento" in report["bullets"][i] or "superaciones" in report["bullets"][i]

    def test_so2_bullet_has_both_norms(self, report):
        so2 = report["bullets"][2]
        assert "24 hora" in so2 or "24h" in so2 or "50" in so2
        assert "100" in so2 or "1 hora" in so2