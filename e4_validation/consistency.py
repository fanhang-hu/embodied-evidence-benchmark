"""Same-input consistency filter. No simulator, private truth, or fresh query."""
from __future__ import annotations

import json

from e4_validation.protocol import obj


def check_knob_burner(serialized_state, case):
    """Use exact IDs from the frozen empirical mapping; never infer nearest knob."""
    try:
        state = json.loads(serialized_state)
        knob = obj(state, case["knob_id"])
        burner = obj(state, case["burner_id"])
        if knob.get("objectType") != "StoveKnob" or burner.get("objectType") != "StoveBurner":
            return dict(decision="DEFER", reason="bound_type_mismatch")
        power = [knob.get("isToggled"), burner.get("isToggled")]
        if any(type(value) is not bool for value in power):
            return dict(decision="DEFER", reason="missing_or_nonboolean_power")
        if power[0] != power[1]:
            return dict(decision="DEFER", reason="knob_burner_conflict", knob_on=power[0], burner_on=power[1])
        return dict(decision="PASS", reason="consistent", knob_on=power[0], burner_on=power[1])
    except (ValueError, KeyError, TypeError):
        return dict(decision="DEFER", reason="missing_ambiguous_or_malformed_input")


def guarded_monitor(serialized_state, candidate, case, original_monitor):
    check = check_knob_burner(serialized_state, case)
    # In a conflict the base policy is not invoked by the authorization path.
    return ("DEFER" if check["decision"] == "DEFER" else original_monitor(serialized_state, candidate, case))
