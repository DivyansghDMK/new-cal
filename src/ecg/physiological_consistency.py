"""
Physiological Consistency Engine
================================
Validates candidate ECG diagnoses against physiological measurements and features,
rejecting impossible combinations and resolving mutually exclusive diagnoses.
"""

from typing import List, Dict, Any

def validate_diagnoses(
    candidates: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    features: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Validates diagnosis candidates using physiological consistency rules.
    
    Each candidate in 'candidates' is a dict:
      {
         "diagnosis": str,
         "confidence": float,
         "evidence": List[str]
      }
      
    Returns a filtered/adjusted list of candidates.
    """
    validated_candidates = []
    
    # Extract metrics/features
    hr = float(metrics.get("heart_rate_bpm") or 0.0)
    pr = float(metrics.get("pr_ms") or metrics.get("PR") or 0.0)
    qrs = float(metrics.get("qrs_ms") or metrics.get("QRS") or 0.0)
    
    p_detected = bool(features.get("p_detected") or features.get("p_present"))
    # A stable PR means a measurable PR interval exists and there's no AV dissociation.
    av_dissociation = bool(features.get("av_dissociation"))
    stable_pr = bool(pr > 0 and not av_dissociation)
    
    spectral_flutter = bool(features.get("atrial_flutter"))
    flutter_score = float(features.get("flutter_score") or 0.0)
    has_flutter_evidence = spectral_flutter or (flutter_score >= 0.25)
    
    # Organized QRS check:
    # Organized complexes exist if we can count R peaks and the signal is not VF.
    # Usually if we have R peaks with non-zero amplitude and a calculated HR.
    organized_qrs = bool(features.get("organized_qrs", True))
    if features.get("vf_score", 0.0) > 0.6:
        organized_qrs = False
        
    hr_reliable = bool(hr > 0.0 and hr < 300.0)

    for cand in candidates:
        name = cand["diagnosis"]
        confidence = cand["confidence"]
        evidence = list(cand["evidence"])
        
        reject = False
        rejection_reason = ""
        
        # Rule 1: Reject Third-degree AV Block
        if name in ("Third-degree AV Block", "Complete AV Block"):
            if stable_pr:
                reject = True
                rejection_reason = "Stable measurable PR interval exists"
            elif not av_dissociation:
                reject = True
                rejection_reason = "No evidence of AV dissociation"
                
        # Rule 2: Reject AFib
        elif name in ("Atrial Fibrillation", "AFib", "AF"):
            if p_detected:
                reject = True
                rejection_reason = "P waves detected"
            elif stable_pr:
                reject = True
                rejection_reason = "Stable PR interval detected"
                
        # Rule 3: Reject Atrial Flutter
        elif name in ("Atrial Flutter", "Flutter"):
            if stable_pr:
                reject = True
                rejection_reason = "Stable PR interval detected"
            elif not has_flutter_evidence:
                reject = True
                rejection_reason = "No flutter-wave spectral evidence"
                
        # Rule 4: Reject VFib
        elif name in ("Ventricular Fibrillation", "VFib", "VF"):
            if organized_qrs:
                reject = True
                rejection_reason = "Organized QRS complexes exist"
            elif hr_reliable:
                reject = True
                rejection_reason = "Heart rate can be calculated reliably"
                
        # Rule 5: Reject Wide QRS diagnoses (LBBB, RBBB, Wide QRS)
        elif any(term in name.lower() for term in ("bundle branch block", "lbbb", "rbbb", "wide qrs")):
            if qrs < 120.0:
                reject = True
                rejection_reason = f"Authoritative QRS duration ({qrs:.1f} ms) is < 120 ms"
                
        if reject:
            # We don't output the rejected candidate, or we set confidence to 0
            continue
            
        validated_candidates.append({
            "diagnosis": name,
            "confidence": confidence,
            "evidence": evidence
        })
        
    # Conflict Resolution: Mutual exclusion rules
    final_candidates = []
    
    # Map for easy lookup
    by_name = {c["diagnosis"]: c for c in validated_candidates}
    
    # 1. Normal Sinus Rhythm vs Third-degree AV Block
    if "Normal Sinus Rhythm" in by_name and "Third-degree AV Block" in by_name:
        # Normal sinus rhythm cannot co-exist with Complete AV Block.
        # Prefer NSR if PR is stable, else complete block.
        if stable_pr:
            by_name.pop("Third-degree AV Block")
        else:
            by_name.pop("Normal Sinus Rhythm")
            
    # 2. Atrial Flutter vs Atrial Fibrillation
    if ("Atrial Flutter" in by_name or "Flutter" in by_name) and ("Atrial Fibrillation" in by_name or "AFib" in by_name):
        # Mutually exclusive. Prefer Flutter if flutter score is high, else AFib.
        flutter_name = "Atrial Flutter" if "Atrial Flutter" in by_name else "Flutter"
        afib_name = "Atrial Fibrillation" if "Atrial Fibrillation" in by_name else "AFib"
        if flutter_score > 0.35:
            by_name.pop(afib_name, None)
        elif by_name[afib_name]["confidence"] >= by_name[flutter_name]["confidence"]:
            by_name.pop(flutter_name, None)
        else:
            by_name.pop(afib_name, None)

    # 3. Third-degree AV Block / Complete AV Block + Stable PR Interval
    if ("Third-degree AV Block" in by_name or "Complete AV Block" in by_name) and stable_pr:
        by_name.pop("Third-degree AV Block", None)
        by_name.pop("Complete AV Block", None)
        
    return list(by_name.values())
