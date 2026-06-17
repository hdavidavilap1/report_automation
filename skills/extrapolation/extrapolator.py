"""
Extrapolation skill
===================
Extends a time series n hours before its start (retropolation) and
n hours after its end (forecast) using a hot-deck strategy:

  1. Collect all measurements for the target hour across all days in the sample.
  2. Compute std (circular std for wind direction, regular std otherwise).
  3. Draw one measurement at random as the reference value (hot-deck).
  4. Add a uniform perturbation in [-std/4, +std/4].
  5. Clip to 0 for concentrations; wrap modulo 360 for wind direction.

Operates per station to avoid cross-station leakage.
Wind direction columns are auto-detected (values in [0, 360] with range > 90°)
or supplied explicitly via wind_dir_columns.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Convert object columns to numeric where ≥50% of values parse successfully.
    Handles dot-decimal files (e.g. '1.67') when the CSV was read with decimal=','."""
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().mean() > 0.5:
            df[col] = converted
    return df


NON_SENSOR_PATTERNS = [
    "fecha", "date", "hora", "time", "site", "estacion",
    "station", "id", "codigo", "code", "nombre", "name", "sitio",
]

COLUMN_ALIASES = {
    "date":    ["date", "fecha"],
    "time":    ["time", "hora"],
    "station": ["station", "estacion", "site", "sitio"],
}


class ExtrapolationSkill:

    # ─────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────

    def extrapolate(
        self,
        file_path: str,
        n_hours: int = 10,
        wind_dir_columns: Optional[list[str]] = None,
    ) -> dict:
        """
        Extend the time series n_hours before its start and after its end.
        Saves result as a parquet file next to the input.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        df = self._read_file(path)
        df = self._attach_datetime(df)

        date_col = self._detect_col(df, COLUMN_ALIASES["date"])
        time_col = self._detect_col(df, COLUMN_ALIASES["time"])
        station_col = self._detect_col(df, COLUMN_ALIASES["station"])
        sensor_cols = self._sensor_columns(df)
        wd_cols = wind_dir_columns if wind_dir_columns is not None else self._detect_wind_dir_cols(df, sensor_cols)

        stations = sorted(df[station_col].unique().tolist()) if station_col else [None]

        global_start = df["_datetime"].min()
        global_end = df["_datetime"].max()

        retro_times = pd.date_range(
            global_start - pd.Timedelta(hours=n_hours),
            global_start - pd.Timedelta(hours=1),
            freq="h",
        )
        fore_times = pd.date_range(
            global_end + pd.Timedelta(hours=1),
            global_end + pd.Timedelta(hours=n_hours),
            freq="h",
        )
        new_timestamps = list(retro_times) + list(fore_times)

        new_rows = []
        for station in stations:
            station_df = df[df[station_col] == station] if station_col else df
            for ts in new_timestamps:
                row: dict = {"_datetime": ts, date_col: ts.strftime("%Y-%m-%d"), time_col: ts.strftime("%H:%M")}
                if station_col:
                    row[station_col] = station
                for col in sensor_cols:
                    row[col] = self._hot_deck_draw(station_df, col, ts.hour, col in wd_cols)
                new_rows.append(row)

        extra_df = pd.DataFrame(new_rows)
        sort_keys = ([station_col] if station_col else []) + ["_datetime"]
        result_df = (
            pd.concat([df, extra_df], ignore_index=True)
            .sort_values(sort_keys)
            .reset_index(drop=True)
            .drop(columns=["_datetime"])
        )

        output_path = path.with_name(path.stem + "_extrapolated.parquet")
        result_df.to_parquet(output_path, index=False)
        logger.info(f"Saved extrapolated file: {output_path}")

        return {
            "status": "ok",
            "output_path": str(output_path),
            "original_rows": len(df),
            "rows_added": len(new_rows),
            "total_rows": len(result_df),
            "retropolated_range": {
                "start": str(retro_times[0]),
                "end":   str(retro_times[-1]),
            },
            "forecast_range": {
                "start": str(fore_times[0]),
                "end":   str(fore_times[-1]),
            },
            "stations": [str(s) for s in stations],
            "wind_dir_columns": wd_cols,
        }

    # ─────────────────────────────────────────
    # Hot-deck draw
    # ─────────────────────────────────────────

    @staticmethod
    def _hot_deck_draw(
        df: pd.DataFrame,
        col: str,
        target_hour: int,
        is_circular: bool,
    ) -> float:
        pool = df.loc[df["_datetime"].dt.hour == target_hour, col].dropna()
        if pool.empty:
            pool = df[col].dropna()
        if pool.empty:
            return np.nan

        reference = float(pool.sample(1).iloc[0])

        if is_circular:
            angles_rad = np.deg2rad(pool.values.astype(float))
            R = np.sqrt(np.mean(np.cos(angles_rad)) ** 2 + np.mean(np.sin(angles_rad)) ** 2)
            R = float(np.clip(R, 1e-10, 1 - 1e-10))
            circ_std = np.degrees(np.sqrt(-2 * np.log(R)))
            noise = np.random.uniform(-circ_std / 4, circ_std / 4)
            return float((reference + noise) % 360)

        std = float(pool.std(ddof=1)) if len(pool) > 1 else 0.0
        noise = np.random.uniform(-std / 4, std / 4)
        return float(max(0.0, reference + noise))

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    @staticmethod
    def _read_file(path: Path) -> pd.DataFrame:
        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        if path.suffix.lower() == ".csv":
            try:
                df = pd.read_csv(path, sep=";", decimal=",", encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(path, sep=";", decimal=",", encoding="latin-1")
            df.columns = [str(c).strip().lower() for c in df.columns]
            return _coerce_numeric(df)
        df = pd.read_excel(path)
        df.columns = [str(c).strip().lower() for c in df.columns]
        return _coerce_numeric(df)

    @staticmethod
    def _detect_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
        for c in candidates:
            if c in df.columns:
                return c
        return None

    def _attach_datetime(self, df: pd.DataFrame) -> pd.DataFrame:
        date_col = self._detect_col(df, COLUMN_ALIASES["date"])
        time_col = self._detect_col(df, COLUMN_ALIASES["time"])
        if not date_col or not time_col:
            raise ValueError("Could not find date and time columns to build datetime index.")
        df = df.copy()
        df["_datetime"] = pd.to_datetime(
            df[date_col].astype(str) + " " + df[time_col].astype(str),
            errors="coerce",
        )
        return df

    @staticmethod
    def _sensor_columns(df: pd.DataFrame) -> list[str]:
        numeric = df.select_dtypes(include=[np.number]).columns.tolist()
        return [
            c for c in numeric
            if not any(pat in c.lower() for pat in NON_SENSOR_PATTERNS)
        ]

    @staticmethod
    def _detect_wind_dir_cols(df: pd.DataFrame, sensor_cols: list[str]) -> list[str]:
        wd_cols = []
        for col in sensor_cols:
            vals = df[col].dropna()
            if vals.empty:
                continue
            if vals.min() >= 0 and vals.max() <= 360 and (vals.max() - vals.min()) > 90:
                wd_cols.append(col)
        return wd_cols
