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

File format (derived from a real `_HA.csv`):
  - `,`-delimited, dot-decimal.
  - 3 bracketed header lines (no trailing delimiters), then 2 column-header lines,
    then data rows.
  - Each data row: combined datetime, then 3×(Unit,Digit,Value) for Component1-3,
    then 16 Status bits (15..0), 64 Caution bits (63..0), 64 Alarm bits (63..0).
  - Value stored as-is (no unit scaling), formatted as "[+/-]X.XXXXXXE[+/-]EEE"
    (always-signed, dot decimal, 6 decimal places, 3-digit exponent).
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from skills.extrapolation.extrapolator import ExtrapolationSkill

logger = logging.getLogger(__name__)


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Convert object columns to numeric where ≥50% of values parse successfully.
    Handles dot-decimal files (e.g. '1.67') when the CSV was read with decimal=','."""
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().mean() > 0.5:
            df[col] = converted
    return df


COLUMN_ALIASES = {
    "date":    ["date", "fecha"],
    "time":    ["time", "hora"],
    "station": ["station", "estacion", "site", "sitio"],
}

N_STATUS_BITS = 16
N_CAUTION_BITS = 64
N_ALARM_BITS = 64

STATUS_BIT_MISSING = 7              # set on imputed rows in the Status block
ALARM_BITS_CALIBRATION = [32, 33]   # DR bits set on the calibration row (second 63..0 block = Alarm)

DEFAULT_CALIBRATION_VALUES = [400, 300, 200, 100, 0]

WORKING_HOUR_START = 8
WORKING_HOUR_END = 18


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
        calibration_offset_hours: int = 2,
        unit_digit: tuple[int, int] = (2, 2),
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

        # Place calibration ~calibration_offset_hours after pad_before start
        cal_target = pad_before["_datetime"].min() + pd.Timedelta(hours=calibration_offset_hours)
        cal_idx = (pad_before["_datetime"] - cal_target).abs().idxmin()
        pad_before.loc[cal_idx, calibration_col] = calibration_value
        pad_before.loc[cal_idx, "_caution_dr"] = 1
        calibration_timestamp = pad_before.loc[cal_idx, "_datetime"]

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
            candidate = last_memory_timestamp + pd.Timedelta(hours=1)
            if candidate.hour < WORKING_HOUR_START:
                save_ts = candidate.normalize() + pd.Timedelta(
                    hours=WORKING_HOUR_START, minutes=minute, seconds=second
                )
            elif candidate.hour >= WORKING_HOUR_END:
                next_day = candidate.normalize() + pd.Timedelta(days=1)
                save_ts = next_day + pd.Timedelta(
                    hours=WORKING_HOUR_START, minutes=minute, seconds=second
                )
            else:
                save_ts = candidate + pd.Timedelta(minutes=minute % 30, seconds=second)

        # Align last row to floor(save_ts) - 1h so the file and save time are consistent.
        target_last = save_ts.floor("h") - pd.Timedelta(hours=1)
        current_last = full_df["_datetime"].max()
        if target_last > current_last:
            ts = current_last + pd.Timedelta(hours=1)
            extra_rows = []
            while ts <= target_last:
                new_row = {"_datetime": ts, "_alarm_v": 0, "_caution_dr": 0}
                for col in component_columns:
                    new_row[col] = ExtrapolationSkill._hot_deck_draw(proc_df, col, ts.hour, is_circular=False)
                extra_rows.append(new_row)
                ts += pd.Timedelta(hours=1)
            full_df = (
                pd.concat([full_df, pd.DataFrame(extra_rows)], ignore_index=True)
                .sort_values("_datetime")
                .reset_index(drop=True)
            )
        elif target_last < current_last:
            full_df = full_df[full_df["_datetime"] <= target_last].reset_index(drop=True)
        last_memory_timestamp = target_last

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
            "padding_after_rows": len(full_df) - len(pad_before) - len(real_window),
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
        T = ","
        lines = []

        # Header lines have no trailing delimiters (matches instrument native format).
        lines.append(f"[{equipment_name}]")
        lines.append("[Data Type-Integration value]")
        lines.append(f"[Save Time-{save_ts.strftime('%Y/%m/%d')} {save_ts.strftime('%H:%M:%S')}]")
        lines.append(
            "Date" + T + "Component1" + T * 3 +
            "Component2" + T * 3 + "Component3" + T * 3 +
            "Status" + T * 16 + "Caution" + T * 64 + "Alarm"
        )

        status_nums = T.join(str(i) for i in range(N_STATUS_BITS - 1, -1, -1))
        caution_nums = T.join(str(i) for i in range(N_CAUTION_BITS - 1, -1, -1))
        alarm_nums = T.join(str(i) for i in range(N_ALARM_BITS - 1, -1, -1))
        lines.append(
            f"{T}Unit{T}Digit{T}Value{T}Unit{T}Digit{T}Value{T}Unit{T}Digit{T}Value"
            f"{T}{status_nums}{T}{caution_nums}{T}{alarm_nums}"
        )

        unit, digit = unit_digit
        for _, row in df.iterrows():
            fields = [_fmt_datetime(row["_datetime"])]
            for col in components:
                if col is None:
                    fields += ["-", "-", "--------------"]
                else:
                    fields += [str(unit), str(digit), _format_value(row[col], digit)]

            alarm_bits = ALARM_BITS_CALIBRATION if row["_caution_dr"] == 1 else None
            fields += _bit_array(N_STATUS_BITS, STATUS_BIT_MISSING if row["_alarm_v"] == 1 else None)
            fields += _bit_array(N_CAUTION_BITS)
            fields += _bit_array(N_ALARM_BITS, alarm_bits)

            lines.append(T.join(fields))

        Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────

def _bit_array(
    total_bits: int,
    set_bits: Optional[int | list[int]] = None,
) -> list[str]:
    arr = [0] * total_bits
    if set_bits is not None:
        for bit in ([set_bits] if isinstance(set_bits, int) else set_bits):
            arr[(total_bits - 1) - bit] = 1
    return [str(b) for b in arr]


def _fmt_datetime(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y/%m/%d %H:%M:%S")


def _format_value(v: float, digit: int = 6) -> str:
    """Format as '[+/-]X.XXXXXXE[+/-]EEE'. Mantissa rounded to `digit` decimal places, zero-padded to 6."""
    x = float(v)
    if abs(x) == 0.0:
        return "+0.000000E+000"
    sign = "+" if x >= 0 else "-"
    mantissa_str, exp_part = f"{abs(x):.6E}".split("E")
    exp_int = int(exp_part)
    mantissa_val = round(float(mantissa_str), digit)
    if mantissa_val >= 10.0:  # rounding overflowed mantissa, re-normalize
        mantissa_val /= 10.0
        exp_int += 1
    return f"{sign}{mantissa_val:.6f}E{exp_int:+04d}"
