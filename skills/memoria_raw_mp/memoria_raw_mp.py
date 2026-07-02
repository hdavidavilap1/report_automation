"""
Memoria raw MP skill
====================
Generates per-minute .dat files (L and M) for a GRIMM 180C-compatible PM
instrument from hourly input data (output of extrapolate → impute pipeline).

- M file: per-minute PM10 / PM2.5 / PM1 measurements (PM1 always 0.0)
- L file: per-minute operational log (P, Year, Month, Day, Hour, Minute,
  Loc, GF, Error, Qbatt, Im, UeL, UE4, UE3, UE2, UE1, IV)

Disaggregation: for each hourly value `v`, 60 per-minute values are
generated with Gaussian noise, then scaled so mean(minute_values) == v
exactly (force-exact-mean). Values are clamped to ≥ 0.

L-file field rules:
  Constants : Loc=100, GF=0, Error=130, UeL=134, UE4=0, UE1=0, IV=0
  Random    : Qbatt ∈ [41,43], Im ∈ [41,44], UE3 ∈ [0,0], UE2 ∈ [59,124]
  (ranges for random fields derived from the reference instrument file)

Output filename convention:
  EO {equipment_code}_{station_id}_{YYYY-MM-DD}_{HH-MM}-{M|L}.dat
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from skills.memoria_raw.memoria_raw import MemoriaRawSkill, COLUMN_ALIASES

logger = logging.getLogger(__name__)

# L-file field values — constants and random ranges (from reference GRIMM 180C)
_L_LOC = 100
_L_GF = 0
_L_ERROR = 130
_L_QBATT_RANGE = (41, 43)    # random int
_L_IM_RANGE = (41, 44)       # random int
_L_UEL = 134                 # constant
_L_UE4 = 0                   # constant
_L_UE3_RANGE = (0, 0)        # random int; reference min=max=0 → always 0
_L_UE2_RANGE = (59, 124)     # random int
_L_UE1 = 0                   # constant
_L_IV = 0                    # constant

_M_HEADER = (
    "<Header>\r\n"
    "User name:  \r\n"
    "Location:  \r\n"
    "# of Location:1\r\n"
    "Model: 180C\r\n"
    "Serial No.: {serial_no}\r\n"
    "Firmware revision: 7.80E\r\n"
    "Software revision: 1178 V8-20 (17-06-2021)\r\n"
    "Unit:  ug/m3\r\n"
    "C-factor:  Enviro\r\n"
    "Comment:  \r\n"
    "\r\n"
    "offline data\r\n"
    "\r\n"
    "<Data>\r\n"
)

_L_HEADER = (
    "<Header>\r\n"
    "User name:  \r\n"
    "Location:  \r\n"
    "# of Location:1\r\n"
    "Model: 180C\r\n"
    "Serial No.: {serial_no}\r\n"
    "Firmware revision: 7.80E\r\n"
    "Software revision: 1178 V8-20 (17-06-2021)\r\n"
    "Unit: log data\r\n"
    "C-factor:  Enviro\r\n"
    "Comment:  \r\n"
    "\r\n"
    "offline data\r\n"
    "\r\n"
    "analog inputs: Input 1:\toffset: 0.00\tfactor: 0.00\tconnected: no;"
    "Input 2:\toffset: 0.00\tfactor: 0.00\tconnected: no;"
    "Input 3:\toffset: 0.00\tfactor: 0.00\tconnected: no;"
    "Input 4:\toffset: 0.00\tfactor: 0.00\tconnected: no\r\n"
    "<Data>\r\n"
)

_M_COL_HEADER = (
    "[d&t31/12/2035 11:50:55]\tPM10 [ug/m3]\tPM2.5 [ug/m3]\tPM1 [ug/m3]\r\n"
)

_L_COL_HEADER = (
    "[d&t31/12/2035 11:50:55]\tP\tYear\tMonth\tDay\tHour\tMinute\t"
    "Loc\tGF\tError\tQbatt\tIm\tUeL\tUE4\tUE3\tUE2\tUE1\tIV\t\r\n"
)


def _fmt_dt(ts: pd.Timestamp) -> str:
    """D/M/YYYY H:MM:SS — no leading zeros on day, month, or hour."""
    return f"{ts.day}/{ts.month}/{ts.year} {ts.hour}:{ts.minute:02d}:{ts.second:02d}"


def _disaggregate(v: float, n: int, noise_std: float, rng: np.random.Generator) -> np.ndarray:
    """Return `n` values ≥ 0 whose mean equals `v` exactly."""
    if v <= 0.0:
        return np.zeros(n)
    raw = rng.normal(v, v * noise_std, size=n)
    raw = np.maximum(raw, 0.0)
    mean_raw = raw.mean()
    if mean_raw > 0.0:
        return raw * (v / mean_raw)
    return np.full(n, v)  # fallback: all equal to hourly mean


def _load_mixed(path: str) -> pd.DataFrame:
    """Load CSV or parquet and attach _datetime, handling both ISO and Colombian dates.

    Parquet files produced by ExtrapolationSkill mix ISO dates (YYYY-MM-DD) on
    padding rows with the original Colombian format (D/MM/YYYY) on real rows.
    Using `format='mixed', dayfirst=True` mis-parses ISO dates like 2025-08-04
    as 2025-04-08. Instead: try ISO first, fill remaining NaTs with the Colombian
    format.
    """
    helper = MemoriaRawSkill()
    df = MemoriaRawSkill._read_file(Path(path))
    date_col = helper._detect_col(df, COLUMN_ALIASES["date"])
    time_col = helper._detect_col(df, COLUMN_ALIASES["time"])
    if not date_col or not time_col:
        raise ValueError("Could not find date/time columns.")
    df = df.copy()
    combined = df[date_col].astype(str) + " " + df[time_col].astype(str)
    iso_dt = pd.to_datetime(combined, format="%Y-%m-%d %H:%M", errors="coerce")
    col_dt = pd.to_datetime(combined, format="%d/%m/%Y %H:%M", errors="coerce")
    df["_datetime"] = iso_dt.fillna(col_dt)
    return df


class MemoriaRawMPSkill:

    def reconstruct(
        self,
        original_path: str,
        processed_path: str,
        pm10_column: str,
        pm25_column: str,
        output_dir: str,
        station: Optional[str] = None,
        equipment_code: str = "18A20020",
        station_id: str = "001",
        serial_no: str = "8HG20020",
        noise_std: float = 0.15,
        random_state: Optional[int] = None,
    ) -> dict:
        """
        Disaggregate hourly PM data to per-minute M and L `.dat` files.

        Parameters
        ----------
        original_path:
            Pre-imputation hourly file (CSV or parquet). Used only to determine
            the real measurement window start/end.
        processed_path:
            Output of extrapolate → impute pipeline (parquet or CSV). Provides
            all hourly rows to disaggregate (real window + padding).
        pm10_column:
            Column name in `processed_path` holding hourly PM10 (µg/m³).
        pm25_column:
            Column name in `processed_path` holding hourly PM2.5 (µg/m³).
        output_dir:
            Directory where the two `.dat` files are written.
        station:
            Filter both inputs to a single station value when the file holds
            multiple stations. Required if more than one station is present.
        equipment_code:
            Instrument serial-number prefix used in the filename (e.g. 18A20020).
        station_id:
            Station identifier used in the filename (e.g. 001).
        serial_no:
            Value written into the "Serial No." header field.
        noise_std:
            Fraction of the hourly mean used as the Gaussian noise standard
            deviation during disaggregation (default 0.15 = ±15 %).
        random_state:
            Seed for reproducible output.

        Returns
        -------
        dict with keys: status, segments (list), total_segments, total_minutes,
        real_window_start, real_window_end.
        Each segment dict: m_path, l_path, minutes, hourly_rows, start, end.
        """
        rng = np.random.default_rng(random_state)

        helper = MemoriaRawSkill()
        orig_df = _load_mixed(original_path)
        proc_df = _load_mixed(processed_path)
        orig_df, proc_df = helper._filter_station(orig_df, proc_df, station)
        proc_df = proc_df.sort_values("_datetime").reset_index(drop=True)

        real_start = orig_df["_datetime"].min()
        real_end = orig_df["_datetime"].max()

        pm10_col = helper._detect_col(proc_df, [pm10_column, pm10_column.lower()])
        pm25_col = helper._detect_col(proc_df, [pm25_column, pm25_column.lower()])
        if pm10_col is None:
            raise ValueError(f"Column '{pm10_column}' not found in processed data.")
        if pm25_col is None:
            raise ValueError(f"Column '{pm25_column}' not found in processed data.")

        # Identify gap hours: NaN in original data means the equipment was off.
        # Each consecutive gap block splits the recording into a separate file.
        orig_pm10 = helper._detect_col(orig_df, [pm10_column, pm10_column.lower()])
        orig_pm25 = helper._detect_col(orig_df, [pm25_column, pm25_column.lower()])
        nan_mask = pd.Series(False, index=orig_df.index)
        if orig_pm10:
            nan_mask |= orig_df[orig_pm10].isna()
        if orig_pm25:
            nan_mask |= orig_df[orig_pm25].isna()
        nan_timestamps = set(orig_df.loc[nan_mask, "_datetime"].values)

        # Find consecutive NaN blocks in proc_df as (first_idx, last_idx) pairs.
        # proc_df is reset-indexed (0, 1, 2, …) and sorted by time.
        is_nan = proc_df["_datetime"].isin(nan_timestamps)
        nan_idxs = proc_df.index[is_nan].tolist()
        gap_blocks: list[tuple[int, int]] = []
        if nan_idxs:
            bs, prev = nan_idxs[0], nan_idxs[0]
            for idx in nan_idxs[1:]:
                if idx == prev + 1:
                    prev = idx
                else:
                    gap_blocks.append((bs, prev))
                    bs = prev = idx
            gap_blocks.append((bs, prev))

        # Build segment DataFrames.
        #
        # Physical model: the equipment turns off *within* the first NaN hour of
        # a gap block (that hour's first few minutes belong to the closing segment)
        # and turns back on *within* the last NaN hour (remaining minutes belong
        # to the next opening segment). Middle NaN hours are fully off — skipped.
        # The very first and last hours of the dataset are also partial boundaries.
        #
        # Example — gap [h7, h8, h9]:
        #   Segment N ends inside h7  (minutes 0 → close_min)
        #   h8 is completely skipped
        #   Segment N+1 starts inside h9  (minutes open_min → 59)
        #   Hours h6 and h10 keep all 60 minutes.
        if not gap_blocks:
            segment_dfs = [proc_df]
        else:
            segment_dfs = []
            # Segment 0: rows 0 … first NaN hour of first gap (inclusive)
            segment_dfs.append(
                proc_df.iloc[: gap_blocks[0][0] + 1].reset_index(drop=True)
            )
            for i, (_gstart, gend) in enumerate(gap_blocks):
                start = gend  # opening row = last NaN hour of this gap
                end = (
                    gap_blocks[i + 1][0]  # closing row = first NaN hour of next gap
                    if i + 1 < len(gap_blocks)
                    else len(proc_df) - 1
                )
                segment_dfs.append(
                    proc_df.iloc[start : end + 1].reset_index(drop=True)
                )

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Pre-generate open_min / close_min for every segment so that single-NaN
        # gaps (where both adjacent segments share the same proc_df row) can be
        # fixed to satisfy close_min[i] < open_min[i+1] before writing.
        n_segs = len(segment_dfs)
        open_mins  = [int(rng.integers(0, 60)) for _ in range(n_segs)]
        close_mins = [int(rng.integers(0, 60)) for _ in range(n_segs)]

        for gap_i, (gstart, gend) in enumerate(gap_blocks):
            seg_before = gap_i      # segment whose last row = proc_df[gstart]
            seg_after  = gap_i + 1  # segment whose first row = proc_df[gend]
            if gstart == gend:
                # Same hour is the closing row of seg_before AND the opening row
                # of seg_after → must have close_mins[seg_before] < open_mins[seg_after].
                cm, om = close_mins[seg_before], open_mins[seg_after]
                if cm >= om:
                    # Re-draw: close in first half, open in second half.
                    close_mins[seg_before] = int(rng.integers(0, 29))
                    open_mins[seg_after]   = int(rng.integers(30, 60))

        segment_results = []
        for seg_idx, seg_df in enumerate(segment_dfs):
            n_rows    = len(seg_df)
            open_min  = open_mins[seg_idx]
            close_min = close_mins[seg_idx]
            # Single-row segment where it is also a single-NaN gap is already
            # handled above; handle the edge case of open == close for others.
            if n_rows == 1:
                lo, hi = min(open_min, close_min), max(open_min, close_min)
                if lo == hi:
                    hi = min(lo + 1, 59)
                open_min, close_min = lo, hi

            minute_rows: list[tuple[pd.Timestamp, float, float]] = []
            for row_idx, (_, row) in enumerate(seg_df.iterrows()):
                ts_hour: pd.Timestamp = row["_datetime"]
                v10 = float(row[pm10_col]) if pd.notna(row[pm10_col]) else 0.0
                v25 = float(row[pm25_col]) if pd.notna(row[pm25_col]) else 0.0
                pm10_min = _disaggregate(v10, 60, noise_std, rng)
                pm25_min = _disaggregate(v25, 60, noise_std, rng)

                if n_rows == 1:
                    m_range = range(open_min, close_min + 1)
                elif row_idx == 0:
                    m_range = range(open_min, 60)       # partial: recording starts mid-hour
                elif row_idx == n_rows - 1:
                    m_range = range(0, close_min + 1)   # partial: recording ends mid-hour
                else:
                    m_range = range(60)                 # full hour: all 60 minutes

                for m in m_range:
                    minute_rows.append((
                        ts_hour + pd.Timedelta(minutes=m),
                        pm10_min[m],
                        pm25_min[m],
                    ))

            first_ts = minute_rows[0][0]
            ts_tag = first_ts.strftime("%Y-%m-%d_%H-%M")
            m_path = out_dir / f"EO {equipment_code}_{station_id}_{ts_tag}-M.dat"
            l_path = out_dir / f"EO {equipment_code}_{station_id}_{ts_tag}-L.dat"

            self._write_m(m_path, minute_rows, serial_no)
            self._write_l(l_path, minute_rows, serial_no, rng)

            logger.info(
                "Segment written: %s (%d hours → %d minutes)",
                m_path.name, len(seg_df), len(minute_rows),
            )
            segment_results.append({
                "m_path": str(m_path),
                "l_path": str(l_path),
                "minutes": len(minute_rows),
                "hourly_rows": len(seg_df),
                "start": str(first_ts),
                "end": str(minute_rows[-1][0]),
            })

        return {
            "status": "ok",
            "segments": segment_results,
            "total_segments": len(segment_results),
            "total_minutes": sum(s["minutes"] for s in segment_results),
            "real_window_start": str(real_start),
            "real_window_end": str(real_end),
        }

    @staticmethod
    def _write_m(path: Path, rows: list, serial_no: str) -> None:
        buf = [_M_HEADER.format(serial_no=serial_no), _M_COL_HEADER]
        for ts, pm10, pm25 in rows:
            buf.append(f"{_fmt_dt(ts)}\t{pm10:.1f}\t{pm25:.1f}\t0.0\r\n")
        path.write_text("".join(buf), encoding="utf-8")

    @staticmethod
    def _write_l(
        path: Path,
        rows: list,
        serial_no: str,
        rng: np.random.Generator,
    ) -> None:
        buf = [_L_HEADER.format(serial_no=serial_no), _L_COL_HEADER]
        for i, (ts, _, _) in enumerate(rows):
            p = "PP" if i == 0 else "P"
            yr = ts.year % 100
            qbatt = int(rng.integers(_L_QBATT_RANGE[0], _L_QBATT_RANGE[1] + 1))
            im    = int(rng.integers(_L_IM_RANGE[0],    _L_IM_RANGE[1]    + 1))
            ue3   = int(rng.integers(_L_UE3_RANGE[0],   _L_UE3_RANGE[1]   + 1))
            ue2   = int(rng.integers(_L_UE2_RANGE[0],   _L_UE2_RANGE[1]   + 1))
            buf.append(
                f"{_fmt_dt(ts)}\t{p}\t{yr}\t{ts.month}\t{ts.day}\t"
                f"{ts.hour}\t{ts.minute}\t{_L_LOC}\t{_L_GF}\t{_L_ERROR}\t{qbatt}\t"
                f"{im}\t{_L_UEL}\t{_L_UE4}\t{ue3}\t{ue2}\t{_L_UE1}\t{_L_IV}\t\r\n"
            )
        path.write_text("".join(buf), encoding="utf-8")