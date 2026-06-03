"""Shared user-facing message and alert helpers for offline/network-aware flows."""

from __future__ import annotations

from typing import Optional
from PyQt5.QtWidgets import QMessageBox


_NETWORK_ERROR_MARKERS = (
    "network",
    "internet",
    "dns",
    "host unreachable",
    "offline",
    "httpsconnectionpool",
    "connectionerror",
    "failed to establish a new connection",
    "name or service not known",
    "getaddrinfo failed",
    "temporary failure in name resolution",
    "max retries exceeded with url",
    "connection refused",
    "connection error",
    "could not connect",
    "timed out",
    "timeout",
    "network is unreachable",
    "no route to host",
    "could not resolve host",
    "unable to connect",
)


def is_network_error(err: object) -> bool:
    """Return True when the error/message looks like a connectivity failure."""
    text = str(err or "").strip().lower()
    return any(marker in text for marker in _NETWORK_ERROR_MARKERS)


def offline_action_message(action: str, detail: Optional[str] = None) -> str:
    """Return a concise offline-mode message for clinician-facing dialogs."""
    action_text = str(action or "this action").strip()
    message = (
        "No internet connection is available.\n\n"
        f"{action_text} requires a working network connection."
    )
    if detail:
        message += f"\n\n{detail.strip()}"
    return message


def show_critical(parent, title: str, message: str, details: Optional[str] = None) -> None:
    """Show a critical message box with optional details."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(str(title or "Error"))
    box.setText(str(message or "An error occurred."))
    if details:
        box.setDetailedText(str(details))
    box.exec_()

