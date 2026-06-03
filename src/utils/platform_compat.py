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
    Optional low-spec mode for older Windows machines and development laptops.

    Enable with ECG_LOW_SPEC_MODE=1 or by setting ECG_UI_LIGHTWEIGHT=1.
    """
    flag = str(os.getenv("ECG_LOW_SPEC_MODE", "")).strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    flag = str(os.getenv("ECG_UI_LIGHTWEIGHT", "")).strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True

    try:
        # Auto-enable on genuinely low-memory machines so Windows users
        # do not need to know about the environment flag.
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
                return status.ullTotalPhys < 8 * 1024 * 1024 * 1024
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
