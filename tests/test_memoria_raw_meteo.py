from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skills.extrapolation.extrapolator import ExtrapolationSkill
from skills.imputation.imputer import ImputationSkill
from skills.memoria_raw_meteo.memoria_raw_meteo import (
    MemoriaRawMeteoSkill,
    _CARDINAL_DEG,
    _DAVIS_COLS,
    _format_time,
    _parse_davis_time,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
OUTPUT_DIR      = Path(__file__).parent / "_meteo_output"
DAVIS_TXT       = Path(__file__).parent / "_sample_davis.txt"
PIPELINE_CSV    = Path(__file__).parent / "_sample_meteo_pipeline.csv"
EXTRAP_PARQUET  = PIPELINE_CSV.with_name(PIPELINE_CSV.stem + "_extrapolated.parquet")
IMPUTED_PARQUET = EXTRAP_PARQUET.with_name(EXTRAP_PARQUET.stem + "_imputed.parquet")

skill        = MemoriaRawMeteoSkill()
extrapolator = ExtrapolationSkill()
imputer      = ImputationSkill()

N_HOURS    = 48
GAP_START  = 10   # first gap hour (inclusive)
GAP_END    = 20   # last gap hour (exclusive)
N_GAP      = GAP_END - GAP_START
N_ORIGINAL = N_HOURS - N_GAP

_WIND_CARDINALS = list(_CARDINAL_DEG.keys())


# ── Synthetic Davis .txt generation ──────────────────────────────────────────

def _make_davis_txt(path: Path):
    """
    48-hour synthetic Davis WeatherLink file.
    Hours 10-19 have '---' for outdoor columns (simulated equipment-off gap).
    """
    rng = np.random.default_rng(0)
    base = pd.Timestamp("2025-11-01 00:00")

    header1 = (
        "Date\tTime\tTemp Out\tHi\tLow\tOut\tDew\tWind\tWind\tWind\tHi\tHi\t"
        "Wind\tHeat\tTHW\tBar\tRain\tRain\tHeat\tCool\tIn\tIn\tIn\tIn\t"
        "EMC\tAir\tWind\tWind\tISS\tArc."
    )
    header2 = (
        "\t\tOut\tTemp\tTemp\tHum\tPt.\tSpeed\tDir\tRun\tSpeed\tDir\t"
        "Chill\tIndex\tIndex\t\t\tRate\tD-D\tD-D\tTemp\tHum\tDew\tHeat\t"
        "\tDensity\tSamp\tTx\tRecept\tInt."
    )

    lines = [header1, header2]
    for h in range(N_HOURS):
        dt = base + pd.Timedelta(hours=h)
        date_str = f"{dt.day}/{dt.month:02d}/{str(dt.year)[-2:]}"
        time_str = _format_time(dt.hour)
        is_gap   = GAP_START <= h < GAP_END
        bar      = str(round(float(rng.uniform(1010, 1015)), 1))
        in_temp  = str(round(float(rng.uniform(21, 24)), 1))
        in_hum   = str(int(rng.integers(50, 65)))
        in_dew   = str(round(float(rng.uniform(12, 16)), 1))
        in_heat  = str(round(float(rng.uniform(21, 24)), 1))
        emc      = str(round(float(rng.uniform(11, 13)), 1))
        density  = str(round(float(rng.uniform(1.08, 1.12)), 2))

        if is_gap:
            outdoor = ["---"] * 13
            row = (
                [date_str, time_str]
                + outdoor
                + [bar, "0.00", "0.00", "0.0", "0.0"]
                + [in_temp, in_hum, in_dew, in_heat, emc, density, "119", "1", "100.0", "60"]
            )
        else:
            temp = round(float(rng.uniform(15, 28)), 1)
            hum  = int(rng.integers(55, 85))
            ws   = round(float(rng.uniform(0.5, 15)), 1)
            wd   = _WIND_CARDINALS[int(rng.integers(0, 16))]
            rain = round(float(rng.uniform(0, 2)), 2)
            row = [
                date_str, time_str,
                str(temp),
                str(round(temp + float(rng.uniform(1.1, 1.7)), 1)),
                str(round(temp - float(rng.uniform(1.1, 1.7)), 1)),
                str(hum),
                str(round(float(rng.uniform(10, 18)), 1)),
                str(ws), wd,
                str(round(float(rng.uniform(1, 5)), 2)),
                str(round(ws + float(rng.uniform(0.2, 2)), 1)),
                _WIND_CARDINALS[int(rng.integers(0, 16))],
                str(round(temp - float(rng.uniform(0, 3)), 1)),
                str(round(temp + float(rng.uniform(0, 2)), 1)),
                str(round(temp + float(rng.uniform(0, 1)), 1)),
                bar,
                str(rain),
                str(round(rain * float(rng.uniform(0.5, 1.5)), 2)),
                "0.0", "0.0",
                in_temp, in_hum, in_dew, in_heat,
                emc, density, "119", "1", "100.0", "60",
            ]

        lines.append("\t".join(row))

    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def _davis_to_pipeline_csv(davis_path: Path, csv_path: Path):
    """Replicates Step 0 from generate_raw_memory_meteo.py."""
    raw   = davis_path.read_text(encoding="utf-8", errors="replace")
    lines = [l for l in raw.splitlines()[2:] if l.strip()]

    rows = []
    for line in lines:
        parts = line.split("\t")
        while len(parts) < len(_DAVIS_COLS):
            parts.append("---")
        rows.append([p.strip() for p in parts[: len(_DAVIS_COLS)]])

    df = pd.DataFrame(rows, columns=_DAVIS_COLS)

    def _parse_row_dt(row):
        try:
            d, m, y = row["Date"].split("/")
            hour = _parse_davis_time(row["Time"])
            return pd.Timestamp(year=2000 + int(y), month=int(m), day=int(d), hour=hour)
        except Exception:
            return pd.NaT

    df["_dt"] = df.apply(_parse_row_dt, axis=1)
    df = df.dropna(subset=["_dt"]).sort_values("_dt").reset_index(drop=True)

    def _to_num(s: pd.Series) -> pd.Series:
        return pd.to_numeric(s.replace(["---", "------", ""], np.nan), errors="coerce")

    out = pd.DataFrame({
        "date":             df["_dt"].dt.strftime("%Y-%m-%d"),
        "time":             df["_dt"].dt.strftime("%H:%M"),
        "Temp Out - Ind":   _to_num(df["Temp Out"]),
        "Hum Out - Ind":    _to_num(df["Out Hum"]),
        "Wind Speed - Ind": _to_num(df["Wind Speed"]),
        "Wind Dir":         df["Wind Dir"].map(_CARDINAL_DEG),
        "Press - Ind":      _to_num(df["Bar"]),
        "Rain - mm":        _to_num(df["Rain"]),
    })
    out.to_csv(str(csv_path), sep=";", index=False)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def reconstruction():
    _make_davis_txt(DAVIS_TXT)
    _davis_to_pipeline_csv(DAVIS_TXT, PIPELINE_CSV)

    extrapolator.extrapolate(str(PIPELINE_CSV), n_hours=5, wind_dir_columns=["Wind Dir"])
    r_imp = imputer.impute(
        str(EXTRAP_PARQUET),
        method="temporal",
        target_columns=[
            "temp out - ind", "hum out - ind",
            "wind speed - ind", "press - ind", "rain - mm",
        ],
    )

    result = skill.reconstruct(
        original_path=str(DAVIS_TXT),
        processed_path=r_imp["output_path"],
        output_dir=str(OUTPUT_DIR),
        equipment_code="TEST",
        random_state=0,
    )
    yield result

    for p in OUTPUT_DIR.glob("*.txt"):
        p.unlink()
    if OUTPUT_DIR.exists():
        OUTPUT_DIR.rmdir()
    for p in [DAVIS_TXT, PIPELINE_CSV, EXTRAP_PARQUET, IMPUTED_PARQUET]:
        if p.exists():
            p.unlink()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_output(reconstruction) -> tuple[list[str], list[list[str]]]:
    text  = Path(reconstruction["output_path"]).read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if l.strip()]
    return lines[:2], [l.split("\t") for l in lines[2:]]


_COL = {name: idx for idx, name in enumerate(_DAVIS_COLS)}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMemoriaRawMeteo:

    def test_returns_ok(self, reconstruction):
        assert reconstruction["status"] == "ok"

    def test_output_file_exists(self, reconstruction):
        assert Path(reconstruction["output_path"]).exists()

    def test_total_rows(self, reconstruction):
        assert reconstruction["total_rows"] == N_HOURS

    def test_reconstructed_and_original_counts(self, reconstruction):
        assert reconstruction["reconstructed_rows"] == N_GAP
        assert reconstruction["original_rows"] == N_ORIGINAL

    def test_counts_sum_to_total(self, reconstruction):
        assert (
            reconstruction["reconstructed_rows"] + reconstruction["original_rows"]
            == reconstruction["total_rows"]
        )

    def test_two_header_rows(self, reconstruction):
        headers, _ = _read_output(reconstruction)
        assert len(headers) == 2

    def test_tab_delimited(self, reconstruction):
        headers, _ = _read_output(reconstruction)
        assert "\t" in headers[0]

    def test_column_count_per_row(self, reconstruction):
        _, data = _read_output(reconstruction)
        for row in data:
            assert len(row) == len(_DAVIS_COLS)

    def test_date_format_D_MM_YY(self, reconstruction):
        _, data = _read_output(reconstruction)
        for row in data:
            parts = row[_COL["Date"]].split("/")
            assert len(parts) == 3
            assert len(parts[2]) == 2  # 2-digit year

    def test_time_format_suffix(self, reconstruction):
        _, data = _read_output(reconstruction)
        for row in data:
            t = row[_COL["Time"]]
            assert t.endswith(" a") or t.endswith(" p"), f"Unexpected time: {t!r}"

    def test_reconstructed_rows_temp_not_missing(self, reconstruction):
        _, data = _read_output(reconstruction)
        for row in data[GAP_START:GAP_END]:
            assert row[_COL["Temp Out"]] != "---"

    def test_original_rows_temp_not_missing(self, reconstruction):
        _, data = _read_output(reconstruction)
        for row in data[:GAP_START]:
            assert row[_COL["Temp Out"]] != "---"

    def test_hi_temp_greater_than_out(self, reconstruction):
        _, data = _read_output(reconstruction)
        for row in data[GAP_START:GAP_END]:
            assert float(row[_COL["Hi Temp"]]) > float(row[_COL["Temp Out"]])

    def test_low_temp_less_than_out(self, reconstruction):
        _, data = _read_output(reconstruction)
        for row in data[GAP_START:GAP_END]:
            assert float(row[_COL["Low Temp"]]) < float(row[_COL["Temp Out"]])

    def test_wind_dir_is_valid_cardinal(self, reconstruction):
        valid = set(_CARDINAL_DEG.keys())
        _, data = _read_output(reconstruction)
        for row in data[GAP_START:GAP_END]:
            assert row[_COL["Wind Dir"]] in valid

    def test_hi_dir_is_valid_cardinal(self, reconstruction):
        valid = set(_CARDINAL_DEG.keys())
        _, data = _read_output(reconstruction)
        for row in data[GAP_START:GAP_END]:
            assert row[_COL["Hi Dir"]] in valid

    def test_heat_dd_always_zero(self, reconstruction):
        _, data = _read_output(reconstruction)
        for row in data:
            assert float(row[_COL["Heat D-D"]]) == 0.0

    def test_cool_dd_always_zero(self, reconstruction):
        _, data = _read_output(reconstruction)
        for row in data:
            assert float(row[_COL["Cool D-D"]]) == 0.0

    def test_date_range_key_present(self, reconstruction):
        assert "date_range" in reconstruction
        assert "–" in reconstruction["date_range"]

    def test_equipment_code_in_filename(self, reconstruction):
        assert "TEST" in Path(reconstruction["output_path"]).name

    def test_rejects_missing_required_columns(self, reconstruction, tmp_path):
        bad = tmp_path / "bad.parquet"
        pd.DataFrame({"date": ["2025-11-01"], "time": ["00:00"], "foo": [1.0]}).to_parquet(bad)
        with pytest.raises(ValueError, match="Required columns"):
            skill.reconstruct(
                original_path=str(DAVIS_TXT),
                processed_path=str(bad),
                output_dir=str(tmp_path),
            )