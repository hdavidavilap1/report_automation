"""
Memoria raw Meteo skill
=======================
Reconstructs a lost Davis WeatherLink .txt export from hourly meteorological
data (extrapolate → impute pipeline output).
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 16-point wind direction sectors
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

# Standard Davis WeatherLink column order
_DAVIS_COLS = [
    "Date", "Time",
    "Temp Out", "Hi Temp", "Low Temp", "Out Hum", "Dew Pt.",
    "Wind Speed", "Wind Dir", "Wind Run", "Hi Speed", "Hi Dir",
    "Wind Chill", "Heat Index", "THW Index",
    "Bar", "Rain", "Rain Rate", "Heat D-D", "Cool D-D",
    "In Temp", "In Hum", "In Dew", "In Heat",
    "EMC", "Air Density", "Wind Samp", "Wind Tx", "ISS Recept", "Arc. Int.",
]

# Columns whose mean fills reconstructed rows ("las demás")
_MEAN_COLS = [
    "In Temp", "In Hum", "In Dew", "In Heat",
    "EMC", "Air Density", "Wind Samp", "Wind Tx", "ISS Recept", "Arc. Int.",
]

# Cardinal direction → degrees (midpoint of each 16-point sector)
_CARDINAL_DEG: dict[str, float] = {
    "N": 0.0,   "NNE": 22.5,  "NE": 45.0,  "ENE": 67.5,
    "E": 90.0,  "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
    "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
}

# Column aliases for imputed parquet
_PARQUET_ALIASES: dict[str, list[str]] = {
    "temp":  ["Temp Out - Ind", "temp", "Temp Out",    "T_ext",   "temperatura"],
    "hum":   ["Hum Out - Ind",  "hum",  "Out Hum",     "HR_ext",  "humedad"],
    "ws":    ["Wind Speed - Ind","ws",   "Wind Speed",  "VV",      "vel_viento"],
    "wd":    ["Wind Dir",       "wd",   "DV",          "dir_viento"],
    "press": ["Press - Ind",    "press","Bar",          "presion",  "presion_atm"],
    "rain":  ["Rain - mm",      "rain", "Rain",         "lluvia",   "precipitacion"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    """D/MM/YY — no leading zero on day."""
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


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.replace(["---", "------", "", "nan"], np.nan), errors="coerce"
    )


def _load_davis(path: str) -> tuple[pd.DataFrame, list[str]]:
    """
    Load a Davis WeatherLink .txt export.
    All values are kept as strings; a _datetime column is added.
    Returns (df, [header_line1, header_line2]).
    """
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    header_lines = lines[:2]

    rows = []
    for line in lines[2:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        while len(parts) < len(_DAVIS_COLS):
            parts.append("---")
        rows.append([p.strip() for p in parts[: len(_DAVIS_COLS)]])

    df = pd.DataFrame(rows, columns=_DAVIS_COLS)

    dts: list[pd.Timestamp] = []
    for _, row in df.iterrows():
        try:
            d, m, y = str(row["Date"]).strip().split("/")
            hour = _parse_davis_time(row["Time"])
            dts.append(
                pd.Timestamp(year=2000 + int(y), month=int(m), day=int(d), hour=hour)
            )
        except Exception:
            dts.append(pd.NaT)
    df["_datetime"] = dts

    return df, header_lines


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
            # Wind direction may be stored as str dtype (str-encoded floats) — force numeric
            if key == "wd":
                df[c] = pd.to_numeric(df[c], errors="coerce")

    return df, col_map


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------

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
            Original Davis WeatherLink .txt file (may contain '---' gaps).
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
        orig_df, header_lines = _load_davis(original_path)
        proc_df, col_map = _load_parquet(processed_path)

        required = ["temp", "hum", "ws", "wd", "press", "rain"]
        missing_cols = [k for k in required if k not in col_map]
        if missing_cols:
            raise ValueError(
                f"Required columns not found in parquet: {missing_cols}. "
                f"Available: {list(proc_df.columns)}"
            )

        # ── Date range from original file ─────────────────────────────────
        orig_valid_dts = orig_df.loc[orig_df["_datetime"].notna(), "_datetime"]
        orig_start = orig_valid_dts.min()
        orig_end   = orig_valid_dts.max()

        proc_df = (
            proc_df[
                proc_df["_datetime"].notna()
                & (proc_df["_datetime"] >= orig_start)
                & (proc_df["_datetime"] <= orig_end)
            ]
            .sort_values("_datetime")
            .reset_index(drop=True)
        )

        # ── Statistics from valid original rows ───────────────────────────
        orig_temp_num = _to_num(orig_df["Temp Out"])
        valid_mask = orig_temp_num.notna() & orig_df["_datetime"].notna()
        valid_orig = orig_df[valid_mask].copy()

        if len(valid_orig) == 0:
            raise ValueError(
                "Original Davis file has no valid rows (all Temp Out are '---')."
            )

        def _rng_minmax(col: str) -> tuple[float, float]:
            s = _to_num(valid_orig[col]).dropna()
            return (float(s.min()), float(s.max())) if len(s) > 0 else (0.0, 1.0)

        def _pool(col: str) -> np.ndarray:
            return _to_num(valid_orig[col]).dropna().values

        wr_min,  wr_max  = _rng_minmax("Wind Run")
        wc_min,  wc_max  = _rng_minmax("Wind Chill")
        hi_min,  hi_max  = _rng_minmax("Heat Index")
        thw_min, thw_max = _rng_minmax("THW Index")
        dew_pool         = _pool("Dew Pt.")
        rr_pool          = _pool("Rain Rate")

        # Wind direction pool: convert cardinal strings from original to degrees
        wd_deg_pool = np.array([
            _CARDINAL_DEG[v]
            for v in valid_orig["Wind Dir"]
            if isinstance(v, str) and v in _CARDINAL_DEG
        ], dtype=float)
        if len(wd_deg_pool) == 0:
            wd_deg_pool = np.array([0.0])

        ws_s    = _to_num(valid_orig["Wind Speed"])
        his_s   = _to_num(valid_orig["Hi Speed"])
        delta_s = (his_s - ws_s).dropna()
        hi_delta_max = float(delta_s.quantile(0.95)) if len(delta_s) >= 5 else 2.0
        hi_delta_max = max(hi_delta_max, 0.3)

        means: dict[str, float] = {}
        for col in _MEAN_COLS:
            s = _to_num(orig_df[col]).dropna()
            means[col] = float(s.mean()) if len(s) > 0 else 0.0

        # ── Index original for fast lookup ────────────────────────────────
        orig_nodup = (
            orig_df.dropna(subset=["_datetime"])
            .drop_duplicates(subset=["_datetime"])
        )
        orig_idx   = orig_nodup.set_index("_datetime")
        valid_dt_set = set(valid_orig["_datetime"].dropna())

        # ── Build output rows ─────────────────────────────────────────────
        out_rows: list[dict] = []
        reconstructed_count = 0

        for _, prow in proc_df.iterrows():
            dt = prow["_datetime"]
            if pd.isna(dt):
                continue

            row: dict[str, str] = {
                "Date": _format_date(dt),
                "Time": _format_time(dt.hour),
            }

            if dt in valid_dt_set:
                # Keep all original string values unchanged
                orow = orig_idx.loc[dt]
                for col in _DAVIS_COLS[2:]:
                    v = orow[col]
                    row[col] = (
                        "---"
                        if (isinstance(v, float) and pd.isna(v))
                        else str(v)
                    )
            else:
                reconstructed_count += 1

                temp = float(prow[col_map["temp"]])
                hum  = float(prow[col_map["hum"]])
                ws   = float(prow[col_map["ws"]])
                wd   = float(prow[col_map["wd"]])
                pr   = float(prow[col_map["press"]])
                rain = float(prow[col_map["rain"]])

                row["Temp Out"]   = f"{temp:.1f}"
                row["Hi Temp"]    = f"{temp + float(rng.uniform(1.1, 1.7)):.1f}"
                row["Low Temp"]   = f"{temp - float(rng.uniform(1.1, 1.7)):.1f}"
                row["Out Hum"]    = f"{hum:.1f}"
                row["Dew Pt."]    = (
                    f"{float(rng.choice(dew_pool)):.1f}"
                    if len(dew_pool) > 0 else "---"
                )
                row["Wind Speed"] = f"{ws:.1f}"
                row["Wind Dir"]   = _deg_to_cardinal(wd)
                row["Wind Run"]   = f"{float(rng.uniform(wr_min, wr_max)):.2f}"
                row["Hi Speed"]   = f"{ws + float(rng.uniform(0.0, hi_delta_max)):.1f}"
                row["Hi Dir"]     = _deg_to_cardinal(
                    (wd + float(rng.uniform(0.0, 33.75))) % 360.0
                )
                row["Wind Chill"] = f"{float(rng.uniform(wc_min, wc_max)):.1f}"
                row["Heat Index"] = f"{float(rng.uniform(hi_min, hi_max)):.1f}"
                row["THW Index"]  = f"{float(rng.uniform(thw_min, thw_max)):.1f}"
                row["Bar"]        = f"{pr:.1f}"
                row["Rain"]       = f"{rain:.2f}"
                row["Rain Rate"]  = (
                    f"{float(rng.choice(rr_pool)):.2f}"
                    if len(rr_pool) > 0 else "0.00"
                )
                row["Heat D-D"]   = "0.0"
                row["Cool D-D"]   = "0.0"

                for col in _MEAN_COLS:
                    v = means[col]
                    row[col] = f"{v:.1f}" if not pd.isna(v) else "---"

            out_rows.append(row)

        # ── Write output ──────────────────────────────────────────────────
        ts_tag   = f"{orig_start.strftime('%Y%m%d')}_{orig_end.strftime('%Y%m%d')}"
        out_path = out_dir / f"{equipment_code}_{ts_tag}.txt"

        lines_out = [
            header_lines[0] if len(header_lines) > 0 else "",
            header_lines[1] if len(header_lines) > 1 else "",
        ]
        for row in out_rows:
            lines_out.append(
                "\t".join(str(row.get(c, "---")) for c in _DAVIS_COLS)
            )

        out_path.write_text("\r\n".join(lines_out) + "\r\n", encoding="utf-8")

        logger.info(
            "Wrote %d rows (%d original, %d reconstructed) → %s",
            len(out_rows),
            len(out_rows) - reconstructed_count,
            reconstructed_count,
            out_path,
        )

        return {
            "status": "ok",
            "output_path": str(out_path),
            "total_rows": len(out_rows),
            "reconstructed_rows": reconstructed_count,
            "original_rows": len(out_rows) - reconstructed_count,
            "date_range": f"{_format_date(orig_start)} – {_format_date(orig_end)}",
        }