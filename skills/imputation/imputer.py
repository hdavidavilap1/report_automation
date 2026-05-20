"""
Imputation skill
================
Handles CSV/Excel ingestion, structure validation, and missing-value filling.

Input format (CSV): semicolon-delimited, European decimal (comma), encoding UTF-8 or latin-1.
Input format (Excel): standard .xlsx / .xls.
Columns: date, time, station, component_1, ..., component_9

Method selection logic (auto mode)
───────────────────────────────────
< 5%  missing  →  temporal   (time-aware linear interpolation, preserves temporal structure)
5–30% missing  →  knn        (K-Nearest Neighbours, good for correlated pollutants)
> 30% missing  →  mice       (Multiple Imputation by Chained Equations, robust for heavy gaps)

All methods operate per station to avoid cross-station data leakage.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.experimental import enable_iterative_imputer  # noqa: F401
from sklearn.impute import IterativeImputer, KNNImputer
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# These column name fragments are never treated as sensor values
NON_SENSOR_PATTERNS = [
    "fecha", "date", "hora", "time", "site", "estacion",
    "station", "id", "codigo", "code", "nombre", "name", "sitio",
]

COLUMN_ALIASES = {
    "date":       ["date", "fecha"],
    "time":       ["time", "hora"],
    "station":    ["station", "estacion", "site", "sitio"],
    "datetime":   ["datetime", "timestamp", "fecha_hora"],
    "wind_speed": ["ws", "wind_speed", "velocidad_viento", "vel_viento", "windspeed"],
    "wind_dir":   ["wd", "wind_dir", "wind_direction", "direccion_viento", "dir_viento"],
}


class ImputationSkill:
    # ─────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────

    def ingest(self, file_path: str) -> dict:
        """
        Load a CSV or Excel file, validate its structure, and return a data summary.
        Does NOT modify the file.
        """
        path = self._validate_path(file_path)
        df = self._read_file(path)

        date_col    = self._detect_col(df, COLUMN_ALIASES["date"])
        time_col    = self._detect_col(df, COLUMN_ALIASES["time"])
        station_col = self._detect_col(df, COLUMN_ALIASES["station"])
        datetime_col = self._detect_col(df, COLUMN_ALIASES["datetime"])

        effective_datetime_col = self._build_datetime(df, date_col, time_col, datetime_col)

        sensor_cols  = self._sensor_columns(df)
        missing_stats = self._missing_stats(df, sensor_cols)
        overall_pct  = self._overall_missing_pct(df, sensor_cols)
        warnings     = self._structure_warnings(df)

        result = {
            "status": "ok",
            "file": str(path.resolve()),
            "rows": len(df),
            "columns": list(df.columns),
            "sensor_columns": sensor_cols,
            "date_column": date_col,
            "time_column": time_col,
            "station_column": station_col,
            "date_range": self._date_range(df, effective_datetime_col),
            "missing_by_column": missing_stats,
            "overall_missing_pct": overall_pct,
            "recommended_method": self._select_method(overall_pct),
            "warnings": warnings,
        }

        if station_col:
            result["stations"] = sorted(df[station_col].dropna().unique().tolist())
            result["missing_by_station"] = self._missing_stats_by_station(
                df, sensor_cols, station_col
            )

        return result

    def impute(
        self,
        file_path: str,
        method: str = "auto",
        target_columns: Optional[list[str]] = None,
    ) -> dict:
        """
        Fill missing values and save the result as a parquet file.
        Imputation is applied per station when a station column is detected.
        """
        path = Path(file_path)
        df = self._read_file(path)

        station_col = self._detect_col(df, COLUMN_ALIASES["station"])
        sensor_cols = target_columns or self._sensor_columns(df)
        self._validate_columns_exist(df, sensor_cols)

        missing_before = self._missing_stats(df, sensor_cols)
        overall_pct    = self._overall_missing_pct(df, sensor_cols)

        if method == "auto":
            method = self._select_method(overall_pct)
            logger.info(f"Auto-selected method: '{method}' ({overall_pct:.1f}% missing)")

        df_imputed = self._apply_method(df.copy(), sensor_cols, method, station_col)

        missing_after = self._missing_stats(df_imputed, sensor_cols)
        cells_filled = (
            sum(v["missing"] for v in missing_before.values())
            - sum(v["missing"] for v in missing_after.values())
        )

        output_path = path.with_name(path.stem + "_imputed.parquet")
        df_imputed.to_parquet(output_path, index=False)
        logger.info(f"Saved imputed file: {output_path}")

        return {
            "status": "ok",
            "method_used": method,
            "station_column": station_col,
            "output_path": str(output_path),
            "rows": len(df_imputed),
            "columns_imputed": sensor_cols,
            "cells_filled": cells_filled,
            "missing_before": missing_before,
            "missing_after": missing_after,
        }

    def comparison_report(self, original_path: str, imputed_path: str) -> dict:
        """
        Side-by-side missing-data comparison between original and imputed datasets.
        """
        orig = self._read_file(Path(original_path))
        impl = self._read_file(Path(imputed_path))

        sensor_cols = self._sensor_columns(orig)
        before = self._missing_stats(orig, sensor_cols)
        after  = self._missing_stats(impl, sensor_cols)

        comparison = {}
        for col in sensor_cols:
            b = before.get(col, {"missing": 0, "pct": 0.0})
            a = after.get(col,  {"missing": 0, "pct": 0.0})
            comparison[col] = {
                "missing_before": b["missing"],
                "missing_after":  a["missing"],
                "pct_before": b["pct"],
                "pct_after":  a["pct"],
                "cells_filled": b["missing"] - a["missing"],
            }

        total_before = sum(v["missing_before"] for v in comparison.values())
        total_after  = sum(v["missing_after"]  for v in comparison.values())

        return {
            "status": "ok",
            "rows": len(orig),
            "sensor_columns": sensor_cols,
            "total_cells_filled": total_before - total_after,
            "overall_missing_pct_before": round(total_before / max(orig[sensor_cols].size, 1) * 100, 2),
            "overall_missing_pct_after":  round(total_after  / max(impl[sensor_cols].size, 1) * 100, 2),
            "by_column": comparison,
        }

    # ─────────────────────────────────────────
    # Imputation methods
    # ─────────────────────────────────────────

    def _apply_method(
        self,
        df: pd.DataFrame,
        cols: list[str],
        method: str,
        station_col: Optional[str] = None,
    ) -> pd.DataFrame:
        if method in ("temporal", "linear"):
            return self._temporal_impute(df, cols, station_col)
        elif method == "knn":
            return self._knn_impute(df, cols, station_col)
        elif method == "mice":
            return self._mice_impute(df, cols, station_col)
        else:
            raise ValueError(
                f"Unknown method '{method}'. "
                "Choose from: auto, temporal, linear, knn, mice."
            )

    @staticmethod
    def _temporal_impute(
        df: pd.DataFrame, cols: list[str], station_col: Optional[str] = None
    ) -> pd.DataFrame:
        """Time-aware linear interpolation per station. Best for small gaps."""
        if station_col and station_col in df.columns:
            df[cols] = df.groupby(station_col, group_keys=False)[cols].apply(
                lambda g: g.interpolate(method="linear", limit_direction="both")
            )
        else:
            df[cols] = df[cols].interpolate(method="linear", limit_direction="both")
        return df

    @staticmethod
    def _knn_impute(
        df: pd.DataFrame, cols: list[str], station_col: Optional[str] = None
    ) -> pd.DataFrame:
        """K-Nearest Neighbours per station. Uses cross-component correlation."""
        if station_col and station_col in df.columns:
            for grp_idx in df.groupby(station_col).groups.values():
                data = df.loc[grp_idx, cols].values
                scaler = StandardScaler()
                scaled = scaler.fit_transform(data)
                filled = KNNImputer(n_neighbors=5, weights="distance").fit_transform(scaled)
                df.loc[grp_idx, cols] = scaler.inverse_transform(filled)
        else:
            scaler = StandardScaler()
            scaled = scaler.fit_transform(df[cols].values)
            filled = KNNImputer(n_neighbors=5, weights="distance").fit_transform(scaled)
            df[cols] = scaler.inverse_transform(filled)
        return df

    @staticmethod
    def _mice_impute(
        df: pd.DataFrame, cols: list[str], station_col: Optional[str] = None
    ) -> pd.DataFrame:
        """Multiple Imputation by Chained Equations per station. Robust for heavy gaps."""
        imputer = IterativeImputer(
            max_iter=10,
            random_state=42,
            initial_strategy="median",
            imputation_order="roman",
        )
        if station_col and station_col in df.columns:
            for grp_idx in df.groupby(station_col).groups.values():
                data = df.loc[grp_idx, cols].values
                scaler = StandardScaler()
                scaled = scaler.fit_transform(data)
                filled = imputer.fit_transform(scaled)
                df.loc[grp_idx, cols] = scaler.inverse_transform(filled)
        else:
            scaler = StandardScaler()
            scaled = scaler.fit_transform(df[cols].values)
            filled = imputer.fit_transform(scaled)
            df[cols] = scaler.inverse_transform(filled)
        return df

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    @staticmethod
    def _validate_path(file_path: str) -> Path:
        path = Path(file_path)
        if path.suffix.lower() not in (".xlsx", ".xls", ".csv"):
            raise ValueError(f"Expected .xlsx, .xls, or .csv, got '{path.suffix}'")
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        return path

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
            return df
        df = pd.read_excel(path)
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df

    @staticmethod
    def _detect_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
        for c in candidates:
            if c in df.columns:
                return c
        return None

    @staticmethod
    def _build_datetime(
        df: pd.DataFrame,
        date_col: Optional[str],
        time_col: Optional[str],
        datetime_col: Optional[str],
    ) -> Optional[str]:
        """Combine separate date+time columns into a single datetime column in-place."""
        if date_col and time_col:
            df["_datetime"] = pd.to_datetime(
                df[date_col].astype(str) + " " + df[time_col].astype(str),
                errors="coerce",
            )
            return "_datetime"
        if datetime_col:
            df[datetime_col] = pd.to_datetime(df[datetime_col], errors="coerce")
            return datetime_col
        return None

    @staticmethod
    def _sensor_columns(df: pd.DataFrame) -> list[str]:
        numeric = df.select_dtypes(include=[np.number]).columns.tolist()
        return [
            c for c in numeric
            if not any(pat in c.lower() for pat in NON_SENSOR_PATTERNS)
        ]

    @staticmethod
    def _validate_columns_exist(df: pd.DataFrame, cols: list[str]) -> None:
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"Columns not found in dataset: {missing}")

    @staticmethod
    def _missing_stats(df: pd.DataFrame, cols: list[str]) -> dict:
        return {
            col: {
                "missing": int(df[col].isnull().sum()),
                "pct": round(df[col].isnull().sum() / max(len(df), 1) * 100, 2),
            }
            for col in cols
        }

    @staticmethod
    def _missing_stats_by_station(
        df: pd.DataFrame, cols: list[str], station_col: str
    ) -> dict:
        result = {}
        for station, grp in df.groupby(station_col):
            result[str(station)] = {
                col: {
                    "missing": int(grp[col].isnull().sum()),
                    "pct": round(grp[col].isnull().sum() / max(len(grp), 1) * 100, 2),
                }
                for col in cols
            }
        return result

    @staticmethod
    def _overall_missing_pct(df: pd.DataFrame, cols: list[str]) -> float:
        if not cols:
            return 0.0
        total_cells = df[cols].size
        missing = int(df[cols].isnull().sum().sum())
        return round(missing / max(total_cells, 1) * 100, 2)

    @staticmethod
    def _date_range(df: pd.DataFrame, datetime_col: Optional[str]) -> Optional[dict]:
        if not datetime_col or datetime_col not in df.columns:
            return None
        col = pd.to_datetime(df[datetime_col], errors="coerce")
        if col.isnull().all():
            return None
        delta = col.max() - col.min()
        return {
            "start":   str(col.min()),
            "end":     str(col.max()),
            "n_hours": int(delta.total_seconds() / 3600),
        }

    @staticmethod
    def _select_method(overall_pct: float) -> str:
        if overall_pct < 5:
            return "temporal"
        elif overall_pct <= 30:
            return "knn"
        return "mice"

    def _structure_warnings(self, df: pd.DataFrame) -> list[str]:
        warnings = []

        has_datetime = bool(self._detect_col(df, COLUMN_ALIASES["datetime"]))
        has_date     = bool(self._detect_col(df, COLUMN_ALIASES["date"]))
        has_time     = bool(self._detect_col(df, COLUMN_ALIASES["time"]))

        if not has_datetime and not (has_date and has_time):
            warnings.append(
                "No datetime column detected. Expected a combined datetime column "
                f"({COLUMN_ALIASES['datetime']}) or separate date+time columns "
                f"({COLUMN_ALIASES['date']} + {COLUMN_ALIASES['time']})."
            )

        if not self._detect_col(df, COLUMN_ALIASES["station"]):
            warnings.append(
                f"Station column not detected. Expected one of: {COLUMN_ALIASES['station']}"
            )

        for group in ("wind_speed", "wind_dir"):
            if not self._detect_col(df, COLUMN_ALIASES[group]):
                warnings.append(
                    f"Column group '{group}' not detected. "
                    f"Expected one of: {COLUMN_ALIASES[group]}"
                )

        return warnings
