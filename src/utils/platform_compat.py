"""Cross-platform helpers for file opening and light-weight runtime detection."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_low_spec_mode() -> bool:
    """
    Auto-detects weak machines and enables lightweight rendering mode.

    A machine is considered "low-spec" if ANY of the following is true:
      - ECG_LOW_SPEC_MODE=1 / ECG_UI_LIGHTWEIGHT=1 environment variable is set
      - Total RAM is <= 8 GB  (covers older 8 GB i3 machines)
      - Logical CPU count is <= 4  AND  RAM is <= 12 GB
        (catches budget i3-1xxx / i3-12xxx chips with 4 threads)

    Your DESKTOP-DF1G898 (i3-14100, 8-thread, 8 GB) would normally trigger
    the RAM check, but it runs fine — so we add a CPU-thread exclusion for
    CPUs with >= 8 logical cores to avoid throttling your dev machine.
    """
    flag = str(os.getenv("ECG_LOW_SPEC_MODE", "")).strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    flag = str(os.getenv("ECG_UI_LIGHTWEIGHT", "")).strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True

    try:
        if is_windows():
            import ctypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                total_ram = status.ullTotalPhys
                _6gb  = 6  * 1024 * 1024 * 1024
                _10gb = 10 * 1024 * 1024 * 1024
                _12gb = 12 * 1024 * 1024 * 1024

                # Get logical CPU count (fast — uses GetSystemInfo or os.cpu_count)
                cpu_count = 0
                try:
                    cpu_count = os.cpu_count() or 0
                except Exception:
                    pass

                # Rule 1: Genuine low-RAM machine (< 6 GB, e.g., 4 GB RAM)
                # Such machines will always struggle, regardless of CPU.
                if total_ram < _6gb:
                    return True

                # Rule 2: <=10 GB RAM (typically 8 GB systems) but with < 8 CPU threads.
                # If they have a strong CPU (>= 8 logical cores, like the user's i3-14100 with 8 threads),
                # they can run the full app fine, so they are not flagged as low-spec.
                # But budget/older i3 systems with < 8 threads (like 2-core/4-thread or 4-core/4-thread chips)
                # will be flagged as low-spec.
                if total_ram <= _10gb and 0 < cpu_count < 8:
                    return True

                # Rule 3: Medium RAM (10–12 GB) but very few CPU threads (<= 4).
                if total_ram <= _12gb and 0 < cpu_count <= 4:
                    return True
    except Exception:
        pass

    return False


def open_file(path: str | Path) -> bool:
    """Open a file using the platform default application."""
    target = str(Path(path))
    if not target:
        return False
    try:
        if is_windows():
            os.startfile(target)  # type: ignore[attr-defined]
            return True
        if is_macos():
            subprocess.Popen(["open", target])
            return True
        if is_linux():
            subprocess.Popen(["xdg-open", target])
            return True
    except Exception:
        return False
    return False
