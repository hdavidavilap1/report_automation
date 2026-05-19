"""
Imputation skill
================
Handles Excel ingestion, structure validation, and missing-value filling.

Method selection logic (auto mode)
───────────────────────────────────
< 5%  missing  →  temporal   (time-aware linear interpolation, preserves temporal structure)
5–30% missing  →  knn        (K-Nearest Neighbours, good for correlated pollutants)
> 30% missing  →  mice       (Multiple Imputation by Chained Equations, robust for heavy gaps)
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

# These column name fragments are never treated as pollutant values
NON_SENSOR_PATTERNS = [
    "fecha", "date", "hora", "time", "site", "estacion",
    "station", "id", "codigo", "code", "nombre", "name",
]

# Column groups the skill tries to auto-detect
COLUMN_ALIASES = {
    "datetime": ["fecha", "date", "datetime", "timestamp", "fecha_hora"],
    "wind_speed": ["ws", "wind_speed", "velocidad_viento", "vel_viento", "windspeed"],
    "wind_dir":   ["wd", "wind_dir", "wind_direction", "direccion_viento", "dir_viento"],
}


class ImputationSkill:
    # ─────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────

    def ingest(self, file_path: str) -> dict:
        """
        Load an Excel file, validate its structure, and return a data summary.
        Does NOT modify the file.
        """
        path = self._validate_excel_path(file_path)
        df = self._read_excel(path)

        datetime_col = self._detect_col(df, COLUMN_ALIASES["datetime"])
        if datetime_col:
            df[datetime_col] = pd.to_datetime(df[datetime_col], errors="coerce")

        sensor_cols = self._sensor_columns(df)
        missing_stats = self._missing_stats(df, sensor_cols)
        overall_pct = self._overall_missing_pct(df, sensor_cols)

        warnings = self._structure_warnings(df)

        return {
            "status": "ok",
            "file": str(path.resolve()),
            "rows": len(df),
            "columns": list(df.columns),
            "sensor_columns": sensor_cols,
            "datetime_column": datetime_col,
            "date_range": self._date_range(df, datetime_col),
            "missing_by_column": missing_stats,
            "overall_missing_pct": overall_pct,
            "recommended_method": self._select_method(overall_pct),
            "warnings": warnings,
        }

    def impute(
        self,
        file_path: str,
        method: str = "auto",
        target_columns: Optional[list[str]] = None,
    ) -> dict:
        """
        Fill missing values and save the result as a parquet file.
        Returns imputation metadata and the output path.
        """
        path = Path(file_path)
        df = self._read_file(path)

        sensor_cols = target_columns or self._sensor_columns(df)
        self._validate_columns_exist(df, sensor_cols)

        missing_before = self._missing_stats(df, sensor_cols)
        overall_pct = self._overall_missing_pct(df, sensor_cols)

        if method == "auto":
            method = self._select_method(overall_pct)
            logger.info(f"Auto-selected method: '{method}' ({overall_pct:.1f}% missing)")

        df_imputed = self._apply_method(df.copy(), sensor_cols, method)

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

    def _apply_method(self, df: pd.DataFrame, cols: list[str], method: str) -> pd.DataFrame:
        if method in ("temporal", "linear"):
            return self._temporal_impute(df, cols)
        elif method == "knn":
            return self._knn_impute(df, cols)
        elif method == "mice":
            return self._mice_impute(df, cols)
        else:
            raise ValueError(
                f"Unknown method '{method}'. "
                "Choose from: auto, temporal, linear, knn, mice."
            )

    @staticmethod
    def _temporal_impute(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        """Time-aware linear interpolation. Best for small gaps in time series."""
        df[cols] = df[cols].interpolate(method="linear", limit_direction="both")
        return df

    @staticmethod
    def _knn_impute(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        """K-Nearest Neighbours. Good for spatially/cross-correlated pollutants."""
        scaler = StandardScaler()
        scaled = scaler.fit_transform(df[cols].values)
        filled = KNNImputer(n_neighbors=5, weights="distance").fit_transform(scaled)
        df[cols] = scaler.inverse_transform(filled)
        return df

    @staticmethod
    def _mice_impute(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        """Multiple Imputation by Chained Equations. Robust for heavy missingness."""
        scaler = StandardScaler()
        scaled = scaler.fit_transform(df[cols].values)
        filled = IterativeImputer(
            max_iter=10,
            random_state=42,
            initial_strategy="median",
            imputation_order="roman",
        ).fit_transform(scaled)
        df[cols] = scaler.inverse_transform(filled)
        return df

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    @staticmethod
    def _validate_excel_path(file_path: str) -> Path:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if path.suffix.lower() not in (".xlsx", ".xls"):
            raise ValueError(f"Expected .xlsx or .xls, got '{path.suffix}'")
        return path

    @staticmethod
    def _read_excel(path: Path) -> pd.DataFrame:
        df = pd.read_excel(path)
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df

    @staticmethod
    def _read_file(path: Path) -> pd.DataFrame:
        if path.suffix == ".parquet":
            return pd.read_parquet(path)
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
    def _overall_missing_pct(df: pd.DataFrame, cols: list[str]) -> float:
        if not cols:
            return 0.0
        total_cells = df[cols].size
        missing = int(df[cols].isnull().sum().sum())
        return round(missing / max(total_cells, 1) * 100, 2)

    @staticmethod
    def _date_range(df: pd.DataFrame, datetime_col: Optional[str]) -> Optional[dict]:
        if not datetime_col:
            return None
        col = pd.to_datetime(df[datetime_col], errors="coerce")
        if col.isnull().all():
            return None
        delta = col.max() - col.min()
        return {
            "start": str(col.min()),
            "end":   str(col.max()),
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
        for group, candidates in COLUMN_ALIASES.items():
            if not self._detect_col(df, candidates):
                warnings.append(
                    f"Column group '{group}' not detected. "
                    f"Expected one of: {candidates}"
                )
        return warnings
