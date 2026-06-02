"""Shared user-facing message helpers for offline/network-aware flows."""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox


def is_network_error(message: str) -> bool:
    """Return True when the message looks like a connectivity failure."""
    msg = str(message or "").lower()
    needles = (
        "network",
        "internet",
        "timeout",
        "timed out",
        "connection refused",
        "connection error",
        "could not connect",
        "offline",
        "dns",
        "host unreachable",
        "name or service not known",
    )
    return any(n in msg for n in needles)


def offline_action_message(action: str, instruction: str) -> str:
    """Return a concise offline-mode message for clinician-facing dialogs."""
    action_text = str(action or "").strip()
    instruction_text = str(instruction or "").strip()
    if action_text and instruction_text:
        return f"{action_text} requires an internet connection.\n\n{instruction_text}"
    if action_text:
        return f"{action_text} requires an internet connection."
    return instruction_text or "This action requires an internet connection."


def show_critical(parent, title: str, message: str, details: str | None = None) -> None:
    """Show a critical message box with optional details."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(str(title or "Error"))
    box.setText(str(message or "An error occurred."))
    if details:
        box.setDetailedText(str(details))
    box.exec_()
