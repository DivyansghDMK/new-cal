"""
Lead Capability Matrix Module
=============================
Defines available clinical diagnostics based on lead configuration.
- LEAD_3 (less than 12 leads): Rhythm analysis and basic intervals only.
- LEAD_12 (all 12 leads): Full analysis (ST, MI localization, LVH, axis) enabled.
"""

from typing import List, Dict, Any

def get_lead_capabilities(available_leads: List[str]) -> Dict[str, Any]:
    """
    Returns diagnostic capabilities based on the list of active/connected lead names.
    """
    active_set = {lead.upper() for lead in available_leads if lead}
    
    required_12 = {"I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2", "V3", "V4", "V5", "V6"}
    
    # All 12 leads must be active for full diagnostic interpretation
    is_12_lead = required_12.issubset(active_set)
    
    if is_12_lead:
        return {
            "lead_count": 12,
            "rhythm": True,
            "pr_qrs_qt": True,
            "st_analysis": True,
            "mi_localization": True,
            "lvh": True,
            "axis": "Full"
        }
    else:
        return {
            "lead_count": len(active_set),
            "rhythm": True,
            "pr_qrs_qt": True,
            "st_analysis": False,
            "mi_localization": False,
            "lvh": False,
            "axis": "Limited"
        }
