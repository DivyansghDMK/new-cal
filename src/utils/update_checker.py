"""
src/utils/update_checker.py
============================
Background update-availability checker for ECG Monitor.

Flow
----
1. App launches → UpdateCheckerThread is started after license validation.
2. Thread calls GET /api/v1/latest-version on the license server.
3. If a newer version is found the ``update_available`` signal fires with
   an UpdateInfo dict so the UI can show a non-blocking banner.
4. Result is cached for the life of the process (won't hammer the server
   on every loop iteration or repeated checks).

Version format
--------------
The CI workflow uses ``YYYY.MM.DD.HHMM`` (e.g. ``2026.05.21.1003``).
Comparison is done component-by-component as integers, so the lexicographic
string comparison issue is avoided.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal


# ── Module-level cache ────────────────────────────────────────────────────────

_cache_lock = threading.Lock()
_cached_result: Optional[dict] = None          # None = not checked yet
_cache_time: float = 0.0
_CACHE_TTL_SECONDS: float = 4 * 3600           # 4 hours


# ── Version comparison ────────────────────────────────────────────────────────

def _parse_version(version_str: str) -> tuple[int, ...]:
    """
    Parse a version string into a tuple of ints for comparison.
    Handles: '2026.05.21.1003', '1.2.3', '2026.05.21'
    Non-numeric parts are treated as 0.
    """
    parts = []
    for part in version_str.strip().replace("-", ".").split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_newer(remote_version: str, local_version: str) -> bool:
    """Return True if *remote_version* is strictly newer than *local_version*."""
    return _parse_version(remote_version) > _parse_version(local_version)


# ── Core network check ────────────────────────────────────────────────────────

def check_for_update(current_version: str, channel: str = "stable") -> Optional[dict]:
    """
    Check the license server for a newer release.

    Returns a dict on success::

        {
          "update_available": True,
          "version": "2026.05.21.1003",
          "channel": "stable",
          "release_notes": "...",
          "download_url": "https://...",
          "published_at": "2026-05-21T10:00:00+00:00",
        }

    Returns ``None`` if:
      - No update is available.
      - The server is unreachable (fail-silently so offline users are unaffected).
      - The cached result is still fresh.
    """
    global _cached_result, _cache_time

    # Return cached result if still fresh.
    with _cache_lock:
        if _cached_result is not None and (time.time() - _cache_time) < _CACHE_TTL_SECONDS:
            return _cached_result if _cached_result.get("update_available") else None

    server_url = os.getenv("LICENSE_SERVER_URL", "").rstrip("/")
    if not server_url:
        try:
            from utils.crash_logger import get_crash_logger
            get_crash_logger().warning("Update check skipped: LICENSE_SERVER_URL is empty or not defined.", category="UPDATE_CHECK_WARNING")
        except Exception:
            pass
        return None

    url = f"{server_url}/api/v1/latest-version?channel={channel}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ECGMonitor-UpdateChecker/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                try:
                    from utils.crash_logger import get_crash_logger
                    get_crash_logger().warning(f"Update check returned HTTP {resp.status}", category="UPDATE_CHECK_WARNING")
                except Exception:
                    pass
                return None
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        try:
            import traceback
            from utils.crash_logger import get_crash_logger
            get_crash_logger().warning(
                f"Update check failed with exception: {e}\n{traceback.format_exc()}",
                category="UPDATE_CHECK_WARNING"
            )
        except Exception:
            pass
        return None

    remote_version = data.get("version")
    if not remote_version:
        # AWS Lambda proxy integration wraps the actual payload in a "body" string.
        # Unwrap it transparently so the checker works whether hosted on Lambda or a plain server.
        raw_body = data.get("body")
        if isinstance(raw_body, str):
            try:
                data = json.loads(raw_body)
            except Exception:
                pass
        remote_version = data.get("version")
    if not remote_version:
        return None


    force_notify = bool(data.get("force_notify", False))
    newer = is_newer(remote_version, current_version)
    same  = remote_version == current_version

    # Show banner if: newer version exists, OR server forces notification (rollback case).
    # Skip if force_notify AND same version (already on target, nothing to do).
    notify = newer or (force_notify and not same)

    result: dict = {
        "update_available":  notify,
        "force_rollback":    force_notify and not newer,   # True when rolling back to older version
        "version":           remote_version,
        "channel":           data.get("channel", channel),
        "release_notes":     data.get("release_notes", ""),
        "download_url":      data.get("download_url", ""),
        "published_at":      data.get("published_at", ""),
        "current_version":   current_version,
    }

    with _cache_lock:
        _cached_result = result
        _cache_time = time.time()

    return result if result["update_available"] else None


def invalidate_cache() -> None:
    """Force the next check to hit the server (e.g. after user dismisses a banner)."""
    global _cached_result, _cache_time
    with _cache_lock:
        _cached_result = None
        _cache_time = 0.0


# ── QThread wrapper ───────────────────────────────────────────────────────────

class UpdateCheckerThread(QThread):
    """
    Background thread that runs the update check and emits a signal on completion.

    Usage::

        checker = UpdateCheckerThread(current_version="2026.05.20.0900", channel="stable")
        checker.update_available.connect(show_update_banner)
        checker.start()

    Signals
    -------
    update_available(dict)
        Emitted only when a newer version is found.  The dict is the same
        structure returned by ``check_for_update()``.
    check_complete()
        Always emitted when the check finishes (regardless of outcome).
    """

    update_available: pyqtSignal = pyqtSignal(dict)
    check_complete:   pyqtSignal = pyqtSignal()

    def __init__(
        self,
        current_version: str,
        channel: str = "stable",
        delay_seconds: float = 5.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._current_version = current_version
        self._channel = channel
        self._delay = delay_seconds   # Small delay so the app is fully shown first
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Signal the thread to stop as soon as possible and wait for it."""
        self._stop_event.set()
        self.wait(3000)  # wait up to 3 s; gives the network call time to abort

    def run(self) -> None:
        """Thread entry point — runs in background, never blocks UI."""
        # Use Event.wait() instead of time.sleep() so stop() can interrupt it.
        if self._stop_event.wait(timeout=self._delay):
            return   # Interrupted during initial delay — exit cleanly.
        if self._stop_event.is_set():
            return
        result = check_for_update(self._current_version, self._channel)
        if result and not self._stop_event.is_set():
            self.update_available.emit(result)
        if not self._stop_event.is_set():
            self.check_complete.emit()
