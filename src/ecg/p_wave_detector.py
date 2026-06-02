"""
Deprecated compatibility shim for the old P-wave detector.

The previous implementation used a simplistic "largest bump before QRS" rule
that could manufacture P waves and PR intervals. The clinical pipeline now
measures PR from the median beat via `clinical_measurements.py`.

These helpers remain only so older imports keep working, but they intentionally
return no detected P waves or PR intervals.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

DEFAULT_FS = 500.0


def detect_p_waves(signal: np.ndarray, qrs_peaks: np.ndarray,
                   fs: float = DEFAULT_FS) -> List[Optional[int]]:
    """Deprecated: return no detected P waves."""
    _ = (signal, qrs_peaks, fs)
    return [None] * int(len(qrs_peaks))


def compute_pr_intervals(p_positions: List[Optional[int]],
                         qrs_peaks: np.ndarray,
                         fs: float = DEFAULT_FS) -> List[Optional[float]]:
    """Deprecated: PR intervals are now measured clinically elsewhere."""
    _ = (p_positions, qrs_peaks, fs)
    return [None] * int(len(qrs_peaks))


def p_wave_metrics(signal: np.ndarray, qrs_peaks: np.ndarray,
                   fs: float = DEFAULT_FS) -> Dict:
    """Deprecated compatibility wrapper that reports no P-wave detection."""
    _ = signal
    p_pos = detect_p_waves(signal, qrs_peaks, fs)
    pr = compute_pr_intervals(p_pos, qrs_peaks, fs)
    return {
        "p_positions": p_pos,
        "pr_ms": pr,
        "p_count": 0,
        "p_ratio": 0.0,
        "p_present": False,
        "mean_pr_ms": None,
        "pr_std_ms": None,
    }


__all__ = [
    "detect_p_waves",
    "compute_pr_intervals",
    "p_wave_metrics",
]
