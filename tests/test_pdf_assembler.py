import os
import tempfile
from pathlib import Path

import pytest

from skills.pdf_assembler.assembler import (
    _extract_body,
    _extract_styles,
    _find_chrome,
    generate_report,
)

SAMPLE_POLL = Path(__file__).parent.parent / "data" / "sample_pollutants.csv"
SAMPLE_METEO = Path(__file__).parent.parent / "data" / "sample_meteo.csv"


@pytest.fixture(scope="module")
def section_htmls():
    """Generate all four section HTML files into a shared temp dir."""
    from skills.meteorologia.meteo import generate_report as mgen
    from skills.resultados_analisis.resultados import generate_report as rgen
    from skills.ica.ica import generate_report as igen
    from skills.conclusiones.conclusiones import generate_report as cgen

    with tempfile.TemporaryDirectory() as tmp:
        meteo_r = mgen(str(SAMPLE_METEO), os.path.join(tmp, "meteo"))
        res_r = rgen(str(SAMPLE_POLL), os.path.join(tmp, "resultados"))
        ica_r = igen(str(SAMPLE_POLL), os.path.join(tmp, "ica"))
        conc_r = cgen(res_r, ica_r, meteo_r, os.path.join(tmp, "conclusiones"))
        yield {
            "meteo":        meteo_r["report_path"],
            "resultados":   res_r["report_path"],
            "ica":          ica_r["report_path"],
            "conclusiones": conc_r["report_path"],
            "period_start": res_r["period_start"],
            "period_end":   res_r["period_end"],
        }


@pytest.fixture(scope="module")
def assembled(section_htmls):
    with tempfile.TemporaryDirectory() as tmp:
        yield generate_report(
            output_dir=tmp,
            meteo_html=section_htmls["meteo"],
            resultados_html=section_htmls["resultados"],
            ica_html=section_htmls["ica"],
            conclusiones_html=section_htmls["conclusiones"],
            period_start=section_htmls["period_start"],
            period_end=section_htmls["period_end"],
            title="INFORME DE CALIDAD DEL AIRE",
            subtitle="Campaña de Monitoreo de Calidad del Aire",
            company_name="Corola Ambiental S.A.S.",
            report_number="CA.25420.I1",
            location="Planta de Beneficio Minero",
        )


# ─────────────────────────────────────────────────────────────────────────────
# HTML extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_extract_body_returns_content(self, section_htmls):
        body = _extract_body(section_htmls["conclusiones"])
        assert len(body) > 100
        assert "<html" not in body
        assert "<body" not in body

    def test_extract_body_keeps_tags(self, section_htmls):
        body = _extract_body(section_htmls["conclusiones"])
        assert "<h1" in body or "<p" in body

    def test_extract_styles_returns_css(self, section_htmls):
        styles = _extract_styles(section_htmls["conclusiones"])
        assert "font-family" in styles or "body" in styles or len(styles) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Merged HTML
# ─────────────────────────────────────────────────────────────────────────────

class TestMergedHTML:
    def test_html_path_exists(self, assembled):
        assert Path(assembled["html_path"]).exists()

    def test_html_is_valid(self, assembled):
        content = Path(assembled["html_path"]).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "</html>" in content

    def test_all_sections_present(self, assembled):
        content = Path(assembled["html_path"]).read_text(encoding="utf-8")
        for sid in ["section-5", "section-6", "section-7", "section-8"]:
            assert sid in content

    def test_cover_page_present(self, assembled):
        content = Path(assembled["html_path"]).read_text(encoding="utf-8")
        assert "INFORME DE CALIDAD DEL AIRE" in content
        assert "Corola Ambiental" in content

    def test_report_number_on_cover(self, assembled):
        content = Path(assembled["html_path"]).read_text(encoding="utf-8")
        assert "CA.25420.I1" in content

    def test_period_on_cover(self, assembled):
        content = Path(assembled["html_path"]).read_text(encoding="utf-8")
        assert "abril" in content or "2026" in content

    def test_base64_images_preserved(self, assembled):
        content = Path(assembled["html_path"]).read_text(encoding="utf-8")
        assert "data:image/png;base64," in content

    def test_four_sections_included(self, assembled):
        assert len(assembled["sections_included"]) == 4

    def test_html_size_reasonable(self, assembled):
        size = Path(assembled["html_path"]).stat().st_size
        assert size > 500_000  # should be several MB with base64 images


# ─────────────────────────────────────────────────────────────────────────────
# PDF output
# ─────────────────────────────────────────────────────────────────────────────

class TestPDF:
    def test_pdf_path_returned(self, assembled):
        assert "pdf_path" in assembled

    def test_renderer_reported(self, assembled):
        assert assembled["renderer"] in ("chrome", "weasyprint") or \
               assembled["renderer"].startswith("html_only")

    @pytest.mark.skipif(_find_chrome() is None, reason="Chrome not available")
    def test_pdf_exists_when_chrome_available(self, assembled):
        if assembled["renderer"] == "chrome":
            assert Path(assembled["pdf_path"]).exists()

    def test_pdf_is_real_pdf_when_present(self, assembled):
        if assembled["pdf_path"] and Path(assembled["pdf_path"]).exists():
            header = Path(assembled["pdf_path"]).read_bytes()[:4]
            assert header == b"%PDF"

    def test_pdf_size_reasonable_when_present(self, assembled):
        if assembled["pdf_path"] and Path(assembled["pdf_path"]).exists():
            size = Path(assembled["pdf_path"]).stat().st_size
            assert size > 100_000


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_partial_sections(self, section_htmls):
        with tempfile.TemporaryDirectory() as tmp:
            r = generate_report(
                output_dir=tmp,
                conclusiones_html=section_htmls["conclusiones"],
            )
            assert Path(r["html_path"]).exists()
            assert r["sections_included"] == ["section-8"]

    def test_no_sections_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError):
                generate_report(output_dir=tmp)

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(FileNotFoundError):
                generate_report(output_dir=tmp, meteo_html="/nonexistent/file.html")

    def test_creates_output_dir(self, section_htmls):
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "sub", "pdf")
            generate_report(
                output_dir=new_dir,
                conclusiones_html=section_htmls["conclusiones"],
            )
            assert Path(new_dir).exists()