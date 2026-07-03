"""
Memoria raw Meteo skill
=======================
Reconstructs a lost Davis WeatherLink .txt export from hourly meteorological
data (extrapolate → impute pipeline output).

Follows the same working-hours conventions as MemoriaRawSkill (APNA-370):
  - Memory start is snapped to the latest working hour that is at least
    MIN_HOURS_BEFORE_REAL_START (+ random jitter) before the first real reading.
  - Virtual download time (save_ts) is placed inside working hours.
  - Memory end = floor(save_ts, h) - 1h, so last row and download are coherent.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from skills.extrapolation.extrapolator import ExtrapolationSkill

logger = logging.getLogger(__name__)

# ── Working-hours constants (same as memoria_raw.py) ─────────────────────────
WORKING_HOUR_START = 8
WORKING_HOUR_END   = 18
MIN_HOURS_BEFORE_REAL_START  = 7
MAX_EXTRA_HOURS_BEFORE_START = 6

# ── 16-point wind direction sectors ──────────────────────────────────────────
_WIND_SECTORS: list[tuple[float, float, str]] = [
    (0.0,    11.25,  "N"),
    (11.25,  33.75,  "NNE"),
    (33.75,  56.25,  "NE"),
    (56.25,  78.75,  "ENE"),
    (78.75,  101.25, "E"),
    (101.25, 123.75, "ESE"),
    (123.75, 146.25, "SE"),
    (146.25, 168.75, "SSE"),
    (168.75, 191.25, "S"),
    (191.25, 213.75, "SSW"),
    (213.75, 236.25, "SW"),
    (236.25, 258.75, "WSW"),
    (258.75, 281.25, "W"),
    (281.25, 303.75, "WNW"),
    (303.75, 326.25, "NW"),
    (326.25, 348.75, "NNW"),
    (348.75, 360.0,  "N"),
]

# ── Standard Davis WeatherLink column order ───────────────────────────────────
_DAVIS_COLS = [
    "Date", "Time",
    "Temp Out", "Hi Temp", "Low Temp", "Out Hum", "Dew Pt.",
    "Wind Speed", "Wind Dir", "Wind Run", "Hi Speed", "Hi Dir",
    "Wind Chill", "Heat Index", "THW Index",
    "Bar", "Rain", "Rain Rate", "Heat D-D", "Cool D-D",
    "In Temp", "In Hum", "In Dew", "In Heat",
    "EMC", "Air Density", "Wind Samp", "Wind Tx", "ISS Recept", "Arc. Int.",
]

# ── Davis WeatherLink header rows (hardcoded from reference file) ─────────────
_DAVIS_HEADER_1 = (
    "\t\tTemp\tHi\tLow\tOut\tDew\tWind\tWind\tWind\tHi\tHi\tWind\tHeat\tTHW"
    "\t\t\tRain\tHeat\tCool\tIn \tIn\tIn \tIn \tIn \tIn Air\tWind\tWind\tISS \tArc."
)
_DAVIS_HEADER_2 = (
    "Date\tTime\tOut\tTemp\tTemp\tHum\tPt.\tSpeed\tDir\tRun\tSpeed\tDir"
    "\tChill\tIndex\tIndex\tBar  \tRain\tRate\tD-D \tD-D \tTemp\tHum\tDew"
    "\tHeat\tEMC\tDensity\tSamp\tTx \tRecept\tInt."
)

# ── Cardinal direction → degrees (midpoint of each sector) ───────────────────
_CARDINAL_DEG: dict[str, float] = {
    "N": 0.0,   "NNE": 22.5,  "NE": 45.0,  "ENE": 67.5,
    "E": 90.0,  "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
    "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
}

# ── Hardcoded statistical parameters (derived from Vainillal May 26 reference)
_WR_MIN,  _WR_MAX   = 0.00, 17.70
_WC_MIN,  _WC_MAX   = 4.10, 34.10
_HI_MIN,  _HI_MAX   = 5.50, 47.30
_THW_MIN, _THW_MAX  = 4.10, 47.30
_DEW_MIN, _DEW_MAX  = 2.90, 29.20
_HI_SPD_DELTA_MAX   = 4.50

_FIXED_MEANS: dict[str, float] = {
    "In Temp":    27.1,
    "In Hum":     61.3,
    "In Dew":     18.4,
    "In Heat":    29.6,
    "EMC":        11.6,
    "Air Density": 0.08,
    "Wind Samp":  1383.7,
    "Wind Tx":    1.0,
    "ISS Recept": 99.5,
    "Arc. Int.":  60.0,
}

# ── Column aliases for imputed parquet ────────────────────────────────────────
_PARQUET_ALIASES: dict[str, list[str]] = {
    "temp":  ["Temp Out - Ind", "temp", "Temp Out",    "T_ext",   "temperatura"],
    "hum":   ["Hum Out - Ind",  "hum",  "Out Hum",     "HR_ext",  "humedad"],
    "ws":    ["Wind Speed - Ind","ws",   "Wind Speed",  "VV",      "vel_viento"],
    "wd":    ["Wind Dir",       "wd",   "DV",          "dir_viento"],
    "press": ["Press - Ind",    "press","Bar",          "presion",  "presion_atm"],
    "rain":  ["Rain - mm",      "rain", "Rain",         "lluvia",   "precipitacion"],
}


# ── Module-level helpers ──────────────────────────────────────────────────────

def _latest_working_hour_at_or_before(ts: pd.Timestamp) -> pd.Timestamp:
    """Latest whole-hour timestamp ≤ ts that falls within [WORKING_HOUR_START, WORKING_HOUR_END)."""
    if WORKING_HOUR_START <= ts.hour < WORKING_HOUR_END:
        return ts.normalize() + pd.Timedelta(hours=ts.hour)
    if ts.hour >= WORKING_HOUR_END:
        return ts.normalize() + pd.Timedelta(hours=WORKING_HOUR_END - 1)
    prev_day = ts.normalize() - pd.Timedelta(days=1)
    return prev_day + pd.Timedelta(hours=WORKING_HOUR_END - 1)


def _deg_to_cardinal(degrees: float) -> str:
    d = float(degrees) % 360.0
    for lo, hi, name in _WIND_SECTORS:
        if lo <= d < hi:
            return name
    return "N"


def _parse_davis_time(t: str) -> int:
    """Parse 'H:MM a' or 'H:MM p' → 24-hour int."""
    parts = str(t).strip().split()
    h, _ = map(int, parts[0].split(":"))
    suffix = parts[1].lower() if len(parts) > 1 else "a"
    if suffix == "a":
        h = 0 if h == 12 else h
    else:
        h = h if h == 12 else h + 12
    return h


def _format_time(hour: int) -> str:
    if hour == 0:
        return "12:00 a"
    elif 1 <= hour <= 11:
        return f"{hour}:00 a"
    elif hour == 12:
        return "12:00 p"
    else:
        return f"{hour - 12}:00 p"


def _format_date(dt: pd.Timestamp) -> str:
    return f"{dt.day}/{dt.month:02d}/{str(dt.year)[-2:]}"


def _detect_col(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    for a in aliases:
        if a in df.columns:
            return a
    lower = {c.lower(): c for c in df.columns}
    for a in aliases:
        if a.lower() in lower:
            return lower[a.lower()]
    return None


def _load_pipeline_csv(path: str) -> pd.DataFrame:
    """Load pre-imputation pipeline CSV; attach _datetime column."""
    df = pd.read_csv(path, sep=";")
    date_col = _detect_col(df, ["date", "Date", "fecha"])
    time_col = _detect_col(df, ["time", "Time", "hora"])
    if not date_col or not time_col:
        raise ValueError("No date/time columns found in pipeline CSV.")
    combined = df[date_col].astype(str) + " " + df[time_col].astype(str)
    iso = pd.to_datetime(combined, format="%Y-%m-%d %H:%M", errors="coerce")
    col_dt = pd.to_datetime(combined, format="%d/%m/%Y %H:%M", errors="coerce")
    df["_datetime"] = iso.fillna(col_dt)
    return df


def _load_parquet(path: str) -> tuple[pd.DataFrame, dict[str, str]]:
    """Load imputed parquet; attach _datetime if absent; detect column mapping."""
    df = pd.read_parquet(path)

    if "_datetime" not in df.columns:
        date_col = _detect_col(df, ["date", "Date", "fecha"])
        time_col = _detect_col(df, ["time", "Time", "hora"])
        if not date_col or not time_col:
            raise ValueError("No date/time columns found in parquet.")
        combined = df[date_col].astype(str) + " " + df[time_col].astype(str)
        iso = pd.to_datetime(combined, format="%Y-%m-%d %H:%M", errors="coerce")
        col_fmt = pd.to_datetime(combined, format="%d/%m/%Y %H:%M", errors="coerce")
        df["_datetime"] = iso.fillna(col_fmt)

    col_map: dict[str, str] = {}
    for key, aliases in _PARQUET_ALIASES.items():
        c = _detect_col(df, aliases)
        if c:
            col_map[key] = c
            if key == "wd":
                df[c] = pd.to_numeric(df[c], errors="coerce")

    return df, col_map


# ── Skill ─────────────────────────────────────────────────────────────────────

class MemoriaRawMeteoSkill:

    def reconstruct(
        self,
        original_path: str,
        processed_path: str,
        output_dir: str,
        equipment_code: str = "METEO",
        random_state: Optional[int] = None,
    ) -> dict:
        """
        Reconstruct a lost Davis WeatherLink .txt export.

        Parameters
        ----------
        original_path:
            Pre-imputation pipeline CSV (semicolon-delimited, ISO dates).
            Used to determine the measurement period and identify gap rows.
        processed_path:
            Imputed parquet from the extrapolate → impute pipeline.
        output_dir:
            Directory where the output .txt file is written.
        equipment_code:
            Prefix used in the output filename.
        random_state:
            Seed for reproducible output.
        """
        rng = np.random.default_rng(random_state)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # ── Load inputs ──────────────────────────────────────────────────────
        orig_df = _load_pipeline_csv(original_path)
        proc_df, col_map = _load_parquet(processed_path)

        required = ["temp", "hum", "ws", "wd", "press", "rain"]
        missing_cols = [k for k in required if k not in col_map]
        if missing_cols:
            raise ValueError(
                f"Required columns not found in parquet: {missing_cols}. "
                f"Available: {list(proc_df.columns)}"
            )

        # ── Measurement period from original CSV ──────────────────────────
        orig_dts = orig_df["_datetime"].dropna()
        orig_start = orig_dts.min()
        orig_end   = orig_dts.max()

        # ── Gap rows: timestamps where temp was NaN in the original CSV ───
        temp_col = _detect_col(orig_df, _PARQUET_ALIASES["temp"])
        if temp_col:
            gap_dt_set = set(
                orig_df.loc[
                    pd.to_numeric(orig_df[temp_col], errors="coerce").isna()
                    & orig_df["_datetime"].notna(),
                    "_datetime",
                ]
            )
        else:
            gap_dt_set = set()

        # ── Index ALL parquet rows for fast lookup ────────────────────────
        proc_indexed = (
            proc_df[proc_df["_datetime"].notna()]
            .drop_duplicates(subset=["_datetime"])
            .set_index("_datetime")
            .sort_index()
        )

        # Wind direction fallback pool (non-NaN wd values)
        wd_col = col_map["wd"]
        wd_pool = proc_df[wd_col].dropna().values
        if len(wd_pool) == 0:
            wd_pool = np.array([0.0])

        # ── Working-hours memory bounds ───────────────────────────────────
        extra_h = int(rng.integers(0, MAX_EXTRA_HOURS_BEFORE_START + 1))
        margin_target = orig_start - pd.Timedelta(hours=MIN_HOURS_BEFORE_REAL_START + extra_h)
        mem_start = _latest_working_hour_at_or_before(margin_target)

        rand_min = int(rng.integers(0, 60))
        rand_sec = int(rng.integers(0, 60))
        candidate_save = proc_indexed.index.max() + pd.Timedelta(hours=1)
        if candidate_save.hour < WORKING_HOUR_START:
            save_ts = candidate_save.normalize() + pd.Timedelta(
                hours=WORKING_HOUR_START, minutes=rand_min, seconds=rand_sec
            )
        elif candidate_save.hour >= WORKING_HOUR_END:
            next_day = candidate_save.normalize() + pd.Timedelta(days=1)
            save_ts = next_day + pd.Timedelta(
                hours=WORKING_HOUR_START, minutes=rand_min, seconds=rand_sec
            )
        else:
            save_ts = candidate_save + pd.Timedelta(minutes=rand_min % 30, seconds=rand_sec)
        mem_end = save_ts.floor("h") - pd.Timedelta(hours=1)

        # ── Build output rows ─────────────────────────────────────────────
        all_timestamps = pd.date_range(mem_start, mem_end, freq="h")
        out_rows: list[dict] = []
        reconstructed_count = 0
        padding_before_count = 0
        padding_after_count  = 0

        for dt in all_timestamps:
            is_padding = dt < orig_start or dt > orig_end
            is_gap     = dt in gap_dt_set
            is_in_proc = dt in proc_indexed.index

            if is_in_proc:
                prow = proc_indexed.loc[dt]
                temp = float(prow[col_map["temp"]])
                hum  = float(prow[col_map["hum"]])
                ws   = float(prow[col_map["ws"]])
                wd_val = prow[col_map["wd"]]
                wd = float(rng.choice(wd_pool)) if pd.isna(wd_val) else float(wd_val)
                pr   = float(prow[col_map["press"]])
                rain = float(prow[col_map["rain"]])
            else:
                # Hot-deck for timestamps outside the imputed parquet range
                temp = float(ExtrapolationSkill._hot_deck_draw(proc_df, col_map["temp"], dt.hour, False))
                hum  = float(ExtrapolationSkill._hot_deck_draw(proc_df, col_map["hum"],  dt.hour, False))
                ws   = float(ExtrapolationSkill._hot_deck_draw(proc_df, col_map["ws"],   dt.hour, False))
                wd   = float(ExtrapolationSkill._hot_deck_draw(proc_df, col_map["wd"],   dt.hour, True))
                pr   = float(ExtrapolationSkill._hot_deck_draw(proc_df, col_map["press"],dt.hour, False))
                rain = float(ExtrapolationSkill._hot_deck_draw(proc_df, col_map["rain"], dt.hour, False))

            if is_padding or is_gap or not is_in_proc:
                reconstructed_count += 1
            if dt < orig_start:
                padding_before_count += 1
            elif dt > orig_end:
                padding_after_count += 1

            row: dict[str, str] = {
                "Date":       _format_date(dt),
                "Time":       _format_time(dt.hour),
                "Temp Out":   f"{temp:.1f}",
                "Hi Temp":    f"{temp + float(rng.uniform(1.1, 1.7)):.1f}",
                "Low Temp":   f"{temp - float(rng.uniform(1.1, 1.7)):.1f}",
                "Out Hum":    f"{hum:.1f}",
                "Dew Pt.":    f"{float(rng.uniform(_DEW_MIN, _DEW_MAX)):.1f}",
                "Wind Speed": f"{ws:.1f}",
                "Wind Dir":   _deg_to_cardinal(wd),
                "Wind Run":   f"{float(rng.uniform(_WR_MIN, _WR_MAX)):.2f}",
                "Hi Speed":   f"{ws + float(rng.uniform(0.0, _HI_SPD_DELTA_MAX)):.1f}",
                "Hi Dir":     _deg_to_cardinal(
                    (wd + float(rng.uniform(0.0, 33.75))) % 360.0
                ),
                "Wind Chill": f"{float(rng.uniform(_WC_MIN, _WC_MAX)):.1f}",
                "Heat Index": f"{float(rng.uniform(_HI_MIN, _HI_MAX)):.1f}",
                "THW Index":  f"{float(rng.uniform(_THW_MIN, _THW_MAX)):.1f}",
                "Bar":        f"{pr:.1f}",
                "Rain":       f"{rain:.2f}",
                "Rain Rate":  f"{rain:.2f}",
                "Heat D-D":   "0.0",
                "Cool D-D":   "0.0",
            }
            for col, val in _FIXED_MEANS.items():
                row[col] = f"{val:.1f}"

            out_rows.append(row)

        # ── Write output ──────────────────────────────────────────────────
        ts_tag   = f"{mem_start.strftime('%Y%m%d')}_{mem_end.strftime('%Y%m%d')}"
        out_path = out_dir / f"{equipment_code}_{ts_tag}.txt"

        lines_out = [_DAVIS_HEADER_1, _DAVIS_HEADER_2]
        for row in out_rows:
            lines_out.append(
                "\t".join(str(row.get(c, "---")) for c in _DAVIS_COLS)
            )

        out_path.write_text("\r\n".join(lines_out) + "\r\n", encoding="utf-8")

        logger.info(
            "Wrote %d rows (%d original, %d reconstructed [%d pad-before, %d pad-after, %d gap]) → %s",
            len(out_rows),
            len(out_rows) - reconstructed_count,
            reconstructed_count,
            padding_before_count,
            padding_after_count,
            reconstructed_count - padding_before_count - padding_after_count,
            out_path,
        )

        return {
            "status": "ok",
            "output_path": str(out_path),
            "total_rows": len(out_rows),
            "reconstructed_rows": reconstructed_count,
            "original_rows": len(out_rows) - reconstructed_count,
            "padding_before_rows": padding_before_count,
            "padding_after_rows": padding_after_count,
            "save_datetime": str(save_ts),
            "date_range": f"{_format_date(mem_start)} – {_format_date(mem_end)}",
            "measurement_range": f"{_format_date(orig_start)} – {_format_date(orig_end)}",
        }
