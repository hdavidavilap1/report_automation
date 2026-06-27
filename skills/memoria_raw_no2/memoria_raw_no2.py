"""
Memoria raw NO2 skill
======================
Reconstructs a 3-channel NOx-analyzer memory dump (`_HA.csv`) for cases where
only NO2 was actually measured. NO2 is handled exactly like any other single
component by MemoriaRawSkill (real values, hot-deck-filled missing rows,
calibration row, padding, bit-flagging, ...). NO and NOx are then derived,
row by row, from whichever NO2 value ended up written to the file:

  - NO  = NO2 * ratio + hourly noise   (ratio fixed per run, drawn from
          NO_NO2_RATIO_RANGE; represents the site/source NO:NO2 relationship)
  - NOx = NO + NO2                     (exact sum, no extra noise)

Deriving NO/NOx *after* MemoriaRawSkill has finalized NO2 (rather than
synthesizing them upfront) keeps NOx = NO + NO2 exact for every row, including
hot-deck-filled missing rows and the calibration row.

By default NO2 occupies Component2 (as actually wired on the analyzer), NO
occupies Component1, and NOx occupies Component3.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from skills.memoria_raw.memoria_raw import MemoriaRawSkill, _format_value

logger = logging.getLogger(__name__)

NO_NO2_RATIO_RANGE = (1.05, 1.15)
NO_NOISE_PCT = 0.02  # ±2% hourly noise on top of the ratio-derived NO value


def _fields_for_slot(slot: int) -> tuple[int, int, int]:
    """Field indices (Unit, Digit, Value) for a 1-based Component slot."""
    start = 1 + (slot - 1) * 3
    return start, start + 1, start + 2


class MemoriaRawNO2Skill:

    def reconstruct(
        self,
        original_path: str,
        processed_path: str,
        no2_column: str,
        output_path: str,
        station: Optional[str] = None,
        equipment_name: str = "Equipment-1:APNA",
        no2_slot: int = 2,
        unit_digit: tuple[int, int] = (2, 2),
        no_no2_ratio_range: tuple[float, float] = NO_NO2_RATIO_RANGE,
        no_noise_pct: float = NO_NOISE_PCT,
        random_state: Optional[int] = None,
        **reconstruct_kwargs,
    ) -> dict:
        if no2_slot not in (1, 2, 3):
            raise ValueError("no2_slot must be 1, 2, or 3.")
        no_slot = 1 if no2_slot != 1 else 2
        nox_slot = next(s for s in (1, 2, 3) if s not in (no2_slot, no_slot))

        if random_state is not None:
            np.random.seed(random_state)
        ratio = float(np.random.uniform(*no_no2_ratio_range))

        reconstruct_kwargs.setdefault("calibration_component", 1)  # index into component_columns=[no2_column]

        result = MemoriaRawSkill().reconstruct(
            original_path=original_path,
            processed_path=processed_path,
            component_columns=[no2_column],
            component_slots=[no2_slot],
            output_path=output_path,
            station=station,
            equipment_name=equipment_name,
            unit_digit=unit_digit,
            random_state=random_state,
            **reconstruct_kwargs,
        )

        self._inject_no_and_nox(
            output_path, no2_slot, no_slot, nox_slot, ratio, no_noise_pct, unit_digit,
        )
        result["no_no2_ratio"] = ratio
        return result

    @staticmethod
    def _inject_no_and_nox(
        output_path: str,
        no2_slot: int,
        no_slot: int,
        nox_slot: int,
        ratio: float,
        noise_pct: float,
        unit_digit: tuple[int, int],
    ) -> None:
        unit, digit = unit_digit
        _, _, no2_v_idx = _fields_for_slot(no2_slot)
        no_u_idx, no_d_idx, no_v_idx = _fields_for_slot(no_slot)
        nox_u_idx, nox_d_idx, nox_v_idx = _fields_for_slot(nox_slot)

        lines = Path(output_path).read_text(encoding="utf-8").splitlines()
        header, data_lines = lines[:5], lines[5:]

        new_data_lines = []
        for line in data_lines:
            if not line.strip():
                new_data_lines.append(line)
                continue
            fields = line.split(",")
            no2_val = float(fields[no2_v_idx])
            noise = np.random.uniform(-noise_pct, noise_pct)
            no_val = max(0.0, no2_val * ratio * (1 + noise))
            nox_val = no_val + no2_val

            fields[no_u_idx], fields[no_d_idx], fields[no_v_idx] = str(unit), str(digit), _format_value(no_val, digit)
            fields[nox_u_idx], fields[nox_d_idx], fields[nox_v_idx] = str(unit), str(digit), _format_value(nox_val, digit)
            new_data_lines.append(",".join(fields))

        Path(output_path).write_text("\n".join(header + new_data_lines) + "\n", encoding="utf-8")
