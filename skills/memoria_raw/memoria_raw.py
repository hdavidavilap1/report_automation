"""
Memoria raw skill
==================
Reconstructs a lost APNA-370 raw memory-dump file (`_HA.csv`) from data that has
already gone through extrapolation + imputation, using the analyzer's own
Status/Caution/Alarm bit fields to flag which rows were reconstructed:

  - Alarm bit 6  ("V")  — set on rows, inside the real measurement window, whose
    original reading was missing and had to be filled with a hot-deck draw.
  - Caution bit 32 ("DR") — set on the reconstructed calibration row (the first
    padding-before hour), whose value is the average of the calibration gas
    concentrations.

File format (derived from a real `_HA.csv` / `_HA_COMPILADO.CSV` pair):
  - `;`-delimited, comma-decimal.
  - 3 bracketed header lines, then 2 column-header lines, then data rows.
  - Each data row: Date;Time; then 3x(Unit;Digit;Value) for Component1-3, then
    16 Status bits (15..0), 64 Caution bits (63..0), 64 Alarm bits (63..0).
  - Value = COMPILADO value x 1e6, rounded to 3 significant figures, formatted
    as "[-]D,DDE±EE".
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from skills.extrapolation.extrapolator import ExtrapolationSkill

logger = logging.getLogger(__name__)

COLUMN_ALIASES = {
    "date":    ["date", "fecha"],
    "time":    ["time", "hora"],
    "station": ["station", "estacion", "site", "sitio"],
}

N_STATUS_BITS = 16
N_CAUTION_BITS = 64
N_ALARM_BITS = 64

ALARM_BIT_MISSING = 6
CAUTION_BIT_CALIBRATION = 32

DEFAULT_CALIBRATION_VALUES = [400, 300, 200, 100, 0]


class MemoriaRawSkill:

    # ─────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────

    def reconstruct(
        self,
        original_path: str,
        processed_path: str,
        component_columns: list[str],
        output_path: str,
        station: Optional[str] = None,
        equipment_name: str = "Equipment-1:APNA",
        save_datetime: Optional[str] = None,
        calibration_component: int = 1,
        calibration_values: Optional[list[float]] = None,
        unit_digit: tuple[int, int] = (2, 3),
        random_state: Optional[int] = None,
    ) -> dict:
        if not (1 <= len(component_columns) <= 3):
            raise ValueError("component_columns must have between 1 and 3 entries.")
        if not (1 <= calibration_component <= len(component_columns)):
            raise ValueError(
                f"calibration_component must be between 1 and {len(component_columns)}."
            )
        components = list(component_columns) + [None] * (3 - len(component_columns))
        calibration_values = calibration_values or DEFAULT_CALIBRATION_VALUES

        if random_state is not None:
            np.random.seed(random_state)

        orig_df = self._load(original_path)
        proc_df = self._load(processed_path)

        orig_df, proc_df = self._filter_station(orig_df, proc_df, station)

        real_start = orig_df["_datetime"].min()
        real_end = orig_df["_datetime"].max()

        proc_df = proc_df.sort_values("_datetime").reset_index(drop=True)
        pad_before = proc_df[proc_df["_datetime"] < real_start].copy()
        real_window = proc_df[
            (proc_df["_datetime"] >= real_start) & (proc_df["_datetime"] <= real_end)
        ].copy()
        pad_after = proc_df[proc_df["_datetime"] > real_end].copy()

        if pad_before.empty:
            raise ValueError(
                "No padding hours found before the real measurement window. "
                "Run extrapolate_data (n_hours >= 1) before impute_data."
            )

        for df_part in (pad_before, real_window, pad_after):
            df_part["_alarm_v"] = 0
            df_part["_caution_dr"] = 0

        alarmed_rows = self._mark_missing_rows(orig_df, real_window, component_columns)

        pad_before = pad_before.sort_values("_datetime").reset_index(drop=True)
        calibration_col = components[calibration_component - 1]
        calibration_value = float(np.mean(calibration_values))
        pad_before.loc[0, calibration_col] = calibration_value
        pad_before.loc[0, "_caution_dr"] = 1
        calibration_timestamp = pad_before.loc[0, "_datetime"]

        full_df = (
            pd.concat([pad_before, real_window, pad_after], ignore_index=True)
            .sort_values("_datetime")
            .reset_index(drop=True)
        )
        last_memory_timestamp = full_df["_datetime"].max()

        if save_datetime is not None:
            save_ts = pd.Timestamp(save_datetime)
        else:
            minute = int(np.random.randint(0, 60))
            second = int(np.random.randint(0, 60))
            save_ts = last_memory_timestamp + pd.Timedelta(hours=1, minutes=minute, seconds=second)

        self._write_csv(
            output_path=output_path,
            df=full_df,
            components=components,
            equipment_name=equipment_name,
            save_ts=save_ts,
            unit_digit=unit_digit,
        )
        logger.info(f"Saved reconstructed memory file: {output_path}")

        return {
            "status": "ok",
            "output_path": str(output_path),
            "rows_written": len(full_df),
            "real_window_rows": len(real_window),
            "padding_before_rows": len(pad_before),
            "padding_after_rows": len(pad_after),
            "alarmed_rows": alarmed_rows,
            "calibration_timestamp": str(calibration_timestamp),
            "calibration_value": calibration_value,
            "save_datetime": str(save_ts),
            "last_memory_timestamp": str(last_memory_timestamp),
        }

    # ─────────────────────────────────────────
    # Data loading
    # ─────────────────────────────────────────

    def _load(self, file_path: str) -> pd.DataFrame:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        df = self._read_file(path)
        return self._attach_datetime(df)

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

    def _filter_station(
        self, orig_df: pd.DataFrame, proc_df: pd.DataFrame, station: Optional[str]
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        station_col = self._detect_col(proc_df, COLUMN_ALIASES["station"])
        if not station_col:
            return orig_df, proc_df

        if station is None:
            if proc_df[station_col].nunique() > 1:
                raise ValueError(
                    f"'{station_col}' has multiple values; pass `station` to select one."
                )
            return orig_df, proc_df

        orig_station_col = self._detect_col(orig_df, COLUMN_ALIASES["station"])
        if orig_station_col:
            orig_df = orig_df[orig_df[orig_station_col] == station].reset_index(drop=True)
        return orig_df, proc_df[proc_df[station_col] == station].reset_index(drop=True)

    # ─────────────────────────────────────────
    # Missing-data reconstruction
    # ─────────────────────────────────────────

    def _mark_missing_rows(
        self, orig_df: pd.DataFrame, real_window: pd.DataFrame, component_columns: list[str]
    ) -> int:
        orig_lookup = orig_df.set_index("_datetime")[component_columns]

        for idx, row in real_window.iterrows():
            ts = row["_datetime"]
            if ts not in orig_lookup.index:
                continue
            orig_row = orig_lookup.loc[ts]
            row_alarmed = False
            for col in component_columns:
                if pd.isna(orig_row[col]):
                    real_window.at[idx, col] = ExtrapolationSkill._hot_deck_draw(
                        orig_df, col, ts.hour, is_circular=False
                    )
                    row_alarmed = True
            if row_alarmed:
                real_window.at[idx, "_alarm_v"] = 1

        return int((real_window["_alarm_v"] == 1).sum())

    # ─────────────────────────────────────────
    # CSV writing
    # ─────────────────────────────────────────

    def _write_csv(
        self,
        output_path: str,
        df: pd.DataFrame,
        components: list[Optional[str]],
        equipment_name: str,
        save_ts: pd.Timestamp,
        unit_digit: tuple[int, int],
    ) -> None:
        lines = []

        # Every line has 155 ;-delimited fields, matching the data rows
        # (2 date/time + 3x3 unit/digit/value + 16 status + 64 caution + 64 alarm).
        pad = ";" * 154
        lines.append(f"[{equipment_name}]" + pad)
        lines.append("[Data;Type-Integration;value]" + pad)
        lines.append(
            f"[Save;Time-{save_ts.strftime('%Y/%m/%d')};{save_ts.strftime('%H:%M:%S')}]" + pad
        )
        lines.append(
            "Date;Component1;Component2;Component3;Status;Caution;Alarm" + (";" * 148)
        )

        status_nums = ";".join(str(i) for i in range(N_STATUS_BITS - 1, -1, -1))
        caution_nums = ";".join(str(i) for i in range(N_CAUTION_BITS - 1, -1, -1))
        alarm_nums = ";".join(str(i) for i in range(N_ALARM_BITS - 1, -1, -1))
        lines.append(
            ";Unit;Digit;Value;Unit;Digit;Value;Unit;Digit;Value;"
            f"{status_nums};{caution_nums};{alarm_nums};"
        )

        unit, digit = unit_digit
        for _, row in df.iterrows():
            fields = [_fmt_date(row["_datetime"]), _fmt_time(row["_datetime"])]
            for col in components:
                if col is None:
                    fields += [str(unit), str(digit), "0,00E+00"]
                else:
                    fields += [str(unit), str(digit), _format_value(row[col])]

            fields += _bit_array(N_STATUS_BITS)
            fields += _bit_array(
                N_CAUTION_BITS,
                CAUTION_BIT_CALIBRATION if row["_caution_dr"] == 1 else None,
            )
            fields += _bit_array(
                N_ALARM_BITS,
                ALARM_BIT_MISSING if row["_alarm_v"] == 1 else None,
            )

            lines.append(";".join(fields))

        Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────

def _bit_array(total_bits: int, set_bit: Optional[int] = None) -> list[str]:
    arr = [0] * total_bits
    if set_bit is not None:
        arr[(total_bits - 1) - set_bit] = 1
    return [str(b) for b in arr]


def _fmt_date(ts: pd.Timestamp) -> str:
    return f"{ts.day}/{ts.month:02d}/{ts.year}"


def _fmt_time(ts: pd.Timestamp) -> str:
    return f"{ts.hour}:{ts.minute:02d}:{ts.second:02d}"


def _format_value(v: float) -> str:
    """Scale by 1e6, round to 3 significant figures, format as '[-]D,DDE±EE'."""
    scaled = Decimal(str(float(v))) * Decimal(1_000_000)
    if scaled == 0:
        return "0,00E+00"

    sign = "-" if scaled < 0 else ""
    abs_scaled = abs(scaled)
    exponent = abs_scaled.adjusted()
    quantum = Decimal(1).scaleb(exponent - 2)
    rounded = abs_scaled.quantize(quantum, rounding=ROUND_HALF_UP)

    rounded_exp = rounded.adjusted()
    mantissa = rounded.scaleb(-rounded_exp)
    mantissa_str = f"{mantissa:.2f}".replace(".", ",")
    return f"{sign}{mantissa_str}E{rounded_exp:+03d}"
