"""
Diagnosis Hysteresis Module
===========================
Filters rhythm diagnoses over consecutive windows to prevent rapid toggling/oscillation.
- Activation threshold: 5 consecutive windows.
- Deactivation threshold: 3 consecutive windows of absence.
- Lethal rhythms (Asystole, VFib, VT) bypass activation delay.
"""

from typing import List, Dict, Any, Set

# Global store for tracking hysteresis state
# Structure: { instance_id: { diagnosis_name: { "active": bool, "detected_count": int, "absent_count": int, "last_candidate": dict } } }
_states: Dict[str, Dict[str, Dict[str, Any]]] = {}

LETHAL_RHYTHMS: Set[str] = {
    "Asystole",
    "Ventricular Fibrillation", "VFib", "VF",
    "Ventricular Tachycardia", "VT", "VTach"
}

def clear_hysteresis_state(instance_id: str):
    """
    Clears the hysteresis state for a given instance ID.
    """
    if instance_id in _states:
        _states.pop(instance_id)

def apply_diagnosis_hysteresis(
    instance_id: str,
    candidates: List[Dict[str, Any]],
    activate_threshold: int = 5,
    deactivate_threshold: int = 3
) -> List[Dict[str, Any]]:
    """
    Applies separate activation/deactivation thresholds to a list of candidate diagnoses.
    Returns the filtered list of diagnoses.
    """
    if not instance_id:
        # Pass through if no instance_id is provided
        return candidates

    if instance_id not in _states:
        _states[instance_id] = {}
        
    instance_state = _states[instance_id]
    current_names = {c["diagnosis"] for c in candidates}
    
    # Track all diagnoses we have seen or are currently seeing
    all_known_diagnoses = set(instance_state.keys()) | current_names
    
    output_candidates = []
    candidates_by_name = {c["diagnosis"]: c for c in candidates}
    
    for name in all_known_diagnoses:
        if name not in instance_state:
            instance_state[name] = {
                "active": False,
                "detected_count": 0,
                "absent_count": 0,
                "last_candidate": None
            }
            
        state = instance_state[name]
        is_detected = name in current_names
        is_lethal = name in LETHAL_RHYTHMS or any(lethal in name for lethal in LETHAL_RHYTHMS)
        
        if is_detected:
            state["absent_count"] = 0
            if state["active"]:
                output_candidates.append(candidates_by_name[name])
            else:
                if is_lethal:
                    state["active"] = True
                    state["detected_count"] = activate_threshold
                    output_candidates.append(candidates_by_name[name])
                else:
                    state["detected_count"] += 1
                    if state["detected_count"] >= activate_threshold:
                        state["active"] = True
                        output_candidates.append(candidates_by_name[name])
        else:
            state["detected_count"] = 0
            if state["active"]:
                state["absent_count"] += 1
                if state["absent_count"] >= deactivate_threshold:
                    state["active"] = False
                else:
                    last_cand = state.get("last_candidate")
                    if last_cand:
                        faded_cand = last_cand.copy()
                        faded_cand["confidence"] = max(0.1, faded_cand["confidence"] * 0.9)
                        output_candidates.append(faded_cand)
            
        if is_detected:
            state["last_candidate"] = candidates_by_name[name]
            
    # Sort output candidates to match the original order if present
    original_order = {c["diagnosis"]: i for i, c in enumerate(candidates)}
    output_candidates.sort(key=lambda c: original_order.get(c["diagnosis"], 999))
    
    return output_candidates
