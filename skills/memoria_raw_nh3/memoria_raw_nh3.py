"""
Memoria raw NH3 skill
======================
Reconstructs a 2-channel NH3-analyzer memory dump (`_HA.csv`) for cases where
only one channel was actually measured (Component2). Component2 is handled
exactly like any other single component by MemoriaRawSkill (real values,
hot-deck-filled missing rows, calibration row, padding, bit-flagging, ...).
Component1 is then derived, row by row, from whichever Component2 value ended
up written to the file:

  - Component1 = Component2 * fraction   (fraction drawn once per run from
    COMPONENT1_FRACTION_RANGE, < 1.0, so Component1 always stays smaller than
    Component2)

Deriving Component1 *after* MemoriaRawSkill has finalized Component2 (rather
than synthesizing it upfront) keeps Component1 < Component2 consistent for
every row, including hot-deck-filled missing rows and the calibration row.

Component3 is left inactive (only Component1 and Component2 carry values).
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from skills.memoria_raw.memoria_raw import MemoriaRawSkill, _format_value

logger = logging.getLogger(__name__)

COMPONENT1_FRACTION_RANGE = (0.3, 0.7)


def _fields_for_slot(slot: int) -> tuple[int, int, int]:
    """Field indices (Unit, Digit, Value) for a 1-based Component slot."""
    start = 1 + (slot - 1) * 3
    return start, start + 1, start + 2


class MemoriaRawNH3Skill:

    def reconstruct(
        self,
        original_path: str,
        processed_path: str,
        component2_column: str,
        output_path: str,
        station: Optional[str] = None,
        equipment_name: str = "Equipment-1:APNA",
        component2_slot: int = 2,
        unit_digit: tuple[int, int] = (2, 2),
        component1_fraction_range: tuple[float, float] = COMPONENT1_FRACTION_RANGE,
        random_state: Optional[int] = None,
        **reconstruct_kwargs,
    ) -> dict:
        if component2_slot not in (1, 2, 3):
            raise ValueError("component2_slot must be 1, 2, or 3.")
        if not (0.0 < component1_fraction_range[0] <= component1_fraction_range[1] < 1.0):
            raise ValueError("component1_fraction_range must be within (0.0, 1.0).")
        component1_slot = 1 if component2_slot != 1 else 2

        if random_state is not None:
            np.random.seed(random_state)
        fraction = float(np.random.uniform(*component1_fraction_range))

        reconstruct_kwargs.setdefault("calibration_component", 1)  # index into component_columns=[component2_column]

        result = MemoriaRawSkill().reconstruct(
            original_path=original_path,
            processed_path=processed_path,
            component_columns=[component2_column],
            component_slots=[component2_slot],
            output_path=output_path,
            station=station,
            equipment_name=equipment_name,
            unit_digit=unit_digit,
            random_state=random_state,
            **reconstruct_kwargs,
        )

        self._inject_component1(output_path, component2_slot, component1_slot, fraction, unit_digit)
        result["component1_fraction"] = fraction
        return result

    @staticmethod
    def _inject_component1(
        output_path: str,
        component2_slot: int,
        component1_slot: int,
        fraction: float,
        unit_digit: tuple[int, int],
    ) -> None:
        unit, digit = unit_digit
        _, _, c2_v_idx = _fields_for_slot(component2_slot)
        c1_u_idx, c1_d_idx, c1_v_idx = _fields_for_slot(component1_slot)

        lines = Path(output_path).read_text(encoding="utf-8").splitlines()
        header, data_lines = lines[:5], lines[5:]

        new_data_lines = []
        for line in data_lines:
            if not line.strip():
                new_data_lines.append(line)
                continue
            fields = line.split(",")
            c2_val = float(fields[c2_v_idx])
            c1_val = max(0.0, c2_val * fraction)

            fields[c1_u_idx], fields[c1_d_idx], fields[c1_v_idx] = str(unit), str(digit), _format_value(c1_val, digit)
            new_data_lines.append(",".join(fields))

        Path(output_path).write_text("\n".join(header + new_data_lines) + "\n", encoding="utf-8")
