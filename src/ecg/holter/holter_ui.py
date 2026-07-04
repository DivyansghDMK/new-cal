"""
ecg/holter/holter_ui.py
========================
Complete Holter Monitor UI - Professional Medical Software
Matches reference images: black/green medical workstation style.

Screens:
  1. HolterStartDialog        - patient info + duration + start
  2. HolterStatusBar          - REC indicator, elapsed, live BPM, arrhythmia ticker
  3. HolterSummaryCards       - KPI cards (Avg HR, Min/Max, Beats, Pauses, Quality, SDNN)
  4. HolterOverviewPanel      - full stats table (Name/Value pairs)
  5. HolterHRVPanel           - HRV table per hour + bottom stats strip
  6. HolterReplayPanel        - RR scatter/Lorenz + scrub slider + ECG strip
  7. HolterEventsPanel        - Arrhythmia events list with strip nav
  8. HolterWaveGridPanel      - 12-lead live/replay grid (3 rows Ã— 4 cols)
  9. HolterInsightPanel       - Comprehensive report preview narrative
 10. HolterRecordManagementPanel - searchable session browser
 11. HolterHistogramPanel     - RR-interval histogram
 12. HolterAFPanel            - AF episode browser
 13. HolterSTPanel            - ST tendency per channel
 14. HolterEditEventPanel     - Edit events with strip thumbnails
 15. HolterEditStripsPanel    - Edit strips (max HR, min HR, sinus max/min thumbnails)
 16. HolterReportTablePanel   - Hour-by-hour report table
 17. HolterMainWindow         - Orchestrates all panels in tabbed layout
"""

import os
import sys
import json
import time
import math
import shutil
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QComboBox, QSlider, QGroupBox, QFrame,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QSizePolicy, QScrollArea, QGridLayout, QSpinBox, QMessageBox,
    QFileDialog, QApplication, QProgressBar, QSplitter, QTextEdit, QInputDialog, QDoubleSpinBox,
    QAbstractItemView, QToolButton, QButtonGroup, QMenu, QScrollBar)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QPoint, QPointF, QRect, QObject, QEvent
from PyQt5.QtGui import QFont, QColor, QPalette, QPainter, QPen, QBrush, QPixmap

try:
    import pyqtgraph as pg
    HAS_PG = True
except Exception:
    pg = None
    HAS_PG = False


def _resolve_recordings_dir(session_dir: str = "") -> str:
    """Return the recordings root directory for the current session or project."""
    normalized = os.path.dirname(session_dir) if os.path.isfile(session_dir) else session_dir
    if normalized and os.path.isdir(normalized):
        if os.path.basename(os.path.normpath(normalized)).lower() == "recordings":
            return normalized
        parent_dir = os.path.dirname(normalized)
        if os.path.basename(os.path.normpath(parent_dir)).lower() == "recordings":
            return parent_dir

    src_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    preferred_dir = os.path.join(src_root, "recordings")
    fallback_dir = os.path.join(os.getcwd(), "recordings")
    if os.path.isdir(preferred_dir):
        return preferred_dir
    if os.path.isdir(fallback_dir):
        return fallback_dir
    return preferred_dir


def _find_latest_completed_session(output_dir: str) -> str:
    """Return the newest completed session directory, or empty string."""
    if not output_dir or not os.path.isdir(output_dir):
        return ""

    candidates = []
    try:
        for name in os.listdir(output_dir):
            session_dir = os.path.join(output_dir, name)
            ecgh_path = os.path.join(session_dir, "recording.ecgh")
            if not os.path.isdir(session_dir):
                continue
            if not os.path.exists(ecgh_path):
                continue
            try:
                sort_key = os.path.getmtime(ecgh_path)
            except Exception:
                sort_key = os.path.getmtime(session_dir)
            candidates.append((sort_key, session_dir))
    except Exception:
        return ""

    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _normalize_patient_info(info: Optional[dict]) -> dict:
    normalized = dict(info or {})
    if not normalized:
        return {}

    display_name = ""
    for key in ("patient_name", "name", "full_name", "patientName"):
        raw_value = normalized.get(key)
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if value and value.lower() not in {"unknown", "unknown patient"}:
            display_name = value
            break

    if display_name:
        normalized["patient_name"] = display_name
        normalized["name"] = display_name
        normalized["full_name"] = display_name
        normalized["patientName"] = display_name

    return normalized


def _load_patient_info_from_session(session_dir: str, fallback_info: Optional[dict] = None) -> dict:
    merged = _normalize_patient_info(fallback_info)
    if not session_dir:
        return merged

    metadata = read_session_metadata(session_dir) if session_dir else {}
    if isinstance(metadata, dict):
        patient_sources = [metadata.get("patient_info")]
        summary = metadata.get("summary")
        if isinstance(summary, dict):
            patient_sources.append(summary.get("patient_info"))
        for candidate in patient_sources:
            if isinstance(candidate, dict) and candidate:
                merged.update(_normalize_patient_info(candidate))

    patient_json = os.path.join(session_dir, "patient.json")
    if os.path.exists(patient_json):
        try:
            with open(patient_json, "r", encoding="utf-8") as handle:
                patient_data = json.load(handle) or {}
            if isinstance(patient_data, dict) and patient_data:
                merged.update(_normalize_patient_info(patient_data))
        except Exception:
            pass

    return _normalize_patient_info(merged)



def _metrics_duration_sec(metrics_list: list) -> float:
    return float(sum(m.get('duration', 0.0) or 0.0 for m in metrics_list))


def _normalize_beat_class(label) -> str:
    """Map recorded beat labels into the compact class buttons used by the UI."""
    raw = str(label or "").strip().upper()
    if not raw:
        return "Other"
    if raw in {"N", "NORMAL", "SINUS"}:
        return "N"
    if raw.startswith("S") or "SV" in raw or "PAC" in raw:
        return "S"
    if raw.startswith("V") or "PVC" in raw or "VENT" in raw:
        return "V"
    if raw.startswith("P") or "PACED" in raw:
        return "P"
    if "AF" in raw or "AFL" in raw or raw in {"F", "Q"}:
        return "AF"
    if raw in {"X", "ART", "ARTIFACT", "NOISE"} or "ARTIFACT" in raw or "NOISE" in raw:
        return "X"
    if raw == "OTHER":
        return "Other"
    return "Other"


def _class_matches_filter(beat_class: str, filter_key: str) -> bool:
    if filter_key == "all":
        return True
    if filter_key == "AF":
        return beat_class == "AF"
    if filter_key == "Other":
        return beat_class == "Other"
    return beat_class == filter_key


def _template_filter_key(label: str) -> str:
    """Normalize template labels into the UI filter keys."""
    return _normalize_beat_class(label)

try:
    from .theme import (
        ADC_TO_MV,
        COL_BEAT_S,
        COL_BG,
        COL_BLACK,
        COL_BTN_ACTIVE_BG,
        COL_BTN_ACTIVE_TEXT,
        COL_DARK,
        COL_GRAY,
        COL_GREEN,
        COL_GREEN_DRK,
        COL_GREEN_MID,
        COL_GRID_MAJOR,
        COL_GRID_MINOR,
        COL_RED,
        COL_TEXT,
        COL_TIMESTAMP,
        COL_WAVE_ORANGE,
        COL_WAVE_RED,
        COL_WHITE,
        COL_YELLOW,
        GAINS,
        PAPER_SPEEDS,
        TOOL_CALIPER,
        TOOL_MAGNIFY,
        TOOL_RULER,
        TOOL_SELECT,
    )
    from .tool_engine import (
        ECGToolEngine,
        amplitude_mv_from_pixels,
        caliper_label,
        canonical_tool,
        hint as tool_hint,
        interval_ms_from_pixels,
        ruler_label,
        tool_specs,
        tooltip as tool_tooltip,
    )
    from .session_store import append_annotation, load_annotations, load_events, load_metrics, read_session_metadata
    from .summary_utils import derive_hr_focus_summary
except ImportError:
    from ecg.holter.theme import (
        ADC_TO_MV,
        COL_BEAT_S,
        COL_BG,
        COL_BLACK,
        COL_BTN_ACTIVE_BG,
        COL_BTN_ACTIVE_TEXT,
        COL_DARK,
        COL_GRAY,
        COL_GREEN,
        COL_GREEN_DRK,
        COL_GREEN_MID,
        COL_GRID_MAJOR,
        COL_GRID_MINOR,
        COL_RED,
        COL_TEXT,
        COL_TIMESTAMP,
        COL_WAVE_ORANGE,
        COL_WAVE_RED,
        COL_WHITE,
        COL_YELLOW,
        GAINS,
        PAPER_SPEEDS,
        TOOL_CALIPER,
        TOOL_MAGNIFY,
        TOOL_RULER,
        TOOL_SELECT,
    )
    from ecg.holter.tool_engine import (
        ECGToolEngine,
        amplitude_mv_from_pixels,
        caliper_label,
        canonical_tool,
        hint as tool_hint,
        interval_ms_from_pixels,
        ruler_label,
        tool_specs,
        tooltip as tool_tooltip,
    )
    from ecg.holter.session_store import append_annotation, load_annotations, load_events, load_metrics, read_session_metadata
    from ecg.holter.summary_utils import derive_hr_focus_summary

# Professional UI palette (kept separate from signal colors).
UI_BG = "#0B1220"
UI_PANEL = "#0F1A2E"
UI_PANEL_ALT = "#13213A"
UI_CARD = "#101B2F"
UI_BORDER = "#243552"
UI_TEXT = "#E6EDF7"
UI_MUTED = "#9AAECB"
UI_ACCENT = "#2F80ED"
UI_ACCENT_HOVER = "#4B96FA"
UI_SUCCESS = "#16C172"
UI_WARNING = "#F59E0B"


def _style_btn(bg=UI_PANEL_ALT, fg=UI_TEXT, hover="#1A2C49"):
    return f"""
        QPushButton {{
            background: {bg};
            color: {fg};
            border: 1px solid {UI_BORDER};
            border-radius: 8px;
            padding: 7px 14px;
            font-size: 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background: {hover};
            color: {UI_TEXT};
        }}
        QPushButton:pressed {{ background: {bg}; border: 1px solid {UI_ACCENT_HOVER}; }}
        QPushButton:disabled {{ background: #1A2233; color: #5F708A; border: 1px solid #2A3953; }}
    """


def _style_active_btn():
    return f"""
        QPushButton {{
            background: {UI_ACCENT};
            color: {UI_TEXT};
            border: 1px solid #5EA4FF;
            border-radius: 8px;
            padding: 7px 14px;
            font-size: 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background: {UI_ACCENT_HOVER}; }}
    """


def _table_style():
    return f"""
        QTableWidget {{
            background: {UI_PANEL};
            alternate-background-color: {UI_PANEL_ALT};
            color: {UI_TEXT};
            gridline-color: {UI_BORDER};
            font-size: 12px;
            border: 1px solid {UI_BORDER};
            selection-background-color: #1E3A5F;
            selection-color: {UI_TEXT};
        }}
        QHeaderView::section {{
            background: {UI_PANEL_ALT};
            color: {UI_MUTED};
            font-size: 11px;
            font-weight: bold;
            padding: 6px;
            border: 1px solid {UI_BORDER};
        }}
        QTableWidget::item {{ padding: 5px; border: none; }}
        QScrollBar:vertical {{
            border: none;
            background: {UI_PANEL_ALT};
            width: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {UI_BORDER};
            min-height: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {UI_MUTED};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        QScrollBar:horizontal {{
            border: none;
            background: {UI_PANEL_ALT};
            height: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {UI_BORDER};
            min-width: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {UI_MUTED};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
    """


def _sec_to_hms(s: float) -> str:
    h = int(s // 3600); m = int((s % 3600) // 60); sec = int(s % 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


# -----------------------------------------------------------------------------
# 1. HOLTER START DIALOG
# -----------------------------------------------------------------------------

class HolterStartDialog(QDialog):
    def __init__(self, parent=None, patient_info: dict = None, output_dir: str = "recordings"):
        super().__init__(parent)
        self.setWindowTitle("Comprehensive ECG Analysis - Setup")
        self.setMinimumWidth(640)
        self.setStyleSheet(f"background: #0F1724; color: {COL_WHITE};")
        self.output_dir = output_dir
        self._result_info = None
        self._result_duration = 24
        self._result_dir = output_dir
        self._build_ui(patient_info or {})

    def _build_ui(self, info: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Comprehensive ECG Analysis - Professional Setup")
        title.setStyleSheet(f"background:{COL_GRAY};color:{COL_GREEN};border:2px solid {COL_GREEN};"
                            f"font-size:20px;font-weight:bold;padding:16px;border-radius:8px;")
        layout.addWidget(title)

        subtitle = QLabel("Enter patient details, choose study duration, and launch the 12-lead ECG workspace.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color:#cccccc;font-size:13px;padding:4px;")
        layout.addWidget(subtitle)

        # Patient info group
        pg = QGroupBox("Patient Information")
        pg.setStyleSheet(f"QGroupBox{{font-weight:bold;color:{COL_GREEN};border:1px solid {COL_GREEN_DRK};"
                         f"border-radius:8px;margin-top:12px;padding-top:20px;background:{COL_BLACK};}}")
        pg_layout = QGridLayout(pg)
        pg_layout.setSpacing(10)

        fields = [
            ("Patient Name", "patient_name", info.get("patient_name", "")),
            ("Age", "age", str(info.get("age", ""))),
            ("Email", "email", info.get("email", "")),
            ("Doctor", "doctor", info.get("doctor", "")),
            ("Organisation", "org", info.get("Org.", info.get("org", ""))),
            ("Phone", "phone", info.get("doctor_mobile", info.get("phone", ""))),
        ]
        self._fields = {}
        for row, (label, key, default) in enumerate(fields):
            lbl = QLabel(label + ":")
            lbl.setStyleSheet(f"font-weight:bold;font-size:13px;color:{COL_GREEN};")
            edit = QLineEdit(default)
            edit.setStyleSheet(f"QLineEdit{{border:1px solid {COL_GREEN_DRK};border-radius:4px;padding:8px;"
                               f"font-size:13px;background:{COL_DARK};color:{COL_GREEN};}}"
                               f"QLineEdit:focus{{border-color:{COL_GREEN};}}")
            pg_layout.addWidget(lbl, row, 0)
            pg_layout.addWidget(edit, row, 1)
            self._fields[key] = edit

        lbl_g = QLabel("Gender:")
        lbl_g.setStyleSheet(f"font-weight:bold;font-size:13px;color:{COL_GREEN};")
        self._gender = QComboBox()
        self._gender.addItems(["Select", "Male", "Female", "Other"])
        idx = self._gender.findText(info.get("gender", info.get("sex", "Select")))
        if idx >= 0: self._gender.setCurrentIndex(idx)
        self._gender.setStyleSheet(f"""
            QComboBox {{
                border:1px solid {COL_GREEN_DRK}; border-radius:4px; padding:8px;
                background:{COL_DARK}; color:{COL_GREEN};
            }}
            QComboBox QAbstractItemView {{
                background:{COL_DARK}; color:white; selection-background-color:{COL_GREEN_DRK};
            }}
        """)
        pg_layout.addWidget(lbl_g, len(fields), 0)
        pg_layout.addWidget(self._gender, len(fields), 1)
        layout.addWidget(pg)

        # Recording settings group
        rg = QGroupBox("Recording Settings")
        rg.setStyleSheet(f"QGroupBox{{font-weight:bold;color:{COL_GREEN};border:1px solid {COL_GREEN_DRK};"
                         f"border-radius:8px;margin-top:12px;padding-top:20px;background:{COL_BLACK};}}")
        rg_layout = QGridLayout(rg)
        rg_layout.setSpacing(10)

        dur_lbl = QLabel("Duration:")
        dur_lbl.setStyleSheet(f"font-weight:bold;font-size:13px;color:{COL_GREEN};")
        self._duration = QComboBox()
        self._duration.addItems(["24 hours", "48 hours", "Custom"])
        self._duration.setStyleSheet(f"""
            QComboBox {{
                border:1px solid {COL_GREEN_DRK}; border-radius:4px; padding:8px;
                background:{COL_DARK}; color:{COL_GREEN};
            }}
            QComboBox QAbstractItemView {{
                background:{COL_DARK}; color:white; selection-background-color:{COL_GREEN_DRK};
            }}
        """)
        self._duration.currentTextChanged.connect(lambda t: self._custom_hours.setVisible(t == "Custom"))
        rg_layout.addWidget(dur_lbl, 0, 0)
        rg_layout.addWidget(self._duration, 0, 1)

        self._custom_hours = QSpinBox()
        self._custom_hours.setRange(1, 72)
        self._custom_hours.setValue(24)
        self._custom_hours.setSuffix(" hours")
        self._custom_hours.setVisible(False)
        self._custom_hours.setStyleSheet(f"border:1px solid {COL_GREEN_DRK};border-radius:4px;padding:8px;"
                                         f"font-size:13px;background:{COL_DARK};color:{COL_GREEN};")
        rg_layout.addWidget(self._custom_hours, 1, 1)

        out_lbl = QLabel("Output Directory:")
        out_lbl.setStyleSheet(f"font-weight:bold;font-size:13px;color:{COL_GREEN};")
        rg_layout.addWidget(out_lbl, 2, 0)
        dir_row = QHBoxLayout()
        self._dir_label = QLabel(self.output_dir)
        self._dir_label.setStyleSheet(f"font-size:12px;color:{COL_GREEN};")
        dir_row.addWidget(self._dir_label, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.setStyleSheet(_style_btn())
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_btn)
        rg_layout.addLayout(dir_row, 2, 1)

        self._rec_count_label = QLabel("")
        self._rec_count_label.setStyleSheet(f"font-size:13px;color:{COL_GREEN};font-weight:700;")
        rg_layout.addWidget(QLabel("Recorded Sessions:"), 3, 0)
        rg_layout.addWidget(self._rec_count_label, 3, 1)
        self._refresh_rec_count()
        layout.addWidget(rg)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_style_btn(COL_GRAY, COL_WHITE, COL_GREEN_DRK))
        cancel_btn.clicked.connect(self.reject)
        start_btn = QPushButton("Open ECG Workspace")
        start_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #ff6600, stop:1 #e65c00);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 14px 24px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #ff7a26; }}
            QPushButton:pressed {{ background: #cc5200; }}
        """)
        start_btn.setMinimumHeight(48)
        start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(start_btn, 1)
        layout.addLayout(btn_row)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.output_dir)
        if d:
            self._result_dir = d
            self._dir_label.setText(d)
            self._refresh_rec_count()

    def _refresh_rec_count(self):
        root = getattr(self, '_result_dir', self.output_dir)
        count = 0
        try:
            if os.path.isdir(root):
                for name in os.listdir(root):
                    if os.path.exists(os.path.join(root, name, "recording.ecgh")):
                        count += 1
        except Exception:
            pass
        self._rec_count_label.setText(f"{count} completed recording(s)")

    def _on_start(self):
        info = {key: field.text().strip() for key, field in self._fields.items()}
        info['gender'] = self._gender.currentText()
        info['sex'] = info['gender']
        info['name'] = info.get('patient_name', 'Unknown')
        info['Org.'] = info.get('org', '')
        if not info.get('patient_name'):
            QMessageBox.warning(self, "Missing Name", "Please enter the patient name.")
            return
        dur_text = self._duration.currentText()
        if dur_text == "24 hours": self._result_duration = 24
        elif dur_text == "48 hours": self._result_duration = 48
        else: self._result_duration = self._custom_hours.value()
        self._result_info = info
        self._result_dir = self._dir_label.text()
        self.accept()

    def get_result(self):
        if self._result_info:
            return self._result_info, self._result_duration, self._result_dir
        return None


# -----------------------------------------------------------------------------
# 2. HOLTER STATUS BAR  (Live recording indicator)
# -----------------------------------------------------------------------------

class HolterStatusBar(QFrame):
    stop_requested = pyqtSignal()

    def __init__(self, parent=None, target_hours: int = 24):
        super().__init__(parent)
        self.target_hours = target_hours
        self._start_time = time.time()
        self._blink_state = True
        self.setFixedHeight(52)
        self.setStyleSheet(f"QFrame{{background:{COL_BLACK};border-bottom:2px solid {COL_GREEN};}}")
        self._build_ui()
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_timer.start(800)
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._elapsed_timer.start(1000)

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 4, 15, 4)
        layout.setSpacing(18)

        self._rec_label = QLabel("REC")
        self._rec_label.setStyleSheet(f"color:{COL_GREEN};font-size:15px;font-weight:bold;")
        layout.addWidget(self._rec_label)

        self._time_label = QLabel("00:00:00")
        self._time_label.setStyleSheet(f"color:{COL_GREEN};font-size:18px;font-weight:bold;font-family:monospace;")
        layout.addWidget(self._time_label)

        tgt = QLabel(f"/ {self.target_hours:02d}:00:00")
        tgt.setStyleSheet(f"color:{COL_GREEN_DRK};font-size:12px;")
        layout.addWidget(tgt)

        sep = QLabel("|")
        sep.setStyleSheet(f"color:{COL_GREEN_DRK};")
        layout.addWidget(sep)

        bpm_lbl = QLabel("BPM:")
        bpm_lbl.setStyleSheet(f"color:{COL_GREEN};font-size:12px;")
        layout.addWidget(bpm_lbl)
        self._bpm_label = QLabel("-")
        self._bpm_label.setStyleSheet(f"color:{COL_GREEN};font-size:18px;font-weight:bold;")
        layout.addWidget(self._bpm_label)

        sep2 = QLabel("|")
        sep2.setStyleSheet(f"color:{COL_GREEN_DRK};")
        layout.addWidget(sep2)

        ev_lbl = QLabel("Events:")
        ev_lbl.setStyleSheet(f"color:{COL_GREEN};font-size:12px;")
        layout.addWidget(ev_lbl)
        self._arrhy_label = QLabel("None detected")
        self._arrhy_label.setStyleSheet(f"color:{COL_GREEN};font-size:12px;font-weight:bold;")
        self._arrhy_label.setMaximumWidth(380)
        layout.addWidget(self._arrhy_label, 1)

        self._progress = QProgressBar()
        self._progress.setRange(0, self.target_hours * 3600)
        self._progress.setValue(0)
        self._progress.setFixedWidth(140)
        self._progress.setFixedHeight(12)
        self._progress.setStyleSheet(f"""
            QProgressBar{{background:{COL_DARK};border-radius:6px;border:1px solid {COL_GREEN_DRK};}}
            QProgressBar::chunk{{background:{COL_GREEN};border-radius:5px;}}
        """)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        stop_btn = QPushButton("Stop")
        stop_btn.setStyleSheet(_style_btn(COL_GREEN_DRK, COL_WHITE, COL_GREEN))
        stop_btn.setFixedHeight(34)
        stop_btn.clicked.connect(self.stop_requested)
        layout.addWidget(stop_btn)

    def _blink(self):
        self._blink_state = not self._blink_state
        color = COL_GREEN if self._blink_state else COL_GREEN_DRK
        self._rec_label.setStyleSheet(f"color:{color};font-size:15px;font-weight:bold;")

    def _update_elapsed(self):
        elapsed = int(time.time() - self._start_time)
        h = elapsed // 3600; m = (elapsed % 3600) // 60; s = elapsed % 60
        self._time_label.setText(f"{h:02d}:{m:02d}:{s:02d}")
        self._progress.setValue(min(elapsed, self.target_hours * 3600))

    def update_stats(self, bpm: float, arrhythmias: List[str]):
        if bpm > 0:
            self._bpm_label.setText(f"{bpm:.0f}")
        if arrhythmias:
            self._arrhy_label.setText("  |  ".join(arrhythmias[:3]))

    def cleanup(self):
        self._blink_timer.stop()
        self._elapsed_timer.stop()


# -----------------------------------------------------------------------------
# 3. HOLTER SUMMARY CARDS
# -----------------------------------------------------------------------------

class HolterSummaryCards(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value_labels = {}
        self._card_frames = []
        self._grid = None
        self.setStyleSheet(f"background:{UI_BG};")
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(12, 10, 12, 10)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        cards = [
            ("Average HR", "avg_hr", "bpm"),
            ("Min / Max HR", "range_hr", "bpm"),
            ("Total Beats", "beats", ""),
            ("Pauses", "pauses", "events"),
            ("Signal Quality", "quality", "%"),
            ("HRV SDNN", "sdnn", "ms"),
            ("rMSSD", "rmssd", "ms"),
            ("Longest RR", "longest_rr", "s"),
        ]
        for idx, (title, key, unit) in enumerate(cards):
            frame = QFrame()
            frame.setStyleSheet(
                f"QFrame{{background:{UI_CARD};border:1px solid {UI_BORDER};border-radius:10px;}}"
            )
            frame.setMinimumHeight(74)
            box = QVBoxLayout(frame)
            box.setContentsMargins(12, 10, 12, 10)
            box.setSpacing(3)
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color:{UI_MUTED};font-size:11px;font-weight:600;border:none;")
            val = QLabel("-")
            val.setStyleSheet(f"color:{UI_TEXT};font-size:21px;font-weight:700;border:none;")
            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet(f"color:{UI_SUCCESS};font-size:10px;font-weight:700;border:none;")
            box.addWidget(lbl)
            box.addWidget(val)
            box.addWidget(unit_lbl)
            self._value_labels[key] = val
            self._card_frames.append(frame)
        self._relayout_cards()

    def _relayout_cards(self):
        if self._grid is None:
            return
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(self)

        width = max(1, self.width())
        if width >= 1400:
            cols = 4
        elif width >= 1050:
            cols = 3
        elif width >= 700:
            cols = 2
        else:
            cols = 1

        for idx, frame in enumerate(self._card_frames):
            self._grid.addWidget(frame, idx // cols, idx % cols)

        rows = int(math.ceil(len(self._card_frames) / float(cols)))
        self.setMinimumHeight(rows * 84 + 24)

    def update_summary(self, s: dict):
        self._value_labels["avg_hr"].setText(f"{s.get('avg_hr', 0):.0f}")
        self._value_labels["range_hr"].setText(f"{s.get('min_hr', 0):.0f} / {s.get('max_hr', 0):.0f}")
        self._value_labels["beats"].setText(f"{s.get('total_beats', 0):,}")
        self._value_labels["pauses"].setText(str(s.get("pauses", 0)))
        self._value_labels["quality"].setText(f"{s.get('avg_quality', 0) * 100:.1f}")
        self._value_labels["sdnn"].setText(f"{s.get('sdnn', 0):.1f}")
        self._value_labels["rmssd"].setText(f"{s.get('rmssd', 0):.1f}")
        self._value_labels["longest_rr"].setText(f"{s.get('longest_rr_ms', 0) / 1000:.2f}")
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_cards()


# -----------------------------------------------------------------------------
# 4. HOLTER OVERVIEW PANEL
# -----------------------------------------------------------------------------

class HolterOverviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{UI_BG};")
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Overview")
        title.setStyleSheet(
            f"color:{UI_TEXT};font-size:14px;font-weight:700;background:{UI_PANEL_ALT};"
            f"padding:8px;border-radius:6px;border:1px solid {UI_BORDER};"
        )
        layout.addWidget(title)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Name", "Value"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.setStyleSheet(_table_style())
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._table, 1)

    def update_summary(self, s: dict):
        rows = [
            ("Total Beats",          f"{s.get('total_beats', 0):,}"),
            ("AVG Heart Rate",       f"{s.get('avg_hr', 0):.0f} bpm"),
            ("Max HR",               f"{s.get('max_hr', 0):.0f} bpm"),
            ("Min HR",               f"{s.get('min_hr', 0):.0f} bpm"),
            ("Sinus Max HR",         f"{s.get('max_hr', 0):.0f} bpm"),
            ("Sinus Min HR",         f"{s.get('min_hr', 0):.0f} bpm"),
            ("Longest RR Interval",  f"{s.get('longest_rr_ms', 0)/1000:.2f}s"),
            ("RRI (>=2.0s)",          str(pauses)),
            ("Tachycardia Beats",    str(s.get('tachy_beats', 0))),
            ("Bradycardia Beats",    str(s.get('brady_beats', 0))),
            ("Ventricular Beats",    str(s.get('ve_beats', 0))),
            ("Supraventricular Beats", str(s.get('sve_beats', 0))),
            ("Template Clusters",    str(s.get('template_count', 0))),
            ("X Total",              str(s.get('pauses', 0))),
            ("SDNN (HRV)",           f"{s.get('sdnn', 0):.1f} ms"),
            ("rMSSD (HRV)",          f"{s.get('rmssd', 0):.1f} ms"),
            ("pNN50 (HRV)",          f"{s.get('pnn50', 0):.2f}%"),
            ("ST Elevation",         "-"),
            ("ST Depression",        "-"),
            ("Signal Quality",       f"{s.get('avg_quality', 1.0)*100:.1f}%"),
            ("Chunks Analyzed",      str(s.get('chunks_analyzed', 0))),
        ]
        self._table.setRowCount(len(rows))
        for i, (name, value) in enumerate(rows):
            ni = QTableWidgetItem(name)
            ni.setForeground(QColor(UI_MUTED))
            ni.setBackground(QColor(UI_PANEL if i % 2 == 0 else UI_PANEL_ALT))
            vi = QTableWidgetItem(value)
            vi.setForeground(QColor(UI_TEXT))
            vi.setBackground(QColor(UI_PANEL if i % 2 == 0 else UI_PANEL_ALT))
            vi.setFont(QFont("Arial", 12, QFont.Bold))
            self._table.setItem(i, 0, ni)
            self._table.setItem(i, 1, vi)
        self._table.resizeRowsToContents()


# -----------------------------------------------------------------------------
# 5. HOLTER HRV PANEL
# -----------------------------------------------------------------------------

class HolterHRVPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{COL_BG};")
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        tab_row = QHBoxLayout()
        self._hrv_event_btn = QPushButton("HRV Event")
        self._hrv_event_btn.setStyleSheet(_style_active_btn())
        self._hrv_trend_btn = QPushButton("HRV Tendency")
        self._hrv_trend_btn.setStyleSheet(_style_btn())
        tab_row.addWidget(self._hrv_event_btn)
        tab_row.addWidget(self._hrv_trend_btn)
        tab_row.addStretch()
        layout.addLayout(tab_row)

        cols = ["Type", "Start at", "Duration", "Mean NN", "SDNN", "SDANN", "TRIIDX", "pNN50", "LF", "HF", "LF/HF", "Status"]
        self._table = QTableWidget(0, len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setStyleSheet(_table_style())
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._table, 1)

        # Bottom stats strip
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:4px;}}")
        stats_layout = QGridLayout(stats_frame)
        stats_layout.setSpacing(8)
        stats_layout.setContentsMargins(12, 8, 12, 8)
        self._summary_labels = {}
        stat_defs = [("NNs", "nns"), ("Mean NN", "mean_nn"), ("SDNN", "sdnn"), ("SDANN", "sdann"),
                     ("rMSSD", "rmssd"), ("pNN50", "pnn50"), ("TRIIDX", "triidx"), ("SDNNIDX", "sdnnidx"),
                     ("VLF", "vlf"), ("LF", "lf"), ("HF", "hf"), ("LF/HF", "lf_hf_ratio")]
        for i, (label, key) in enumerate(stat_defs):
            row, col = divmod(i, 4)
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(f"color:{COL_GREEN};font-size:11px;font-weight:bold;border:none;")
            val = QLabel("-")
            val.setStyleSheet(f"color:{COL_GREEN};font-size:14px;font-weight:bold;"
                              f"background:{COL_DARK};border:1px solid {COL_GREEN_DRK};"
                              f"border-radius:10px;padding:4px 10px;min-width:70px;")
            val.setAlignment(Qt.AlignCenter)
            stats_layout.addWidget(lbl, row * 2, col)
            stats_layout.addWidget(val, row * 2 + 1, col)
            self._summary_labels[key] = val
        layout.addWidget(stats_frame)

        btn_row = QHBoxLayout()
        for lbl in ["Insert", "Reset", "Remove"]:
            btn = QPushButton(lbl)
            btn.setStyleSheet(_style_btn())
            btn_row.addWidget(btn, 1)
        layout.addLayout(btn_row)

    def update_hrv(self, metrics_list: list, summary: dict):
        hourly: dict = {}
        for m in metrics_list:
            h = int(m.get('t', 0) // 3600)
            hourly.setdefault(h, []).append(m)

        rows = []
        all_rr = [m.get('rr_ms', 0) for m in metrics_list if m.get('rr_ms', 0) > 0]
        if all_rr:
            total_duration_sec = int(_metrics_duration_sec(metrics_list))
            from .hrv_metrics import compute_hrv_summary
            hrv = compute_hrv_summary(all_rr)
            rows.append(("Entire", "-", f"{total_duration_sec//60:02d}:{total_duration_sec%60:02d}",
                         f"{int(np.mean(all_rr))}ms", f"{hrv.get('sdnn', summary.get('sdnn', 0)):.0f}ms",
                         f"{hrv.get('sdnn', summary.get('sdnn', 0))*0.82:.0f}ms", f"{hrv.get('triangular_index', 0.0):.2f}",
                         f"{hrv.get('pnn50', summary.get('pnn50', 0)):.2f}%",
                         f"{hrv.get('lf', 0.0):.3f}", f"{hrv.get('hf', 0.0):.3f}",
                         f"{hrv.get('lf_hf_ratio', 0.0):.3f}", ""))
        for h in sorted(hourly.keys()):
            chunks = hourly[h]
            rr_vals = [c.get('rr_ms', 0) for c in chunks if c.get('rr_ms', 0) > 0]
            rr_stds = [c.get('rr_std', 0) for c in chunks if c.get('rr_std', 0) > 0]
            pnn50s = [c.get('pnn50', 0) for c in chunks]
            if not rr_vals: continue
            from .hrv_metrics import compute_hrv_summary
            hrv = compute_hrv_summary(rr_vals)
            rows.append(("Hour", f"{h:02d}:00", "01:00",
                         f"{int(np.mean(rr_vals))}ms",
                         f"{hrv.get('sdnn', 0):.0f}ms",
                         f"{hrv.get('sdnn', 0)*0.82:.0f}ms",
                         f"{hrv.get('triangular_index', 0.0):.2f}",
                         f"{hrv.get('pnn50', np.mean(pnn50s) if pnn50s else 0.0):.2f}%",
                         f"{hrv.get('lf', 0.0):.3f}", f"{hrv.get('hf', 0.0):.3f}",
                         f"{hrv.get('lf_hf_ratio', 0.0):.3f}", ""))

        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor(COL_WHITE if j > 0 else COL_GREEN))
                self._table.setItem(i, j, item)

        s = summary
        for key, fmt in [("nns", str(s.get('total_beats', 0))),
                          ("mean_nn", f"{s.get('avg_hr', 0):.0f}ms"),
                          ("sdnn", f"{s.get('sdnn', 0):.0f}ms"),
                          ("sdann", f"{s.get('sdnn', 0)*0.82:.0f}ms"),
                          ("rmssd", f"{s.get('rmssd', 0):.0f}ms"),
                          ("pnn50", f"{s.get('pnn50', 0):.2f}%"),
                          ("triidx", f"{s.get('triidx', 0.0):.2f}" if s.get('triidx', 0) else "-"),
                          ("sdnnidx", "-"),
                          ("vlf", f"{s.get('vlf_power', 0.0):.3f}" if s.get('vlf_power', 0) else "-"),
                          ("lf", f"{s.get('lf_power', 0.0):.3f}" if s.get('lf_power', 0) else "-"),
                          ("hf", f"{s.get('hf_power', 0.0):.3f}" if s.get('hf_power', 0) else "-"),
                          ("lf_hf_ratio", f"{s.get('lf_hf_ratio', 0.0):.3f}" if s.get('lf_hf_ratio', 0) else "-")]:
            if key in self._summary_labels:
                self._summary_labels[key].setText(fmt)


# -----------------------------------------------------------------------------
# 6. HOLTER LORENZ / REPLAY PANEL
# -----------------------------------------------------------------------------

class HolterReplayPanel(QWidget):
    playback_state_changed = pyqtSignal(bool)
    seek_requested = pyqtSignal(float)
    lead_changed   = pyqtSignal(int)
    section_requested = pyqtSignal(str)
    frame_received = pyqtSignal(object)

    def __init__(self, parent=None, duration_sec: float = 86400):
        super().__init__(parent)
        self.duration_sec = max(1, duration_sec)
        self._strip_length_sec = 10.0
        self.setStyleSheet(f"background:{COL_DARK};")
        self._replay_engine = None
        self._tool_engine = ECGToolEngine()
        self._current_replay_frame = None
        self._selected_lead_idx = 1
        self._slider_units_per_sec = 100
        self._last_slider_seek_raw = None
        self._class_filter = "all"
        self._last_metrics_list = []
        self._build_ui()
        self._magnifier_overlay = MagnifierOverlay(self)
        self._magnifier_overlay.setGeometry(self.rect())
        self._magnifier_overlay.hide()
        self._install_magnifier_dismiss_filters()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._ribbon_buttons = {}

        self._rr_mode = "RR"
        self._time_scope = "whole"

        # â”€â”€ 48-hour session summary bar (replaces the two RR trend canvases) â”€â”€
        summary_frame = QFrame()
        summary_frame.setStyleSheet(f"QFrame{{background:{UI_PANEL};border:1px solid {UI_BORDER};border-radius:6px;}}")
        summary_frame.setFixedHeight(72)
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(12, 6, 12, 6)
        summary_layout.setSpacing(20)
        self._summary_labels = {}
        for key, title in [("duration","Duration"),("total_beats","Total Beats"),("avg_hr","Avg HR"),("max_hr","Max HR"),("min_hr","Min HR"),("pauses","Pauses"),("ve","VE Beats"),("sve","SVE Beats"),("sdnn","SDNN"),("rmssd","rMSSD")]:
            col = QVBoxLayout()
            col.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet(f"color:{UI_MUTED};font-size:9px;font-weight:600;border:none;")
            v = QLabel("-")
            v.setStyleSheet(f"color:{UI_TEXT};font-size:13px;font-weight:700;border:none;")
            col.addWidget(t)
            col.addWidget(v)
            self._summary_labels[key] = v
            summary_layout.addLayout(col)
        summary_layout.addStretch()
        layout.addWidget(summary_frame)

        # ── HR trend mini-chart (40h-48h of data at a glance) ──
        self._hr_trend_canvas = HolterRRTrendCanvas(title="Heart Rate Trend (full recording)")
        self._hr_trend_canvas.setFixedHeight(100)
        layout.addWidget(self._hr_trend_canvas)
        # Keep these as dummy attrs so update_lorenz doesn't crash
        self._rr_trend_full = self._hr_trend_canvas
        self._rr_trend_zoom = self._hr_trend_canvas

        time_row = QHBoxLayout()
        self._btn_time_whole = QPushButton("Time-whole")
        self._btn_time_share = QPushButton("Time-share")
        self._btn_goto_time = QPushButton("Goto Time")
        self._btn_rr = QPushButton("RR")
        self._btn_hr = QPushButton("HR")
        for b in [self._btn_time_whole, self._btn_time_share, self._btn_goto_time]:
            b.setFixedHeight(28)
            b.setStyleSheet(_style_btn(UI_PANEL_ALT, UI_MUTED, "#1A2C49"))
            time_row.addWidget(b)
        time_row.addStretch()
        for b in [self._btn_rr, self._btn_hr]:
            b.setFixedHeight(28)
            b.setFixedWidth(52)
            b.setStyleSheet(_style_btn(UI_PANEL_ALT, UI_MUTED, "#1A2C49"))
            time_row.addWidget(b)
        layout.addLayout(time_row)
        self._btn_time_whole.clicked.connect(lambda: self._set_time_scope("whole"))
        self._btn_time_share.clicked.connect(lambda: self._set_time_scope("share"))
        self._btn_goto_time.clicked.connect(self._goto_time)
        self._btn_rr.clicked.connect(lambda: self._set_rr_mode("RR"))
        self._btn_hr.clicked.connect(lambda: self._set_rr_mode("HR"))
        self._set_time_scope("whole")
        self._set_rr_mode("RR")

        # Top: left (lorenz + templates) + right (focused CH strips)
        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.setChildrenCollapsible(False)
        top_splitter.setHandleWidth(1)
        top_splitter.setStyleSheet(f"QSplitter{{background:{UI_BG};}} QSplitter::handle{{background:{UI_BORDER};}}")

        left_wrap = QFrame()
        left_wrap.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}")
        lw_l = QVBoxLayout(left_wrap)
        lw_l.setContentsMargins(4, 4, 4, 4)
        lw_l.setSpacing(6)
        self._lorenz_canvas = LorenzCanvas(parent=left_wrap)
        lw_l.addWidget(self._lorenz_canvas, 3)
        lorenz_filter_row = QHBoxLayout()
        lorenz_filter_row.setSpacing(4)
        self._lorenz_class_btns = {}
        for key, lbl in [("all", "All"), ("N", "N"), ("S", "S"), ("V", "V"), ("P", "P"), ("AF", "AF"), ("X", "X"), ("Other", "Other")]:
            b = QPushButton(lbl)
            b.setCheckable(True)
            b.setToolTip(f"Show {lbl} beats" if key != "all" else "Show all beats")
            b.setFixedHeight(24)
            b.setStyleSheet(_style_btn(COL_DARK, COL_GREEN, COL_GREEN_DRK))
            b.clicked.connect(lambda checked=False, k=key: self._set_lorenz_class_filter(k))
            self._lorenz_class_btns[key] = b
            lorenz_filter_row.addWidget(b)
        lorenz_filter_row.addStretch()
        lw_l.addLayout(lorenz_filter_row)
        self._set_lorenz_class_filter("all")

        thumbs = QFrame()
        thumbs.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}")
        th_l = QGridLayout(thumbs)
        th_l.setContentsMargins(4, 4, 4, 4)
        th_l.setSpacing(4)
        self._template_thumbs = []
        for idx in range(4):
            s = ECGStripCanvas(height=70, color="#22E36E", pen_width=0.8)
            s.set_gain(1.0)
            self._template_thumbs.append(s)
            th_l.addWidget(s, idx // 2, idx % 2)
        lw_l.addWidget(thumbs, 2)
        top_splitter.addWidget(left_wrap)

        ecg_right = QFrame()
        ecg_right.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}")
        ecg_right_layout = QVBoxLayout(ecg_right)
        ecg_right_layout.setContentsMargins(4, 4, 4, 4)
        ecg_right_layout.setSpacing(2)

        # â”€â”€ 12-lead scrollable grid (1 column, 12 rows) â”€â”€
        leads_scroll = QScrollArea()
        leads_scroll.setWidgetResizable(True)
        leads_scroll.setFrameShape(QFrame.NoFrame)
        leads_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        leads_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        leads_scroll.setStyleSheet(f"QScrollArea{{background:{COL_BLACK};border:none;}}")
        leads_container = QWidget()
        leads_container.setStyleSheet(f"background:{COL_BLACK};")
        leads_vbox = QVBoxLayout(leads_container)
        leads_vbox.setContentsMargins(2, 2, 2, 2)
        leads_vbox.setSpacing(2)

        self._lead_names_ordered = ["I","II","III","aVR","aVL","aVF","V1","V2","V3","V4","V5","V6"]
        self._lead_strips = {}   # lead_name -> ECGStripCanvas
        self._ch_strips = []     # backward-compat list for gain/speed handlers
        for lead in self._lead_names_ordered:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            lbl = QLabel(lead)
            lbl.setFixedWidth(34)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet(f"color:{COL_GREEN};font-weight:bold;font-size:10px;border:none;")
            # Height 60px makes them compact enough to fit well, but scrollable if needed
            strip = ECGStripCanvas(height=60, color="#00FF00", pen_width=0.9, lead_name=lead)
            strip.set_gain(1.0)
            self._lead_strips[lead] = strip
            self._ch_strips.append(strip)
            row.addWidget(lbl)
            row.addWidget(strip, 1)
            leads_vbox.addLayout(row)

        leads_scroll.setWidget(leads_container)
        ecg_right_layout.addWidget(leads_scroll, 3)

        # Full-width rhythm strip (Lead II) at bottom
        rhythm_row = QHBoxLayout()
        rhythm_row.setContentsMargins(0, 0, 0, 0)
        rhythm_row.setSpacing(4)
        rhythm_lbl = QLabel("II")
        self._mini_lead_lbl = rhythm_lbl
        rhythm_lbl.setFixedWidth(34)
        rhythm_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        rhythm_lbl.setStyleSheet(f"color:{COL_GREEN};font-weight:bold;font-size:10px;border:none;")
        self._mini_strip = ECGStripCanvas(height=60, color="#00AA00", pen_width=0.9)
        rhythm_row.addWidget(rhythm_lbl)
        rhythm_row.addWidget(self._mini_strip, 1)
        ecg_right_layout.addLayout(rhythm_row)

        top_splitter.addWidget(ecg_right)


        ov_frame = QFrame()
        ov_frame.setStyleSheet(f"QFrame{{background:{UI_PANEL};border:1px solid {UI_BORDER};border-radius:6px;}}")
        ov_layout = QVBoxLayout(ov_frame)
        ov_layout.setContentsMargins(6, 6, 6, 6)
        ov_layout.setSpacing(6)
        ov_title = QLabel("Overview")
        ov_title.setStyleSheet(f"color:{UI_TEXT};font-size:14px;font-weight:700;border:none;")
        ov_layout.addWidget(ov_title)
        self._overview_table = QTableWidget(0, 2)
        self._overview_table.setHorizontalHeaderLabels(["Name", "Value"])
        self._overview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._overview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._overview_table.verticalHeader().setVisible(False)
        self._overview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._overview_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._overview_table.setFocusPolicy(Qt.NoFocus)
        self._overview_table.setStyleSheet(_table_style())
        ov_layout.addWidget(self._overview_table, 1)
        top_splitter.addWidget(ov_frame)
        top_splitter.setSizes([300, 1050, 260])
        layout.addWidget(top_splitter, 2)

        # Scrub slider row
        slider_row = QHBoxLayout()
        self._time_start_label = QLabel("00:00:00")
        self._time_start_label.setStyleSheet(f"color:{COL_TIMESTAMP};font-family:monospace;font-size:12px;border:none;")
        slider_row.addWidget(self._time_start_label)
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, self._slider_sec_to_value(self.duration_sec))
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal{{height:8px;background:{COL_DARK};border:1px solid {COL_GREEN_DRK};border-radius:4px;}}
            QSlider::handle:horizontal{{background:{COL_GREEN};border:1px solid {COL_WHITE};border-radius:9px;
                width:18px;height:18px;margin:-6px 0;}}
            QSlider::sub-page:horizontal{{background:{COL_GREEN_DRK};border-radius:4px;}}
        """)
        self._slider.setTracking(True)
        self._slider.valueChanged.connect(self._on_slider)
        self._slider.sliderMoved.connect(self._on_slider)
        slider_row.addWidget(self._slider, 1)
        self._pos_label = QLabel("00:00:00")
        self._pos_label.setStyleSheet(f"color:{COL_TIMESTAMP};font-family:monospace;font-size:14px;font-weight:bold;"
                                      f"background:{COL_BLACK};padding:4px;border:1px solid {COL_GREEN_DRK};border-radius:4px;border:none;")
        slider_row.addWidget(self._pos_label)
        layout.addLayout(slider_row)

        # Transport + controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)

        self._play_btn = QPushButton("Play")
        self._play_btn.setStyleSheet(_style_btn())
        self._play_btn.setFixedHeight(30)
        self._play_btn.setMinimumWidth(100)
        self._play_btn.clicked.connect(self._toggle_playback)
        ctrl_row.addWidget(self._play_btn)

        for speed_lbl in ["0.5x", "1x", "2x", "4x"]:
            btn = QPushButton(speed_lbl)
            btn.setStyleSheet(_style_btn(COL_DARK, COL_GREEN, COL_GREEN_DRK))
            btn.setFixedHeight(30)
            btn.setMinimumWidth(56)
            btn.clicked.connect(lambda _, s=speed_lbl: self._set_speed(s))
            ctrl_row.addWidget(btn)
        sep = QLabel("|")
        sep.setStyleSheet(f"color:{COL_GREEN_DRK};")
        ctrl_row.addWidget(sep)

        lbl_lead = QLabel("Lead:")
        lbl_lead.setStyleSheet(f"color:{COL_GREEN};font-weight:bold;border:none;font-size:13px;")
        ctrl_row.addWidget(lbl_lead)
        self._lead_combo = QComboBox()
        self._lead_combo.addItems(["I","II","III","aVR","aVL","aVF","V1","V2","V3","V4","V5","V6"])
        self._lead_combo.setCurrentIndex(1)
        self._lead_combo.setFixedWidth(70)
        self._lead_combo.setStyleSheet(f"background:{COL_DARK};color:{COL_GREEN};border:1px solid {COL_GREEN_DRK};"
                                       f"padding:4px;border-radius:4px;font-weight:bold;")
        self._lead_combo.currentIndexChanged.connect(self._on_lead_changed)
        ctrl_row.addWidget(self._lead_combo)

        ctrl_row.addSpacing(22)

        # Event jump buttons
        for lbl_txt, ev, d in [("Prev AF","AF","prev"),("Next AF","AF","next"),
                               ("Prev Brady","Brady","prev"),("Next Brady","Brady","next"),
                               ("Prev Tachy","Tachy","prev"),("Next Tachy","Tachy","next")]:
            btn = QPushButton(lbl_txt)
            btn.setStyleSheet(_style_btn(COL_BLACK, COL_GREEN, COL_GREEN_DRK))
            btn.setFixedHeight(30)
            ev_c, d_c = ev, d
            btn.setMinimumWidth(78)
            btn.clicked.connect(lambda _, e=ev_c, dd=d_c: self._jump_event(e, dd))
            ctrl_row.addWidget(btn)

        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Bottom toolbar (like reference image)
        toolbar = QFrame()
        toolbar.setStyleSheet(f"QFrame{{background:{COL_BLACK};border-top:1px solid {COL_GREEN_DRK};}}")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(5, 4, 5, 4)
        toolbar_layout.setSpacing(5)
        self._tool_btns = {}
        tool_min_widths = {
            "Patient information": 140,
            "Full Disc.": 90,
            "Goto Template": 114,
            "Measuring Ruler": 120,
            "Parallel Ruler": 112,
            "Magnifying Glass": 126,
            "Gain Settings": 110,
            "Paper speed:25mm/s": 144,
            "Add Event(space)": 130,
            "Adjust strip position": 146,
            "Strip Length:10s": 120,
        }
        for tool in ["Patient information", "Full Disc.", "Goto Template"]:
            tbtn = QPushButton(tool)
            tbtn.setStyleSheet(f"QPushButton{{background:{COL_DARK};color:{COL_TEXT};border:1px solid {COL_GREEN_DRK};"
                               f"border-radius:4px;padding:4px 8px;font-size:10px;}}"
                               f"QPushButton:hover{{background:#202020;color:{COL_WHITE};}}")
            tbtn.setMinimumHeight(30)
            tbtn.setMinimumWidth(tool_min_widths.get(tool, 110))
            tbtn.clicked.connect(lambda _, t=tool, b=tbtn: self._set_tool_mode(t, b))
            toolbar_layout.addWidget(tbtn)
            self._tool_btns[tool] = tbtn
        for tool in ["Measuring Ruler", "Parallel Ruler", "Magnifying Glass", "Gain Settings",
                     "Paper speed:25mm/s", "Add Event(space)", "Adjust strip position", "Strip Length:10s"]:
            tbtn = QPushButton(tool)
            tbtn.setStyleSheet(f"QPushButton{{background:{COL_DARK};color:{COL_TEXT};border:1px solid {COL_GREEN_DRK};"
                               f"border-radius:4px;padding:4px 8px;font-size:10px;}}"
                               f"QPushButton:hover{{background:#202020;color:{COL_WHITE};}}")
            tbtn.setMinimumHeight(30)
            tbtn.setMinimumWidth(tool_min_widths.get(tool, 110))
            tbtn.clicked.connect(lambda _, t=tool, b=tbtn: self._set_tool_mode(t, b))
            toolbar_layout.addWidget(tbtn)
            self._tool_btns[tool] = tbtn
        self._tool_btns["Gain Settings"].setToolTip(
            "Cycle gain (5/10/20/40 mm/mV equivalent) to improve waveform visibility."
        )
        toolbar_layout.addStretch()
        layout.addWidget(toolbar)



    def _install_magnifier_dismiss_filters(self):
        """Dismiss the magnifier on any non-wave click inside the replay panel."""
        self.installEventFilter(self)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)

    def _clear_magnifier_if_needed(self, event) -> bool:
        if event.type() != QEvent.MouseButtonPress or event.button() != Qt.LeftButton:
            return False
        overlay = getattr(self, "_magnifier_overlay", None)
        if overlay is None or not getattr(overlay, "_visible", False):
            return False
        source = self.sender()
        if isinstance(source, ECGStripCanvas):
            return False
        overlay.clear_focus()
        for strip in getattr(self, "_ch_strips", []):
            if hasattr(strip, "_magnify_locked"):
                strip._magnify_locked = False
                strip._magnify_pos = None
                strip.update()
        mini_strip = getattr(self, "_mini_strip", None)
        if mini_strip is not None and hasattr(mini_strip, "_magnify_locked"):
            mini_strip._magnify_locked = False
            mini_strip._magnify_pos = None
            mini_strip.update()
        return False

    def eventFilter(self, obj, event):
        if self._clear_magnifier_if_needed(event):
            return False
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_magnifier_overlay") and self._magnifier_overlay is not None:
            self._magnifier_overlay.setGeometry(self.rect())

    def set_magnifier_focus(self, source_widget, payload: dict, focus_pos: QPoint):
        if hasattr(self, "_magnifier_overlay") and self._magnifier_overlay is not None:
            self._magnifier_overlay.setGeometry(self.rect())
            self._magnifier_overlay.set_focus(source_widget, payload, focus_pos)

    def clear_magnifier_focus(self, source_widget=None):
        if hasattr(self, "_magnifier_overlay") and self._magnifier_overlay is not None:
            self._magnifier_overlay.clear_focus(source_widget)

    def clear_strip_tools(self, source_widget=None):
        """Clear transient ruler/caliper overlays and any locked magnifier."""
        self.clear_magnifier_focus(source_widget)
        for strip in getattr(self, "_ch_strips", []):
            if hasattr(strip, "clear_interaction"):
                strip.clear_interaction()
        mini_strip = getattr(self, "_mini_strip", None)
        if mini_strip is not None and hasattr(mini_strip, "clear_interaction"):
            mini_strip.clear_interaction()

    def _set_tool_mode(self, tool_name: str, btn: QPushButton = None):
        if "Patient information" in tool_name:
            self._show_patient_information()
            return
        if "Full Disc." in tool_name:
            if hasattr(self, "_replay_engine") and self._replay_engine:
                from .holter_full_disclosure import HolterFullDisclosureDialog
                dialog = HolterFullDisclosureDialog(self._replay_engine, self)
                dialog.exec_()
            else:
                QMessageBox.warning(self, "No Data", "No valid replay engine found for Full Disclosure.")
            return
        if "Goto Template" in tool_name:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("Holter ECG Software Tools - Explained")
            box.setTextFormat(Qt.PlainText)
            box.setText(
                "Ruler: measure interval/amplitude and BPM.\n"
                "Caliper: compare regularity and coupling across beats.\n"
                "Magnify: zoom-highlight subtle waveform details.\n"
                "Gain Settings: cycle 5/10/20/40 mm/mV-equivalent scaling.\n\n"
                "End-to-end flow:\n"
                "Raw recording -> Gain optimization -> Magnify flagged events -> "
                "Measure intervals (QT/PR/pause) -> Parallel comparison -> Final report."
            )
            box.setStyleSheet(
                "QMessageBox{background:#10151c;color:#f3f7fb;}"
                "QLabel{color:#f3f7fb;font-size:12px;}"
                "QPushButton{background:#1f6feb;color:white;border:1px solid #4b82d0;border-radius:4px;padding:6px 14px;min-width:70px;}"
                "QPushButton:hover{background:#2d7df2;}"
            )
            box.exec_()
            return

        if "Measuring Ruler" in tool_name:
            tool_name = TOOL_RULER
        elif "Parallel Ruler" in tool_name:
            tool_name = TOOL_CALIPER
        elif "Magnifying Glass" in tool_name:
            tool_name = TOOL_MAGNIFY

        # Handle state cycles for Gain, Speed, Length
        if "Gain Settings" in tool_name:
            gains = [g / 10.0 for g in GAINS]
            curr_g = getattr(self, '_curr_gain_idx', 1)
            next_g = (curr_g + 1) % len(gains)
            self._curr_gain_idx = next_g
            val = gains[next_g]
            for s in getattr(self, "_ch_strips", []):
                s.set_gain(val)
            if hasattr(self, "_mini_strip"):
                self._mini_strip.set_gain(val)
            if btn: btn.setText(f"Gain: {int(val*10)}mm/mV")
            return
        elif "Paper speed" in tool_name:
            speeds = PAPER_SPEEDS
            curr_s = getattr(self, '_curr_speed_idx', 1)
            next_s = (curr_s + 1) % len(speeds)
            self._curr_speed_idx = next_s
            val = speeds[next_s]
            for s in getattr(self, "_ch_strips", []):
                s.set_paper_speed(int(val))
            if hasattr(self, "_mini_strip"):
                self._mini_strip.set_paper_speed(int(val))
            if btn: btn.setText(f"Paper speed:{val}mm/s")
            # Adjust strip_length_sec so the replay engine delivers the right amount of data.
            # Reference: 25mm/s = 10s window; scale inversely with speed.
            self._strip_length_sec = 10.0 * (25.0 / max(1.0, float(val)))
            if getattr(self, "_replay_engine", None):
                try:
                    self._replay_engine.set_window_length(self._strip_length_sec)
                except Exception:
                    pass
            # Re-seek to force data reload with the new strip length
            try:
                current_pos = self._slider_value_to_sec(self._slider.value())
                self.seek_requested.emit(current_pos)
            except Exception:
                pass
            return
        elif "Strip Length" in tool_name:
            lengths = [3, 7, 10, 15, 30]
            curr_l = getattr(self, '_curr_length_idx', 1)
            next_l = (curr_l + 1) % len(lengths)
            self._curr_length_idx = next_l
            val = lengths[next_l]
            self._strip_length_sec = float(val)
            if getattr(self, "_replay_engine", None):
                try:
                    self._replay_engine.set_window_length(self._strip_length_sec)
                except Exception:
                    pass
            if btn: btn.setText(f"Strip Length:{val}s")
            return

        mode = canonical_tool(tool_name)
        self._tool_engine.set_tool(mode)
        for strip in getattr(self, "_ch_strips", []):
            if hasattr(strip, 'set_mode'):
                strip.set_mode(mode)
        if hasattr(self._mini_strip, 'set_mode'):
            self._mini_strip.set_mode(mode)
        for strip in getattr(self, "_template_thumbs", []):
            if hasattr(strip, 'set_mode'):
                strip.set_mode(mode)

    def _set_time_scope(self, scope: str):
        self._time_scope = scope
        self._btn_time_whole.setStyleSheet(_style_active_btn() if scope == "whole" else _style_btn(UI_PANEL_ALT, UI_MUTED, "#1A2C49"))
        self._btn_time_share.setStyleSheet(_style_active_btn() if scope == "share" else _style_btn(UI_PANEL_ALT, UI_MUTED, "#1A2C49"))
        self._strip_length_sec = 10.0 if scope == "whole" else 3.6
        if getattr(self, "_replay_engine", None):
            try:
                self._replay_engine.set_window_length(self._strip_length_sec)
            except Exception:
                pass
        self._refresh_wave_window()

    def _refresh_wave_window(self):
        if getattr(self, '_replay_engine', None):
            try:
                current_pos = float(self._replay_engine.current_position())
                self._replay_engine.seek(current_pos)
                self._replay_panel.set_replay_frame(
                    self._replay_engine.get_all_leads_data(window_sec=float(self._strip_length_sec))
                )
            except Exception:
                pass
        elif getattr(self, '_live_source', None) is not None and hasattr(self, '_replay_panel'):
            try:
                raw = getattr(self._live_source, 'data', None)
                if raw is not None and hasattr(raw, '__len__') and len(raw) > 0:
                    import numpy as _np
                    n_samp = max(len(raw[i]) for i in range(min(12, len(raw))))
                    arr = _np.full((12, n_samp), 2048.0)
                    for i in range(min(12, len(raw))):
                        ch = _np.asarray(raw[i], dtype=float)
                        arr[i, :len(ch)] = ch
                    self._replay_panel.set_replay_frame(arr)
            except Exception:
                pass

    def _set_rr_mode(self, mode: str):
        self._rr_mode = mode
        self._btn_rr.setStyleSheet(_style_active_btn() if mode == "RR" else _style_btn(UI_PANEL_ALT, UI_MUTED, "#1A2C49"))
        self._btn_hr.setStyleSheet(_style_active_btn() if mode == "HR" else _style_btn(UI_PANEL_ALT, UI_MUTED, "#1A2C49"))

    def _build_info_table(self, rows):
        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(["Field", "Value"])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setStyleSheet(_table_style())
        table.setAlternatingRowColors(True)
        for row, (label, value) in enumerate(rows):
            label_item = QTableWidgetItem(str(label))
            label_item.setForeground(QColor(UI_TEXT))
            value_item = QTableWidgetItem(str(value))
            value_item.setForeground(QColor(COL_WHITE))
            table.setItem(row, 0, label_item)
            table.setItem(row, 1, value_item)
        table.resizeRowsToContents()
        return table

    def _show_patient_information(self):
        summary = dict(getattr(self, "_summary", {}) or {})
        engine = getattr(self, "_replay_engine", None)
        session_dir = summary.get("session_dir", "") or ""
        if not session_dir and engine is not None:
            session_dir = os.path.dirname(getattr(engine, "ecgh_path", "") or "")
        metadata = read_session_metadata(session_dir) if session_dir else {}
        if isinstance(metadata, dict):
            meta_summary = metadata.get("summary")
            if isinstance(meta_summary, dict):
                merged = dict(meta_summary)
                merged.update(summary)
                summary = merged
            meta_patient = metadata.get("patient_info")
            if isinstance(meta_patient, dict) and meta_patient:
                summary["patient_info"] = dict(meta_patient)

        patient_info = _normalize_patient_info(
            summary.get("patient_info") or getattr(engine, "patient_info", {}) or {}
        )

        if not summary and not patient_info:
            QMessageBox.information(self, "Patient information", "No recording is loaded.")
            return

        session_name = os.path.basename(session_dir) if session_dir else "Current session"
        record_time = session_name
        parts = session_name.split("_", 3)
        if len(parts) >= 2:
            record_time = "_".join(parts[:2]).replace("_", " ")

        def fmt_num(value, suffix="", digits=1):
            try:
                return f"{float(value):.{digits}f}{suffix}"
            except Exception:
                return "-" if value in (None, "") else f"{value}{suffix}"

        def fmt_duration(seconds):
            try:
                sec = max(0, int(float(seconds)))
            except Exception:
                return "-"
            h = sec // 3600
            m = (sec % 3600) // 60
            s = sec % 60
            if h > 0:
                return f"{h}h {m:02d}m"
            if m > 0:
                return f"{m}m {s:02d}s"
            return f"{s}s"

        patient_rows = [
            ("Patient Name", patient_info.get("patient_name") or patient_info.get("name") or "-"),
            ("Age", patient_info.get("age", "-")),
            ("Gender", patient_info.get("gender") or patient_info.get("sex") or "-"),
            ("Doctor", patient_info.get("doctor") or "-"),
            ("Email", patient_info.get("email") or "-"),
            ("Phone", patient_info.get("doctor_mobile") or patient_info.get("phone") or "-"),
            ("Organisation", patient_info.get("org") or patient_info.get("Org.") or "-"),
            ("Study Duration", fmt_duration(summary.get("duration_sec", 0))),
        ]

        dlg = QDialog(self)
        dlg.setWindowTitle("Patient Information")
        dlg.setMinimumSize(760, 620)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: {UI_BG};
                color: {UI_TEXT};
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
            QGroupBox {{
                color: {UI_TEXT};
                font-weight: 700;
                border: 1px solid {UI_BORDER};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                background: {COL_BLACK};
            }}
            QHeaderView::section {{
                background: {UI_PANEL_ALT};
                color: {UI_TEXT};
                border: 1px solid {UI_BORDER};
                padding: 6px;
                font-weight: 700;
            }}
        """)
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        title = QLabel("Patient Information")
        title.setStyleSheet(f"font-size:18px;font-weight:700;color:{UI_TEXT};")
        outer.addWidget(title)

        subtitle = QLabel(f"Selected recording: {session_name}")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color:{UI_MUTED};font-size:12px;")
        outer.addWidget(subtitle)

        patient_box = QGroupBox("Patient Details")
        patient_box.setStyleSheet(f"""
            QGroupBox {{
                color: {UI_TEXT};
                font-weight: 700;
                border: 1px solid {UI_BORDER};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                background: {UI_PANEL};
            }}
        """)
        patient_layout = QVBoxLayout(patient_box)
        patient_layout.setContentsMargins(10, 16, 10, 10)
        patient_layout.addWidget(self._build_info_table(patient_rows))
        outer.addWidget(patient_box)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedSize(94, 32)
        close_btn.setStyleSheet(_style_btn())
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

        dlg.exec_()

    def _goto_time(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Go to Time")
        dlg.setFixedSize(420, 160)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: {UI_BG};
                border: 1px solid {UI_BORDER};
                border-radius: 10px;
            }}
            QLabel {{
                color: {UI_TEXT};
                font-size: 13px;
                font-weight: bold;
                border: none;
                background: transparent;
            }}
            QLineEdit {{
                background: {UI_PANEL};
                color: {UI_TEXT};
                border: 1px solid {UI_BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                selection-background-color: {UI_ACCENT};
            }}
            QLineEdit:focus {{
                border: 1px solid {UI_ACCENT};
            }}
        """)
        v_layout = QVBoxLayout(dlg)
        v_layout.setContentsMargins(20, 18, 20, 18)
        v_layout.setSpacing(12)

        lbl = QLabel("Enter time (HH:MM:SS or seconds):")
        lbl.setStyleSheet(f"color:{UI_MUTED};font-size:12px;font-weight:normal;border:none;background:transparent;")
        v_layout.addWidget(lbl)

        inp = QLineEdit()
        inp.setPlaceholderText("e.g.  01:23:45  or  83")
        inp.setClearButtonEnabled(True)
        v_layout.addWidget(inp)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        ok_btn = QPushButton("Go")
        ok_btn.setFixedSize(90, 34)
        ok_btn.setStyleSheet(_style_active_btn())
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(90, 34)
        cancel_btn.setStyleSheet(_style_btn())
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        v_layout.addLayout(btn_row)

        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        inp.returnPressed.connect(dlg.accept)

        if dlg.exec_() != QDialog.Accepted:
            return
        t = inp.text().strip()
        if not t:
            return
        sec = 0.0
        try:
            if ":" in t:
                parts = [int(p) for p in t.split(":")]
                if len(parts) == 3:
                    sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
                elif len(parts) == 2:
                    sec = parts[0] * 60 + parts[1]
                else:
                    sec = float(t)
            else:
                sec = float(t)
        except Exception:
            warn = QDialog(self)
            warn.setWindowTitle("Invalid Time")
            warn.setFixedSize(340, 120)
            warn.setStyleSheet(f"QDialog{{background:{UI_BG};border:1px solid {UI_BORDER};border-radius:8px;}} QLabel{{color:{UI_TEXT};font-size:12px;border:none;background:transparent;}}")
            wl = QVBoxLayout(warn)
            wl.setContentsMargins(18, 16, 18, 16)
            wl.setSpacing(12)
            wl.addWidget(QLabel("Use HH:MM:SS, MM:SS, or plain seconds."))
            wb = QPushButton("OK")
            wb.setStyleSheet(_style_btn())
            wb.clicked.connect(warn.accept)
            wr = QHBoxLayout()
            wr.addStretch()
            wr.addWidget(wb)
            wl.addLayout(wr)
            warn.exec_()
            return
        sec = max(0.0, min(sec, float(self.duration_sec)))
        self.seek_requested.emit(sec)

    def update_summary(self, summary: dict):
        self._summary = dict(summary or {})
        self._patient_info = _normalize_patient_info(self._summary.get('patient_info') or getattr(self._replay_engine, 'patient_info', {}) or {})
        if hasattr(self, '_summary_labels'):
            def set_lbl(k, v):
                if k in self._summary_labels: self._summary_labels[k].setText(str(v))
            
            dur = summary.get('duration_sec', 0)
            h = int(dur // 3600)
            m = int((dur % 3600) // 60)
            set_lbl("duration", f"{h:02d}h {m:02d}m")
            set_lbl("total_beats", summary.get('total_beats', 0))
            set_lbl("avg_hr", f"{summary.get('avg_hr', 0)} bpm")
            set_lbl("max_hr", f"{summary.get('max_hr', 0)} bpm")
            set_lbl("min_hr", f"{summary.get('min_hr', 0)} bpm")
            set_lbl("pauses", summary.get('pauses', 0))
            set_lbl("ve", summary.get('ve_beats', 0))
            set_lbl("sve", summary.get('sve_beats', 0))
            set_lbl("sdnn", f"{summary.get('sdnn', 0)} ms")
            set_lbl("rmssd", f"{summary.get('rmssd', 0)} ms")

    def _slider_sec_to_value(self, seconds: float) -> int:
        units = max(1, int(getattr(self, "_slider_units_per_sec", 100)))
        return int(round(max(0.0, float(seconds)) * units))

    def _slider_value_to_sec(self, value: int) -> float:
        units = max(1, int(getattr(self, "_slider_units_per_sec", 100)))
        return max(0.0, float(value) / float(units))

    def set_replay_engine(self, engine):
        self._replay_engine = engine
        self._slider.setRange(0, self._slider_sec_to_value(engine.duration_sec))
        engine.set_position_callback(self._on_position_update)
        engine.set_window_length(getattr(self, "_strip_length_sec", 10.0))
        
        # Wire up data callback safely for thread-safe playback updates
        try:
            self.frame_received.disconnect()
        except TypeError:
            pass
        self.frame_received.connect(self.set_replay_frame)
        engine.set_data_callback(lambda data: self.frame_received.emit(data))

    def _on_slider(self, value):
        raw = int(value)
        sec = self._slider_value_to_sec(raw)
        self._pos_label.setText(_sec_to_hms(sec))
        if self._last_slider_seek_raw == raw:
            return
        self._last_slider_seek_raw = raw
        self.seek_requested.emit(float(sec))

    def _on_lead_changed(self, idx: int):
        self._selected_lead_idx = max(0, int(idx))
        frame = getattr(self, "_current_replay_frame", None)
        if frame is not None:
            try:
                self.set_replay_frame(frame)
            except Exception:
                pass
        try:
            self.lead_changed.emit(int(idx))
        except Exception:
            pass

    def _on_position_update(self, current_sec, duration_sec):
        self._last_slider_seek_raw = self._slider_sec_to_value(current_sec)
        self._slider.blockSignals(True)
        self._slider.setValue(self._slider_sec_to_value(current_sec))
        self._slider.blockSignals(False)
        self._pos_label.setText(_sec_to_hms(current_sec))

    def _toggle_playback(self):
        if not self._replay_engine: return
        if self._replay_engine.is_playing():
            self._replay_engine.pause()
            self._play_btn.setText("Play")
        else:
            self._replay_engine.play()
            self._play_btn.setText("Pause")

    def _set_speed(self, text: str):
        if self._replay_engine:
            try:
                self._replay_engine.set_speed(float(text.replace("x", "")))
            except Exception:
                pass

    def _set_lorenz_class_filter(self, key: str):
        key = str(key or "all")
        if key not in self._lorenz_class_btns:
            key = "all"
        self._class_filter = key
        for btn_key, btn in self._lorenz_class_btns.items():
            btn.setChecked(btn_key == key)
            btn.setStyleSheet(_style_active_btn() if btn_key == key else _style_btn(COL_DARK, COL_GREEN, COL_GREEN_DRK))
        if self._last_metrics_list:
            self.update_lorenz(self._last_metrics_list)

    def _jump_event(self, ev_type: str, direction: str):
        if self._replay_engine:
            t = self._replay_engine.seek_to_event(ev_type, direction)
            self.seek_requested.emit(t)

    def update_lorenz(self, metrics_list: list):
        """Update the Lorenz/scatter plot from all individual RR data."""
        self._last_metrics_list = list(metrics_list or [])
        rr_all = []
        rr_points = []
        for m in metrics_list:
            t0 = float(m.get('t', 0.0) or 0.0)
            beat_labels = list(m.get('all_beats') or [])
            if 'rr_intervals_list' in m:
                rr_list = [float(v) for v in (m.get('rr_intervals_list') or []) if float(v) > 0]
                if rr_list:
                    dur = float(m.get('duration', 0.0) or 0.0)
                    step = (dur / max(1, len(rr_list))) if dur > 0 else 0.2
                    for i, rr in enumerate(rr_list):
                        beat_info = beat_labels[i] if i < len(beat_labels) and isinstance(beat_labels[i], dict) else {}
                        beat_class = _normalize_beat_class(
                            beat_info.get("label")
                            or beat_info.get("template_label")
                            or beat_info.get("auto_label")
                            or m.get("label")
                            or m.get("template_label")
                            or m.get("arrhythmia")
                            or (m.get("arrhythmias") or [None])[0]
                        )
                        rr_all.append(rr)
                        rr_points.append((t0 + i * step, rr, beat_class))
                    continue  # skip fallback if list data available
            # Fallback: use single rr_ms value per chunk
            rr_val = float(m.get('rr_ms', 0) or 0)
            if rr_val > 200:
                rr_all.append(rr_val)
                beat_class = _normalize_beat_class(
                    m.get("label")
                    or m.get("template_label")
                    or m.get("arrhythmia")
                    or (m.get("arrhythmias") or [None])[0]
                )
                rr_points.append((t0, rr_val, beat_class))

        rr_n = [r for r in rr_all if r > 200]
        filtered_points = [p for p in rr_points if _class_matches_filter(p[2], self._class_filter)]
        filtered_rr = [p[1] for p in filtered_points if p[1] > 200]
        plot_rr = filtered_rr if len(filtered_rr) >= 2 else rr_n
        if len(plot_rr) >= 2:
            rr_x = plot_rr[:-1]
            rr_y = plot_rr[1:]
            lo = float(np.percentile(plot_rr, 5))
            hi = float(np.percentile(plot_rr, 95))
            if hi - lo < 250:
                center = float(np.median(plot_rr))
                lo = center - 500.0
                hi = center + 500.0
            lo = max(0.0, lo - 50.0)
            hi = hi + 50.0
            self._lorenz_canvas.set_data(rr_x, rr_y, x_range=(lo, hi), y_range=(lo, hi))
        else:
            self._lorenz_canvas.set_data([], [])
        if hasattr(self, "_rr_trend_full"):
            trend_points = [(t, rr) for t, rr, _cls in filtered_points] if len(filtered_points) >= 2 else [(t, rr) for t, rr, _cls in rr_points]
            self._rr_trend_full.set_points(trend_points)
            recent = trend_points[-1200:] if len(trend_points) > 1200 else trend_points
            self._rr_trend_zoom.set_points(recent)
        self._update_overview_table(metrics_list, rr_n)
            
    def set_replay_frame(self, data):
        """Update all 12 lead strips and compute Lorenz from data when no RR metrics."""
        if data is None or data.shape[0] < 12:
            return

        self._current_replay_frame = data
        strip_len = int(max(1, getattr(self, "_strip_length_sec", 10.0)) * 500)
        if data.shape[1] > strip_len:
            data = data[:, -strip_len:]

        N = data.shape[1]
        x = np.linspace(0, N / 500.0, N) if N > 0 else []
        if N <= 0:
            return

        lead_names = ["I","II","III","aVR","aVL","aVF","V1","V2","V3","V4","V5","V6"]

        # Ensure data has 12 channels
        if data.shape[0] < 12:
            new_data = np.zeros((12, data.shape[1]), dtype=data.dtype)
            new_data[:data.shape[0], :] = data
            for i in range(data.shape[0], 12):
                new_data[i, :] = 2048.0
            data = new_data

        # --- Force mathematical derivation of augmented limb leads ---
        # Einthoven's Law dictates these leads are perfectly locked to I and II.
        # We unconditionally derive them to overwrite any floating hardware noise.
        I_lead = data[0]
        II_lead = data[1]
        
        data[2] = (II_lead - 2048.0) - (I_lead - 2048.0) + 2048.0  # III = II - I
        # User wants aVR mapped to 0 to -4096. We synthesize it inverted and centered at -2048.
        data[3] = -((I_lead - 2048.0) + (II_lead - 2048.0)) / 2.0 - 2048.0
        data[4] = (I_lead - 2048.0) - (II_lead - 2048.0) / 2.0 + 2048.0  # aVL = I - II/2
        data[5] = (II_lead - 2048.0) - (I_lead - 2048.0) / 2.0 + 2048.0  # aVF = II - I/2

        # --- Feed all 12 lead strips ---
        lead_strips = getattr(self, "_lead_strips", {})
        for idx, lead in enumerate(lead_names):
            if idx < data.shape[0] and lead in lead_strips:
                lead_strips[lead].set_data(x, data[idx].copy())

        # Mini strip follows the selected lead from the dropdown
        if hasattr(self, "_mini_strip") and data.shape[0] > 0:
            lead_idx = max(0, min(int(getattr(self, "_selected_lead_idx", 1)), data.shape[0] - 1))
            selected_lead = self._lead_combo.currentText() if hasattr(self, "_lead_combo") else lead_names[lead_idx]
            self._mini_strip.set_data(x, data[lead_idx].copy())
            try:
                self._mini_strip.lead_name = selected_lead
            except Exception:
                pass
            if hasattr(self, "_mini_lead_lbl"):
                self._mini_lead_lbl.setText(selected_lead)

        # Template thumbnails (use first 4 leads: I, II, III, aVR)
        for i, ts in enumerate(getattr(self, "_template_thumbs", [])):
            src = min(i, data.shape[0] - 1)
            center = N // 2
            w = min(220, max(80, N // 6))
            a = max(0, center - w // 2)
            b = min(N, center + w // 2)
            seg = data[src, a:b] if b > a else data[src, :]
            tx = np.linspace(0, len(seg) / 500.0, len(seg)) if len(seg) > 0 else []
            ts.set_data(tx, seg.copy() if len(seg) > 0 else data[src].copy())

        # --- On-the-fly Lorenz from data when Lorenz canvas has no data ---
        lorenz = getattr(self, "_lorenz_canvas", None)
        if lorenz is not None and (not lorenz._x):  # no RR data loaded from metrics
            self._compute_lorenz_from_signal(data, N)

    def _compute_lorenz_from_signal(self, data: np.ndarray, N: int):
        """Detect R-peaks in Lead II and populate the Lorenz scatter from the raw ECG data."""
        try:
            from scipy.signal import butter, filtfilt, find_peaks
            fs = 500.0
            lead_ii = np.asarray(data[1], dtype=float) if data.shape[0] > 1 else np.asarray(data[0], dtype=float)
            # Bandpass 5-20 Hz to isolate QRS
            nyq = fs / 2.0
            b, a = butter(2, [5.0 / nyq, 20.0 / nyq], btype='band')
            filtered = filtfilt(b, a, lead_ii)
            squared = filtered ** 2
            win = max(1, int(0.15 * fs))
            mwa = np.convolve(squared, np.ones(win) / win, mode='same')
            threshold = max(np.mean(mwa) * 0.5, 1e-6)
            min_dist = max(1, int(0.3 * fs))
            peaks, _ = find_peaks(mwa, height=threshold, distance=min_dist)
            if len(peaks) >= 3:
                rr_ms = np.diff(peaks) / fs * 1000.0
                rr_valid = [float(r) for r in rr_ms if 250 < r < 2500]
                if len(rr_valid) >= 2:
                    rr_x = rr_valid[:-1]
                    rr_y = rr_valid[1:]
                    self._lorenz_canvas.set_data(rr_x, rr_y)
                    if hasattr(self, "_rr_trend_full"):
                        rr_points = [(i * 0.5, rr) for i, rr in enumerate(rr_valid)]
                        self._rr_trend_full.set_points(rr_points)
                        self._rr_trend_zoom.set_points(rr_points[-400:] if len(rr_points) > 400 else rr_points)
        except Exception:
            pass

    def _update_overview_table(self, metrics_list: list, rr_n: list):
        if not hasattr(self, "_overview_table"):
            return
        summary_rows = self._compute_replay_overview(metrics_list, rr_n)
        self._overview_table.setRowCount(len(summary_rows))
        for r, (name, value) in enumerate(summary_rows):
            n_item = QTableWidgetItem(name)
            v_item = QTableWidgetItem(value)
            n_item.setForeground(QColor(UI_MUTED))
            v_item.setForeground(QColor(UI_TEXT))
            self._overview_table.setItem(r, 0, n_item)
            self._overview_table.setItem(r, 1, v_item)

    def _compute_replay_overview(self, metrics_list: list, rr_n: list) -> list:
        total_beats = len(rr_n)
        avg_hr = (60000.0 / float(np.mean(rr_n))) if rr_n else 0.0
        max_hr = (60000.0 / float(min(rr_n))) if rr_n else 0.0
        min_hr = (60000.0 / float(max(rr_n))) if rr_n else 0.0
        pauses = int(sum(1 for rr in rr_n if rr >= 2000))
        longest_rr = (max(rr_n) / 1000.0) if rr_n else 0.0
        ve = int(sum(1 for m in metrics_list if any("V" in str(a) for a in (m.get("arrhythmias", []) or []))))
        sve = int(sum(1 for m in metrics_list if any(("PAC" in str(a)) or ("SVE" in str(a)) for a in (m.get("arrhythmias", []) or []))))
        
        # Calculate percentages and durations
        total_chunks = len(metrics_list) if metrics_list else 1
        tachy_chunks = sum(1 for m in metrics_list if m.get('hr_mean', 0) > 100)
        brady_chunks = sum(1 for m in metrics_list if 0 < m.get('hr_mean', 0) < 60)
        af_chunks = sum(1 for m in metrics_list if any("AF" in str(a) for a in (m.get("arrhythmias", []) or [])))
        
        # Each chunk is roughly 4 seconds.
        chunk_dur = 4.0
        tachy_pct = (tachy_chunks / total_chunks) * 100.0
        brady_pct = (brady_chunks / total_chunks) * 100.0
        af_dur_str = f"{(af_chunks * chunk_dur) / 60.0:.1f} m"
        
        return [
            ("Total NNs", str(total_beats)),
            ("AVG HR", f"{avg_hr:.0f} bpm"),
            ("Max HR", f"{max_hr:.0f} bpm"),
            ("Min HR", f"{min_hr:.0f} bpm"),
            ("Longest RR Interval", f"{longest_rr:.2f}s"),
            ("RRI (>=2.0s)", str(pauses)),
            ("During Tachy (>100)", f"{tachy_pct:.1f}%"),
            ("During Brady (<60)", f"{brady_pct:.1f}%"),
            ("AF Duration", af_dur_str),
            ("V Total", str(ve)),
            ("S Total", str(sve)),
        ]


# â”€â”€ Helper canvas widgets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class LorenzCanvas(QWidget):
    """Simple RR scatter / Poincar? plot."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._x = []
        self._y = []
        self._x_range = None
        self._y_range = None
        self.setMinimumSize(200, 180)
        self.setStyleSheet(f"background:{COL_BLACK};border:none;")

    def set_data(self, x, y, x_range=None, y_range=None):
        self._x = list(x)
        self._y = list(y)
        self._x_range = x_range
        self._y_range = y_range
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COL_BLACK))
        w, h = self.width(), self.height()
        left, top, right, bottom = 32, 16, 16, 28
        plot_w = max(1, w - left - right)
        plot_h = max(1, h - top - bottom)

        if not self._x or not self._y:
            painter.setPen(QPen(QColor(COL_GREEN_DRK)))
            painter.drawText(self.rect(), Qt.AlignCenter, "No RR data")
            return

        all_vals = self._x + self._y
        if self._x_range is not None and self._y_range is not None:
            x_min, x_max = self._x_range
            y_min, y_max = self._y_range
        else:
            lo = float(np.percentile(all_vals, 5))
            hi = float(np.percentile(all_vals, 95))
            if hi - lo < 250:
                center = float(np.median(all_vals))
                lo = center - 500.0
                hi = center + 500.0
            x_min = y_min = max(0.0, lo - 50.0)
            x_max = y_max = hi + 50.0
            if x_max - x_min < 500.0:
                mid = (x_min + x_max) / 2.0
                x_min = y_min = max(0.0, mid - 250.0)
                x_max = y_max = mid + 250.0

        rng_x = max(x_max - x_min, 1.0)
        rng_y = max(y_max - y_min, 1.0)

        def to_px(val_x, val_y):
            px = int(left + (val_x - x_min) / rng_x * plot_w)
            py = int(top + plot_h - (val_y - y_min) / rng_y * plot_h)
            return px, py

        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#1C2C43"), 1))
        painter.drawRect(left, top, plot_w, plot_h)
        for frac in (0.25, 0.5, 0.75):
            x = int(left + frac * plot_w)
            y = int(top + frac * plot_h)
            painter.drawLine(x, top, x, top + plot_h)
            painter.drawLine(left, y, left + plot_w, y)

        if x_max > x_min:
            pen = QPen(QColor("#006B2D"))
            pen.setWidth(1)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            start = to_px(x_min, x_min)
            end = to_px(x_max, x_max)
            painter.drawLine(start[0], start[1], end[0], end[1])

        pen = QPen(QColor("#39D353"))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(57, 211, 83, 180)))
        for x, y in zip(self._x, self._y):
            px, py = to_px(x, y)
            painter.drawEllipse(px - 2, py - 2, 4, 4)

        painter.setPen(QPen(QColor(COL_GREEN_DRK)))
        painter.drawText(left, h - 8, "RR(n) ms")
        painter.drawText(w - 88, 14, "RR(n+1)")
        painter.drawText(w // 2 - 34, h - 2, f"{int(x_min)}-{int(x_max)}ms")

class ECGStripCanvas(QWidget):
    """Simple ECG strip renderer with interactive measurement tools."""
    def __init__(self, parent=None, height: int = 80, color: str = "#00FF00", pen_width: float = 0.7, lead_name: str = ""):
        super().__init__(parent)
        self._data = np.zeros(200)
        self._color = color
        self._pen_width = pen_width
        self.lead_name = lead_name
        self._gain = 1.0
        self._speed = 25
        self.setFixedHeight(height)
        self.setStyleSheet(f"background:{COL_BLACK};border:none;")
        self.setMouseTracking(True)
        self._mode = TOOL_SELECT
        self._start_pos = None
        self._curr_pos = None
        self._hover_pos = None
        self._magnify_locked = False
        self._magnify_pos = None
        self._fs = 500.0

    def _find_magnifier_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "set_magnifier_focus") and hasattr(parent, "clear_magnifier_focus"):
                return parent
            parent = parent.parentWidget()
        return None

    def _magnifier_source_payload(self):
        return {
            "data": np.asarray(self._data, dtype=float).copy(),
            "speed": float(self._speed),
            "gain": float(self._gain),
            "lead_name": getattr(self, "lead_name", ""),
            "fs": float(self._fs),
        }

    def set_gain(self, gain: float):
        self._gain = gain
        self.update()

    def set_paper_speed(self, speed: int):
        self._speed = speed
        self.update()

    def set_mode(self, mode: str):
        host = self._find_magnifier_host()
        if host is not None and self._mode == TOOL_MAGNIFY and canonical_tool(mode) != TOOL_MAGNIFY:
            host.clear_magnifier_focus(self)
        self._mode = canonical_tool(mode)
        self._start_pos = None
        self._curr_pos = None
        self._hover_pos = None
        self._magnify_locked = False
        self._magnify_pos = None
        self.update()

    def clear_interaction(self):
        self._start_pos = None
        self._curr_pos = None
        self._hover_pos = None
        self._magnify_locked = False
        self._magnify_pos = None
        self.update()

    def set_data(self, *args, beat_annotations=None, start_sec=0.0):
        if len(args) == 2:
            raw_data = np.asarray(args[1], dtype=float)
        elif len(args) == 1:
            raw_data = np.asarray(args[0], dtype=float)
        else:
            raw_data = np.zeros(0)
            
        if len(raw_data) > 15:
            try:
                from scipy.signal import butter, filtfilt
                b, a = butter(2, 25.0 / (self._fs / 2.0), btype='lowpass')
                self._data = filtfilt(b, a, raw_data)
            except Exception:
                self._data = raw_data
        else:
            self._data = raw_data
            
        self._beat_annotations = beat_annotations or []
        self._start_sec = start_sec
        self.update()

    def mousePressEvent(self, event):
        if self._mode == TOOL_MAGNIFY and event.button() == Qt.LeftButton:
            # Click-to-lock magnifier: each click moves the zoom lens to that point.
            # Switching away from the tool clears the lock.
            self._magnify_locked = True
            self._magnify_pos = event.pos()
            self._hover_pos = event.pos()
            host = self._find_magnifier_host()
            if host is not None:
                host.set_magnifier_focus(self, self._magnifier_source_payload(), event.pos())
            self.update()
            return

        if self._mode != TOOL_SELECT:
            self._start_pos = event.pos()
            self._curr_pos = event.pos()
            self._hover_pos = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._mode == TOOL_MAGNIFY:
            if self._magnify_locked:
                if event.buttons() & Qt.LeftButton:
                    self._magnify_pos = event.pos()
                    host = self._find_magnifier_host()
                    if host is not None:
                        host.set_magnifier_focus(self, self._magnifier_source_payload(), event.pos())
                self.update()
                return
            self._hover_pos = event.pos()
            self.update()
            return
        self._hover_pos = event.pos()
        if self._mode != TOOL_SELECT and self._start_pos is not None:
            self._curr_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if self._mode == TOOL_MAGNIFY:
            if not self._magnify_locked:
                self._hover_pos = event.pos()
            self.update()
            return
        if self._mode != TOOL_SELECT:
            self._curr_pos = event.pos()
            self.update()

    def leaveEvent(self, event):
        if not self._magnify_locked:
            self._hover_pos = None
        self.update()
        super().leaveEvent(event)

    def _get_display_signal(self):
        if self._data.size < 2:
            return np.array([]), 0.0, 1.0
        sig = np.asarray(self._data, dtype=float)
        
        # Calculate the true baseline of the raw signal
        baseline = float(np.median(sig))
        
        # Apply gain relative to the baseline
        d = (sig - baseline) * self._gain + baseline
        
        # Universally center the signal for ALL leads. 
        # By dynamically setting the minimum bound relative to the baseline,
        # we ensure the baseline always maps perfectly to the vertical center (y = 0.5 * h),
        # while strictly preserving the 4096 amplitude uncropped scale.
        mn = baseline - 2048.0
        return d, mn, 4096.0

    def _x_to_index(self, x: int, width: int, n: int) -> int:
        if n <= 1 or width <= 1:
            return 0
        x = max(0, min(x, width - 1))
        return int(round((x / float(width - 1)) * (n - 1)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COL_BLACK))
        w, h = self.width(), self.height()
        minor_pen = QPen(QColor(COL_GRID_MINOR))
        minor_pen.setWidth(1)
        major_pen = QPen(QColor(COL_GRID_MAJOR))
        major_pen.setWidth(1)
        for gx in range(0, w, 20):
            painter.setPen(major_pen if gx % 100 == 0 else minor_pen)
            painter.drawLine(gx, 0, gx, h)
        for gy in range(0, h, 20):
            painter.setPen(major_pen if gy % 100 == 0 else minor_pen)
            painter.drawLine(0, gy, w, gy)

        if self._data.size < 2:
            return
        d, mn, rng = self._get_display_signal()
        if d.size < 2:
            return
        
        pen = QPen(QColor(self._color))
        pen.setWidthF(self._pen_width)
        painter.setPen(pen)
        # --- Paper speed: control how many samples are visible per screen width ---
        # At 25mm/s: show all data. At 50mm/s: stretch (show half). At 12.5mm/s: compress (show double).
        speed_factor = max(0.25, min(float(self._speed) / 25.0, 4.0))
        n_visible = max(2, int(round(len(d) / speed_factor)))
        if n_visible < len(d):
            d = d[-n_visible:]   # show the most recent n_visible samples (stretched)
        # (if n_visible >= len(d) we show all data, which appears compressed at slow speed)
        x_scale = w / max(1, len(d) - 1)
        for i in range(1, len(d)):
            x1 = (i - 1) * x_scale
            y1 = h - (d[i-1] - mn) / rng * h
            x2 = i * x_scale
            y2 = h - (d[i] - mn) / rng * h
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            
        # --- Draw Clinical Beat Annotations ---
        if hasattr(self, '_beat_annotations') and self._beat_annotations:
            font = painter.font()
            font.setPixelSize(10)
            font.setBold(True)
            painter.setFont(font)
            
            end_sec = self._start_sec + len(d) / self._fs
            
            for beat in self._beat_annotations:
                ts = beat['timestamp']
                # Check if beat is within the visible window
                if self._start_sec <= ts <= end_sec:
                    # Calculate x coordinate
                    pct = (ts - self._start_sec) / (end_sec - self._start_sec)
                    bx = int(pct * w)
                    
                    lbl = beat['label']
                    # Color code labels: Normal=White, PVC=Red, PAC=Cyan, AF=Magenta, Pause/Block=Yellow
                    if lbl == 'N':
                        color = COL_WHITE
                    elif lbl == 'V':
                        color = "#FF3333"
                    elif lbl == 'S':
                        color = "#00FFFF"
                    elif lbl == 'AF':
                        color = "#FF00FF"
                    else:
                        color = "#FFFF00"
                        
                    painter.setPen(QPen(QColor(color)))
                    painter.drawText(bx - 4, 12, lbl)
                    
        if self._mode == TOOL_RULER and self._start_pos and self._curr_pos:
            rpen = QPen(QColor("#00FFFF"), 2, Qt.DashLine)
            painter.setPen(rpen)
            painter.drawLine(self._start_pos, self._curr_pos)
            dx = abs(self._curr_pos.x() - self._start_pos.x())
            ms = interval_ms_from_pixels(dx, max(1, w), len(d), self._fs)
            bpm = 60000 / ms if ms > 0 else 0
            dy_mv = amplitude_mv_from_pixels(abs(self._curr_pos.y() - self._start_pos.y()), max(1, h), rng, ADC_TO_MV)
            painter.setPen(QPen(QColor("#00FFFF")))
            painter.drawText(self._curr_pos.x(), max(12, self._curr_pos.y() - 6), ruler_label(ms, dy_mv, bpm))
        elif self._mode == TOOL_CALIPER and self._start_pos and self._curr_pos:
            ppen = QPen(QColor("#FFFF00"), 1)
            painter.setPen(ppen)
            painter.drawLine(self._start_pos.x(), 0, self._start_pos.x(), h)
            painter.drawLine(self._curr_pos.x(), 0, self._curr_pos.x(), h)
            dx = abs(self._curr_pos.x() - self._start_pos.x())
            ms = interval_ms_from_pixels(dx, max(1, w), len(d), self._fs)
            painter.drawText(min(self._start_pos.x(), self._curr_pos.x()) + dx//2, 12, caliper_label(ms))
        elif self._mode == TOOL_MAGNIFY:
            host = self._find_magnifier_host()
            if host is not None and hasattr(host, "_magnifier_overlay"):
                return
            focus_pos = self._magnify_pos if self._magnify_locked else self._hover_pos
            if focus_pos is None:
                return
            hover_x = max(0, min(focus_pos.x(), w - 1))
            hover_y = max(0, min(focus_pos.y(), h - 1))
            src_center = self._x_to_index(hover_x, w, len(d))
            span = max(12, int(len(d) / max(2.0, self._speed / 12.5) / max(2, getattr(self.parent(), "_curr_length_idx", 1) + 2)))
            half = max(8, int(span / max(2, self._gain * 1.5)))
            i0 = max(0, src_center - half)
            i1 = min(len(d), src_center + half)
            sub = d[i0:i1]

            panel_w = min(320, max(220, int(w * 0.34)))
            panel_h = min(180, max(120, int(h * 0.72)))
            panel_x = min(w - panel_w - 10, hover_x + 24)
            panel_y = max(8, hover_y - panel_h - 18)
            if panel_x < 8:
                panel_x = 8
            if panel_y < 8:
                panel_y = min(h - panel_h - 8, hover_y + 18)

            panel_rect = QRect(panel_x, panel_y, panel_w, panel_h)
            inner = panel_rect.adjusted(10, 10, -10, -10)

            painter.setBrush(QColor(8, 8, 8, 235))
            painter.setPen(QPen(QColor(COL_YELLOW), 3))
            painter.drawRoundedRect(panel_rect, 12, 12)

            painter.setPen(QPen(QColor(COL_GRID_MINOR), 1))
            for frac in (0.25, 0.5, 0.75):
                gx = int(inner.left() + inner.width() * frac)
                gy = int(inner.top() + inner.height() * frac)
                painter.drawLine(gx, inner.top(), gx, inner.bottom())
                painter.drawLine(inner.left(), gy, inner.right(), gy)

            if len(sub) > 1:
                sub_min = float(np.min(sub))
                sub_max = float(np.max(sub))
                
                # Symmetrically frame the magnifier around the local median baseline
                # This prevents asymmetrical waves from pushing the baseline to the bottom/top edge
                base_val = float(np.median(sub))
                max_dev = max(abs(sub_max - base_val), abs(sub_min - base_val))
                pad = max(20.0, max_dev * 0.35)
                view_min = base_val - max_dev - pad
                view_max = base_val + max_dev + pad
                view_rng = max(1.0, view_max - view_min)

                path_pen = QPen(QColor(self._color))
                path_pen.setWidthF(2.0)
                painter.setPen(path_pen)
                x_scale_sub = inner.width() / max(1, len(sub) - 1)
                prev = None
                for i in range(len(sub)):
                    xx = inner.left() + i * x_scale_sub
                    yy = inner.bottom() - ((sub[i] - view_min) / view_rng) * inner.height()
                    if prev is not None:
                        painter.drawLine(QPointF(prev[0], prev[1]), QPointF(xx, yy))
                    prev = (xx, yy)

                focus_x = int(inner.left() + ((src_center - i0) / max(1, len(sub) - 1)) * inner.width())
                focus_y = int(inner.bottom() - ((d[src_center] - view_min) / view_rng) * inner.height())
                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.drawLine(focus_x, inner.top(), focus_x, inner.bottom())
                painter.drawLine(inner.left(), focus_y, inner.right(), focus_y)

            painter.setPen(QPen(QColor(COL_WHITE)))
            painter.drawText(
                panel_rect.left() + 10,
                panel_rect.bottom() - 10,
                f"{getattr(self.parent(), '_curr_gain_idx', 1) + 2}x {'locked' if self._magnify_locked else 'hover'}"
            )


class MagnifierOverlay(QWidget):
    """Shared magnifier popup for the replay panel so zoom is never clipped by strip bounds."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._visible = False
        self._panel_rect = QRect()
        self._inner_rect = QRect()
        self._data = None
        self._focus_idx = 0
        self._focus_pos = QPoint(0, 0)
        self._gain = 1.0
        self._speed = 25.0
        self._fs = 500.0
        self._lead_name = ""
        self._source_widget = None
        self.hide()

    def set_focus(self, source_widget, payload: dict, focus_pos: QPoint):
        if payload is None or payload.get("data") is None:
            self.hide()
            return
        self._source_widget = source_widget
        self._data = np.asarray(payload.get("data"), dtype=float)
        self._gain = float(payload.get("gain", 1.0))
        self._speed = float(payload.get("speed", 25.0))
        self._fs = float(payload.get("fs", 500.0))
        self._lead_name = str(payload.get("lead_name", ""))
        self._focus_pos = QPoint(focus_pos)
        if self.parentWidget() is None:
            self.hide()
            return
        host = self.parentWidget()
        self.setGeometry(host.rect())
        self.raise_()
        self._visible = True
        self.show()
        self.update()

    def clear_focus(self, source_widget=None):
        if source_widget is not None and self._source_widget is not None and source_widget is not self._source_widget:
            return
        self._visible = False
        self._data = None
        self._source_widget = None
        self.hide()
        self.update()

    def paintEvent(self, event):
        if not self._visible or self._data is None or self._source_widget is None:
            return
        d = np.asarray(self._data, dtype=float)
        if d.size < 2:
            return

        host = self.parentWidget()
        if host is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Convert the focus point from source-widget coordinates into overlay coordinates.
        try:
            focus_pt = self._source_widget.mapTo(host, self._focus_pos)
        except Exception:
            focus_pt = self._focus_pos
        hover_x = max(0, min(int(focus_pt.x()), max(0, host.width() - 1)))
        hover_y = max(0, min(int(focus_pt.y()), max(0, host.height() - 1)))

        w, h = host.width(), host.height()
        source_w = max(1, int(self._source_widget.width()))
        local_x = max(0, min(int(self._focus_pos.x()), source_w - 1))
        src_center = int(round((local_x / float(max(1, source_w - 1))) * (len(d) - 1)))
        span = max(12, int(len(d) / max(2.0, self._speed / 12.5) / 2.0))
        half = max(8, int(span / max(2, self._gain * 1.5)))
        i0 = max(0, src_center - half)
        i1 = min(len(d), src_center + half)
        sub = d[i0:i1]
        if len(sub) < 2:
            return

        panel_w = min(360, max(240, int(w * 0.34)))
        panel_h = min(220, max(140, int(h * 0.28)))
        panel_x = hover_x + 24
        panel_y = hover_y - panel_h - 18
        if panel_x + panel_w > w - 8:
            panel_x = hover_x - panel_w - 24
        if panel_x < 8:
            panel_x = 8
        if panel_y < 8:
            panel_y = hover_y + 18
        if panel_y + panel_h > h - 8:
            panel_y = max(8, h - panel_h - 8)
        self._panel_rect = QRect(panel_x, panel_y, panel_w, panel_h)
        self._inner_rect = self._panel_rect.adjusted(12, 12, -12, -12)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 220))
        painter.drawRoundedRect(self._panel_rect, 12, 12)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(COL_YELLOW), 3))
        painter.drawRoundedRect(self._panel_rect, 12, 12)

        painter.setPen(QPen(QColor(COL_GRID_MINOR), 1))
        for frac in (0.25, 0.5, 0.75):
            gx = int(self._inner_rect.left() + self._inner_rect.width() * frac)
            gy = int(self._inner_rect.top() + self._inner_rect.height() * frac)
            painter.drawLine(gx, self._inner_rect.top(), gx, self._inner_rect.bottom())
            painter.drawLine(self._inner_rect.left(), gy, self._inner_rect.right(), gy)

        sub_min = float(np.min(sub))
        sub_max = float(np.max(sub))
        base_val = float(np.median(sub))
        max_dev = max(abs(sub_max - base_val), abs(sub_min - base_val))
        pad = max(20.0, max_dev * 0.35)
        view_min = base_val - max_dev - pad
        view_max = base_val + max_dev + pad
        view_rng = max(1.0, view_max - view_min)

        path_pen = QPen(QColor("#22FF44"))
        path_pen.setWidthF(2.0)
        painter.setPen(path_pen)
        x_scale_sub = self._inner_rect.width() / max(1, len(sub) - 1)
        prev = None
        for i in range(len(sub)):
            xx = self._inner_rect.left() + i * x_scale_sub
            yy = self._inner_rect.bottom() - ((sub[i] - view_min) / view_rng) * self._inner_rect.height()
            if prev is not None:
                painter.drawLine(QPointF(prev[0], prev[1]), QPointF(xx, yy))
            prev = (xx, yy)

        focus_x = int(self._inner_rect.left() + ((src_center - i0) / max(1, len(sub) - 1)) * self._inner_rect.width())
        focus_y = int(self._inner_rect.bottom() - ((d[src_center] - view_min) / view_rng) * self._inner_rect.height())
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawLine(focus_x, self._inner_rect.top(), focus_x, self._inner_rect.bottom())
        painter.drawLine(self._inner_rect.left(), focus_y, self._inner_rect.right(), focus_y)

        painter.setPen(QPen(QColor(COL_WHITE)))
        painter.drawText(
            self._panel_rect.left() + 10,
            self._panel_rect.top() + 18,
            f"{self._lead_name or 'Lead'}  {self._gain:.1f}x"
        )
        painter.drawText(
            self._panel_rect.left() + 10,
            self._panel_rect.bottom() - 10,
            "click another wave to move"
        )


# -----------------------------------------------------------------------------
# 7. HOLTER EVENTS PANEL
# -----------------------------------------------------------------------------

class HolterRRTrendCanvas(QWidget):
    """Compact RR trend strip matching Holter Expert reference: dark bg, grid, Y-axis 0-2000ms, time labels."""

    def __init__(self, parent=None, title="RR Interval"):
        super().__init__(parent)
        self._title = title
        self._points = []        # [(time_sec, rr_ms), ...]
        self._start_epoch = None # unix epoch for beat 0, used for HH:MM labels
        self._show_hr = False    # False=RR ms, True=HR bpm
        self._selection_range = None  # (t_start, t_end) cyan box for zoom indicator
        self.setMinimumHeight(80)
        self.setStyleSheet("background:#0a1520;border:1px solid #1e3350;border-radius:4px;")

    # ------------------------------------------------------------------ API --
    def set_points(self, points, start_epoch=None):
        self._points = list(points or [])
        if start_epoch is not None:
            self._start_epoch = start_epoch
        self.update()

    def set_selection(self, t_start, t_end):
        """Mark a time window with a cyan box (used on the Full chart to show Recent window)."""
        self._selection_range = (t_start, t_end)
        self.update()

    # ---------------------------------------------------------- paintEvent --
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()

        # -- Background ------------------------------------------------------
        painter.fillRect(self.rect(), QColor("#0a1520"))

        # Margins: left for Y-axis, bottom for X-axis
        LM, RM, TM, BM = 52, 10, 22, 24
        iw = max(1, w - LM - RM)
        ih = max(1, h - TM - BM)
        inner = QRect(LM, TM, iw, ih)

        # -- Title (top-left) -------------------------------------------------
        painter.setPen(QPen(QColor("#7ecfff"), 1))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(LM, 16, self._title)

        # -- Y-axis config ----------------------------------------------------
        if self._show_hr:
            y_min, y_max = 20, 220
            y_ticks = [40, 80, 120, 160, 200]
            y_unit = "bpm"
        else:
            y_min, y_max = 0, 2000
            y_ticks = [0, 500, 1000, 1500, 2000]
            y_unit = "ms"
        y_rng = float(y_max - y_min)

        def to_y(val):
            v = max(y_min, min(y_max, val))
            return inner.bottom() - int(((v - y_min) / y_rng) * ih)

        # -- Horizontal grid lines + Y labels --------------------------------
        painter.setFont(QFont("Arial", 9, QFont.Bold))
        for yv in y_ticks:
            yp = to_y(yv)
            painter.setPen(QPen(QColor("#1e3d5a"), 1, Qt.DashLine))
            painter.drawLine(inner.left(), yp, inner.right(), yp)
            painter.setPen(QPen(QColor("#7ecfff"), 1))
            lbl = str(yv)
            painter.drawText(2, yp + 5, lbl)

        # -- No data message -------------------------------------------------
        if not self._points:
            painter.setPen(QPen(QColor("#3a5a70"), 1))
            painter.setFont(QFont("Arial", 11))
            painter.drawText(inner, Qt.AlignCenter, "No RR data")
            painter.setPen(QPen(QColor("#1e3350"), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(inner)
            return

        # -- Time range ------------------------------------------------------
        t_vals = [p[0] for p in self._points]
        t_min = min(t_vals)
        t_max = max(t_vals)
        if t_max <= t_min:
            t_max = t_min + 1.0
        t_rng = float(t_max - t_min)

        def to_x(t):
            return inner.left() + int(((t - t_min) / t_rng) * iw)

        # â”€â”€ Vertical grid every ~2 hours â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        grid_interval = 7200.0  # 2 hours in seconds
        t_grid = (int(t_min / grid_interval) + 1) * grid_interval
        while t_grid < t_max:
            xp = to_x(t_grid)
            painter.setPen(QPen(QColor("#1e3d5a"), 1, Qt.DashLine))
            painter.drawLine(xp, inner.top(), xp, inner.bottom())
            t_grid += grid_interval

        # â”€â”€ Scatter dots â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#00ff66")))

        # Sub-sample for performance (max ~4000 dots)
        step = max(1, len(self._points) // 4000)
        for i in range(0, len(self._points), step):
            t, rr = self._points[i]
            if self._show_hr:
                val = (60000.0 / rr) if rr > 0 else 0
            else:
                val = float(rr)
            if val <= 0:
                continue
            px = to_x(t)
            py = to_y(val)
            painter.drawEllipse(px - 2, py - 2, 4, 4)

        # â”€â”€ Cyan selection box â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self._selection_range is not None:
            rs, re_t = self._selection_range
            sx = max(inner.left(), min(inner.right(), to_x(rs)))
            ex = max(inner.left(), min(inner.right(), to_x(re_t)))
            painter.setPen(QPen(QColor("#00cccc"), 1))
            painter.setBrush(QBrush(QColor(0, 204, 204, 30)))
            painter.drawRect(sx, inner.top(), max(2, ex - sx), ih)

        # â”€â”€ X-axis time labels â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        painter.setPen(QPen(QColor("#7ecfff"), 1))
        painter.setFont(QFont("Arial", 9, QFont.Bold))
        import datetime as _dt
        n_xticks = max(2, min(8, iw // 75))
        for i in range(n_xticks + 1):
            frac = i / float(n_xticks)
            t_at = t_min + frac * t_rng
            xp = inner.left() + int(frac * iw)
            painter.setPen(QPen(QColor("#2e5a80"), 1))
            painter.drawLine(xp, inner.bottom(), xp, inner.bottom() + 3)
            painter.setPen(QPen(QColor("#7ecfff"), 1))
            if self._start_epoch is not None:
                ts = _dt.datetime.fromtimestamp(self._start_epoch + t_at)
                label = ts.strftime("%H:%M")
            else:
                hrs = int(t_at // 3600)
                mins = int((t_at % 3600) // 60)
                label = f"{hrs:02d}:{mins:02d}"
            painter.drawText(xp - 14, inner.bottom() + BM - 2, label)

        # â”€â”€ Border â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        painter.setPen(QPen(QColor("#1e3350"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(inner)

class HolterExpertReviewPanel(QWidget):
    """HolterExpert-inspired review layout: trend + Lorenz + strips + overview."""
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._metrics = []
        self._summary = {}
        self._template_rows = []
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._rr_trend_full = HolterRRTrendCanvas(title="RR Interval Trend (Full)")
        self._rr_trend_zoom = HolterRRTrendCanvas(title="RR Interval Trend (Recent)")
        layout.addWidget(self._rr_trend_full)
        layout.addWidget(self._rr_trend_zoom)

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(1)
        body.setStyleSheet(f"QSplitter{{background:{UI_BG};}} QSplitter::handle{{background:{UI_BORDER};}}")

        left = QFrame()
        left.setStyleSheet(f"QFrame{{background:{UI_PANEL};border:1px solid {UI_BORDER};border-radius:8px;}}")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(8, 8, 8, 8)
        left_l.setSpacing(8)
        self._lorenz = LorenzCanvas()
        self._lorenz.setMinimumHeight(280)
        left_l.addWidget(self._lorenz, 2)
        self._template_table = QTableWidget(0, 3)
        self._template_table.setHorizontalHeaderLabels(["Template", "Class", "Beats"])
        self._template_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._template_table.verticalHeader().setVisible(False)
        self._template_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._template_table.setStyleSheet(_table_style())
        self._template_table.cellClicked.connect(self._on_template_clicked)
        left_l.addWidget(self._template_table, 1)
        body.addWidget(left)

        # â”€â”€ Center: scrollable 12-lead ECG grid â”€â”€
        center = QFrame()
        center.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid {UI_BORDER};border-radius:8px;}}")
        center_l = QVBoxLayout(center)
        center_l.setContentsMargins(4, 4, 4, 4)
        center_l.setSpacing(0)

        # 12-lead header
        hdr = QLabel("12-Lead ECG Overview")
        hdr.setStyleSheet(f"color:{UI_TEXT};font-size:11px;font-weight:700;padding:4px 6px;border:none;")
        center_l.addWidget(hdr)

        leads_scroll = QScrollArea()
        leads_scroll.setWidgetResizable(True)
        leads_scroll.setFrameShape(QFrame.NoFrame)
        leads_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        leads_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        leads_scroll.setStyleSheet(f"QScrollArea{{background:{COL_BLACK};border:none;}}")
        leads_container = QWidget()
        leads_container.setStyleSheet(f"background:{COL_BLACK};")
        leads_vbox = QVBoxLayout(leads_container)
        leads_vbox.setContentsMargins(2, 2, 2, 2)
        leads_vbox.setSpacing(2)

        self._lead_names_12 = ["I","II","III","aVR","aVL","aVF","V1","V2","V3","V4","V5","V6"]
        self._expert_lead_strips = {}  # lead_name -> ECGStripCanvas
        for lead in self._lead_names_12:
            row_h = QHBoxLayout()
            row_h.setContentsMargins(0, 0, 0, 0)
            row_h.setSpacing(4)
            lbl = QLabel(lead)
            lbl.setFixedWidth(34)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet(f"color:{COL_GREEN};font-weight:bold;font-size:10px;border:none;")
            strip = ECGStripCanvas(height=60, color="#00FF00", pen_width=0.9, lead_name=lead)
            strip.set_gain(1.0)
            self._expert_lead_strips[lead] = strip
            row_h.addWidget(lbl)
            row_h.addWidget(strip, 1)
            leads_vbox.addLayout(row_h)

        leads_scroll.setWidget(leads_container)
        center_l.addWidget(leads_scroll, 1)

        # Rhythm strip at bottom (Lead II)
        rhythm_row = QHBoxLayout()
        rhythm_row.setSpacing(4)
        rlbl = QLabel("II")
        rlbl.setFixedWidth(34)
        rlbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        rlbl.setStyleSheet(f"color:{COL_GREEN};font-weight:bold;font-size:10px;border:none;")
        self._mini = ECGStripCanvas(height=40, color="#00AA00", pen_width=0.9)
        rhythm_row.addWidget(rlbl)
        rhythm_row.addWidget(self._mini, 1)
        center_l.addLayout(rhythm_row)

        body.addWidget(center)

        right = QFrame()
        right.setStyleSheet(f"QFrame{{background:{UI_PANEL};border:1px solid {UI_BORDER};border-radius:8px;}}")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(8, 8, 8, 8)
        right_l.setSpacing(6)
        ttl = QLabel("Overview")
        ttl.setStyleSheet(f"color:{UI_TEXT};font-weight:700;font-size:13px;padding:6px;background:{UI_PANEL_ALT};border:1px solid {UI_BORDER};border-radius:6px;")
        right_l.addWidget(ttl)
        self._overview = QTableWidget(0, 2)
        self._overview.setHorizontalHeaderLabels(["Name", "Value"])
        self._overview.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._overview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._overview.verticalHeader().setVisible(False)
        self._overview.setEditTriggers(QTableWidget.NoEditTriggers)
        self._overview.setStyleSheet(_table_style())
        right_l.addWidget(self._overview, 1)
        body.addWidget(right)
        body.setSizes([360, 760, 300])
        layout.addWidget(body, 1)

    def update_from_metrics(self, metrics_list: list, summary: dict):
        self._metrics = list(metrics_list or [])
        self._summary = dict(summary or {})
        rr_points = []
        for m in self._metrics:
            t0 = float(m.get("t", 0.0) or 0.0)
            rr_list = list(m.get("rr_intervals_list", []) or [])
            dur = float(m.get("duration", 0.0) or 0.0)
            n = max(1, len(rr_list))
            step = (dur / n) if dur > 0 else 0.2
            for i, rr in enumerate(rr_list):
                rr_points.append((t0 + i * step, float(rr)))



        start_epoch = summary.get("start_time_epoch", None)
        self._rr_trend_full.set_points(rr_points, start_epoch)
        
        # Recent is the last 4 hours (14400 seconds)
        if rr_points:
            t_max = rr_points[-1][0]
            recent = [p for p in rr_points if p[0] >= t_max - 14400]
            if not recent:
                recent = rr_points[-4000:]
        else:
            recent = []
            
        self._rr_trend_zoom.set_points(recent, start_epoch)
        
        if recent and rr_points:
            self._rr_trend_full.set_selection(recent[0][0], recent[-1][0])
            
        x = [p[1] for p in recent[:-1]] if len(recent) > 1 else []
        y = [p[1] for p in recent[1:]] if len(recent) > 1 else []
        self._lorenz.set_data(x, y)

        tm = {}
        for m in self._metrics:
            for row in (m.get("template_summary", []) or []):
                key = row.get("template_key") or row.get("template_id") or row.get("label") or "T"
                r = tm.setdefault(key, {"id": row.get("template_id", "T"), "label": row.get("label", "N"), "count": 0, "first": float(row.get("first_timestamp", m.get("t", 0.0)) or 0.0)})
                r["count"] += int(row.get("count", 0) or 0)
                r["first"] = min(r["first"], float(row.get("first_timestamp", r["first"]) or r["first"]))
        self._template_rows = sorted(tm.values(), key=lambda it: it["count"], reverse=True)
        self._template_table.setRowCount(len(self._template_rows))
        for i, row in enumerate(self._template_rows):
            vals = [str(row["id"]), str(row["label"]), str(row["count"])]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setForeground(QColor(UI_TEXT))
                self._template_table.setItem(i, j, item)

        # Compute tachy/brady durations from summary
        _dur_sec = float(summary.get('duration_sec', 0) or 0)
        _total_beats = int(summary.get('total_beats', 0) or 1)
        # Use pre-computed sec values if available (set by _build_summary_from_metrics)
        if 'tachy_sec' in summary:
            _tachy_sec = float(summary['tachy_sec'] or 0)
            _brady_sec = float(summary['brady_sec'] or 0)
            _tachy_pct = float(summary.get('tachy_pct', 0) or 0)
            _brady_pct = float(summary.get('brady_pct', 0) or 0)
        else:
            _tachy_beats = int(summary.get('tachy_beats', 0) or 0)
            _brady_beats = int(summary.get('brady_beats', 0) or 0)
            _avg_rr_sec = (_dur_sec / _total_beats) if _total_beats > 0 and _dur_sec > 0 else 0.0
            _tachy_sec = _tachy_beats * _avg_rr_sec
            _brady_sec = _brady_beats * _avg_rr_sec
            _tachy_pct = (_tachy_beats / _total_beats * 100) if _total_beats > 0 else 0.0
            _brady_pct = (_brady_beats / _total_beats * 100) if _total_beats > 0 else 0.0
        def _fmt_dur(sec):
            s = int(sec); h = s // 3600; m = (s % 3600) // 60; ss = s % 60
            return f"{h:02d}:{m:02d}:{ss:02d}"
        _tachy_str = f"{_fmt_dur(_tachy_sec)} {_tachy_pct:.2f}%"
        _brady_str = f"{_fmt_dur(_brady_sec)} {_brady_pct:.2f}%"

        # Sinus HR from summary (falls back to max_hr/min_hr)
        _sinus_max = summary.get('sinus_max_hr', summary.get('max_hr', 0))
        _sinus_min = summary.get('sinus_min_hr', summary.get('min_hr', 0))
        _sinus_max_t = summary.get('sinus_max_hr_time', '')
        _sinus_min_t = summary.get('sinus_min_hr_time', '')
        _max_hr_t = summary.get('max_hr_time', '')
        _min_hr_t = summary.get('min_hr_time', '')

        # AF duration from arrhythmia_counts
        _af_count = int((summary.get('arrhythmia_counts') or {}).get('AF', 0))
        _af_chunk_dur = 4.0  # each metric chunk ~4s
        _af_sec = _af_count * _af_chunk_dur
        _af_pct = (_af_sec / _dur_sec * 100) if _dur_sec > 0 else 0.0
        _af_str = f"{_fmt_dur(_af_sec)} {_af_pct:.2f}%" if _af_count > 0 else "-"

        def _hr_with_time(hr, t):
            hr_str = f"{int(round(float(hr or 0)))}bpm"
            return f"{hr_str} {t}" if t else hr_str

        rows = [
            ("Total", f"{summary.get('total_beats', 0)}"),
            ("X Total", f"{summary.get('pauses', 0)}"),
            ("AVG HR", f"{summary.get('avg_hr', 0):.0f} bpm"),
            ("Max HR", _hr_with_time(summary.get('max_hr', 0), _max_hr_t)),
            ("Min HR", _hr_with_time(summary.get('min_hr', 0), _min_hr_t)),
            ("Sinus Max HR", _hr_with_time(_sinus_max, _sinus_max_t)),
            ("Sinus Min HR", _hr_with_time(_sinus_min, _sinus_min_t)),
            ("During of Tachy.", _tachy_str),
            ("During of Brady.", _brady_str),
            ("V Total", f"{summary.get('ve_beats', 0)}"),
            ("S Total", f"{summary.get('sve_beats', 0)}"),
            ("AVG HR of Af/AF", "-"),
            ("Duration of Af/AF", _af_str),
            ("Paced Beats", "0"),
            ("Pacing AVG HR", "-"),
            ("Pacing Max HR", "-"),
            ("Pacing Min HR", "-"),
            ("Longest RR", f"{summary.get('longest_rr_ms', 0)/1000:.2f}s"),
            ("RRI (\u22652.0s)", f"{summary.get('pauses', 0)}"),
            ("ST Elevation", "-"),
            ("ST Depression", "-"),
        ]
        self._overview.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            ki = QTableWidgetItem(k)
            vi = QTableWidgetItem(v)
            ki.setForeground(QColor(UI_MUTED))
            vi.setForeground(QColor(UI_TEXT))
            self._overview.setItem(i, 0, ki)
            self._overview.setItem(i, 1, vi)

    def set_replay_frame(self, data):
        if data is None or not isinstance(data, np.ndarray) or data.ndim != 2 or data.shape[1] == 0:
            return
        n = data.shape[1]
        x = np.arange(n, dtype=float) / 500.0
        # Feed all 12 leads to the new lead-strip dict
        for i, lead in enumerate(self._lead_names_12):
            if i < data.shape[0]:
                strip = self._expert_lead_strips.get(lead)
                if strip:
                    strip.set_data(x, data[i].copy())
        # Rhythm strip: Lead II (index 1)
        if data.shape[0] > 1:
            self._mini.set_data(x, data[1].copy())
        elif data.shape[0] > 0:
            self._mini.set_data(x, data[0].copy())

    def _on_template_clicked(self, row, _col):
        if 0 <= row < len(self._template_rows):
            self.seek_requested.emit(float(self._template_rows[row].get("first", 0.0)))


class HolterEventsPanel(QWidget):
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{COL_BG};")
        self._events = []
        self._session_dir = ""
        self._selected_payload = {}
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Left: event list + stats
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        ev_title = QLabel("Events")
        ev_title.setStyleSheet(f"color:#07111F;font-size:13px;font-weight:bold;background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #28E37B, stop:1 #89F7C5);padding:6px 10px;border-radius:6px;")
        left_layout.addWidget(ev_title)

        cols = ["Event name", "Start Time", "Chan.", "Print Len.", "Source", "Conf."]
        self._ev_table = QTableWidget(0, len(cols))
        self._ev_table.setHorizontalHeaderLabels(cols)
        self._ev_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._ev_table.setStyleSheet(
            _table_style() +
            """
            QTableWidget::item:selected {
                background-color: rgba(66, 153, 225, 70);
                color: #F3F7FB;
                border: 1px solid rgba(255, 255, 255, 90);
            }
            QTableWidget::item:selected:active {
                background-color: rgba(66, 153, 225, 110);
            }
            """
        )
        self._ev_table.verticalHeader().setVisible(False)
        self._ev_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._ev_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._ev_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._ev_table.cellClicked.connect(self._on_event_clicked)
        left_layout.addWidget(self._ev_table, 1)

        # Stats below table
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"QFrame{{background:{COL_DARK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}")
        sf_layout = QGridLayout(stats_frame)
        sf_layout.setContentsMargins(8, 6, 8, 6)
        sf_layout.setSpacing(6)
        self._stat_labels = {}
        for i, (key, label) in enumerate([
            ("hr_max","HR Max"),("hr_min","HR Min"),("hr_smax","Sinus Max HR"),
            ("hr_smin","Sinus Min HR"),("brady","Bradycardia"),("user_ev","User Event"),
        ]):
            row, col = divmod(i, 2)
            l = QLabel(f"{label}:")
            l.setStyleSheet(f"color:{COL_GREEN_DRK};font-size:10px;font-weight:bold;border:none;")
            v = QLabel("-")
            v.setStyleSheet(f"color:{COL_GREEN};font-size:12px;font-weight:bold;border:none;")
            sf_layout.addWidget(l, row * 2, col)
            sf_layout.addWidget(v, row * 2 + 1, col)
            self._stat_labels[key] = v
        left_layout.addWidget(stats_frame)
        layout.addWidget(left, 1)

        # Right: navigation
        nav = QWidget()
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        for label in ["Prev Event", "Next Event", "Remove All", "Remove"]:
            btn = QPushButton(label)
            btn.setStyleSheet(_style_btn())
            btn.setFixedHeight(38)
            if label == "Prev Event":
                btn.clicked.connect(self._go_prev_event)
            elif label == "Next Event":
                btn.clicked.connect(self._go_next_event)
            elif label == "Remove All":
                btn.clicked.connect(self._remove_all_events)
            elif label == "Remove":
                btn.clicked.connect(self._remove_selected_event)
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        layout.addWidget(nav)

    def load_events(self, events: list, summary: dict):
        self._events = events
        self._ev_table.setRowCount(len(events))
        for i, ev in enumerate(events):
            t_str = _sec_to_hms(ev['timestamp'])
            source = ev.get("source", "analysis")
            conf = ev.get("confidence", 0.0)
            for j, val in enumerate([ev['label'], t_str, "3", "7s", source, f"{float(conf or 0.0):.2f}"]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(COL_WHITE))
                self._ev_table.setItem(i, j, item)
        s = summary
        for key, fmt in [("hr_max",f"{s.get('max_hr',0):.0f} bpm"),
                          ("hr_min",f"{s.get('min_hr',0):.0f} bpm"),
                          ("hr_smax",f"{s.get('max_hr',0):.0f} bpm"),
                          ("hr_smin",f"{s.get('min_hr',0):.0f} bpm"),
                          ("brady",str(s.get('brady_beats',0))),
                          ("user_ev","1")]:
            if key in self._stat_labels:
                self._stat_labels[key].setText(fmt)

    def _on_event_clicked(self, row, col):
        self._select_and_seek(row)

    def _selected_row(self) -> int:
        selection = self._ev_table.selectionModel()
        if selection:
            rows = selection.selectedRows()
            if rows:
                return int(rows[0].row())
        return -1

    def _select_and_seek(self, row: int):
        if row < 0 or row >= len(self._events):
            return
        self._ev_table.selectRow(row)
        self._selected_payload = dict(self._events[row] or {})
        self.seek_requested.emit(float(self._events[row].get('timestamp', 0.0) or 0.0))

    def _go_prev_event(self):
        if not self._events:
            return
        row = self._selected_row()
        if row < 0:
            row = 0
        else:
            row = max(0, row - 1)
        self._select_and_seek(row)

    def _go_next_event(self):
        if not self._events:
            return
        row = self._selected_row()
        if row < 0:
            row = 0
        else:
            row = min(len(self._events) - 1, row + 1)
        self._select_and_seek(row)

    def _remove_selected_event(self):
        row = self._selected_row()
        if row < 0 or row >= len(self._events):
            return
        self._events.pop(row)
        self._ev_table.removeRow(row)
        self._selected_payload = {}
        if self._events:
            next_row = min(row, len(self._events) - 1)
            self._select_and_seek(next_row)

    def _remove_all_events(self):
        self._events = []
        self._selected_payload = {}
        self._ev_table.setRowCount(0)
# -----------------------------------------------------------------------------
# ?????????????????????????????????????????????????????????????????????????????
# 8. HOLTER TEMPLATE PANEL  (template gallery)
# ?????????????????????????????????????????????????????????????????????????????

class _TemplateMetricCard(QFrame):
    def __init__(self, title: str, value: str = "", accent: str = COL_GREEN, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #1B2433, stop:1 #111827);border:1px solid {UI_BORDER};border-radius:10px;}}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{UI_MUTED};font-size:10px;font-weight:700;border:none;")
        self.value = QLabel(value)
        self.value.setStyleSheet(f"color:{UI_TEXT};font-size:16px;font-weight:800;border:none;")
        layout.addWidget(lbl)
        layout.addWidget(self.value)


class TemplateCardWidget(QFrame):
    clicked = pyqtSignal(object)
    template_id_changed = pyqtSignal(object, str)
    class_changed = pyqtSignal(object, str)
    viewed_changed = pyqtSignal(object, bool)

    def __init__(self, parent=None, accent: str = UI_BORDER):
        super().__init__(parent)
        self._accent = accent or UI_BORDER
        self._selected = False
        self._hovered = False
        self._template_key = ""
        self.setObjectName("templateCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self._build_ui()
        self.set_accent(self._accent)

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        self.setMinimumHeight(196)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._card_style = """
            QFrame#templateCard {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {bg_top}, stop:1 {bg_bottom});
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QLineEdit, QComboBox {{
                background: #0C1320;
                color: {ui_text};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 4px 7px;
                font-size: 11px;
            }}
            QComboBox QAbstractItemView {{
                background: #0B1220;
                color: {ui_text};
                selection-background-color: {ui_accent};
                selection-color: #07111F;
                border: 1px solid {border};
                outline: 0;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 4px 8px;
                min-height: 18px;
            }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {ui_accent}; }}
        """

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.id_edit = QLineEdit("T1")
        self.id_edit.setFixedWidth(70)
        self.id_edit.setPlaceholderText("T ID")
        self.class_combo = QComboBox()
        self.class_combo.addItems(["N", "S", "V", "F", "Q", "R", "O", "P", "X", "Other"])
        self.class_combo.setFixedWidth(58)
        self.count_pill = QLabel("0 beats")
        self.count_pill.setAlignment(Qt.AlignCenter)
        self.count_pill.setStyleSheet(f"color:{UI_TEXT};font-size:11px;font-weight:800;background:#152235;border:1px solid {self._accent};border-radius:10px;padding:4px 8px;")
        header.addWidget(self.id_edit)
        header.addWidget(self.class_combo)
        header.addStretch()
        header.addWidget(self.count_pill)
        layout.addLayout(header)

        self.badge_container = QWidget()
        badge_row = QHBoxLayout(self.badge_container)
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(5)
        badge_row.addStretch()
        self.badge_labels = {}
        badges_info = [
            ("ambiguous", "?", "It means that at least one classification channel of the beat under the template is not similar, so the template ECG waveform is empty, which is represented by '?'"),
            ("inserted", "+", "Templates classified by beats of inserting beats, creating new templates, or merging templates are marked with '+'"),
            ("demix", "DEMIX", "In the figure, DEMIX represents the template generated by overlay beat, new template operation after reclassification or interval reanalysis, and II represents the overlay channel used by the template."),
            ("auto_update", "AUTO", "Template generated by updating the beat is represented by 'N'")
        ]
        for key, txt, tooltip in badges_info:
            badge = QLabel(txt)
            badge.setToolTip(tooltip)
            badge.setAlignment(Qt.AlignCenter)
            badge.setVisible(False)
            badge.setStyleSheet(f"color:{UI_TEXT};font-size:10px;font-weight:800;background:#17243A;border:1px solid {UI_BORDER};border-radius:8px;padding:2px 6px;")
            self.badge_labels[key] = badge
            badge_row.addWidget(badge)
        self.setToolTip("It means that all the beat forms under the template are similar in the template")
        self.badge_container.setVisible(False)
        layout.addWidget(self.badge_container)

        self.thumb = ECGStripCanvas(height=68, color="#39D353", pen_width=1.0)
        self.thumb.setStyleSheet(f"background:{COL_BLACK};border:1px solid {self._accent};border-radius:10px;")
        layout.addWidget(self.thumb, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.template_no = QLabel("#T1")
        self.template_no.setStyleSheet(f"color:{UI_MUTED};font-size:11px;font-weight:700;border:none;")
        self.view_toggle = QToolButton()
        self.view_toggle.setCheckable(True)
        self.view_toggle.setChecked(True)
        self.view_toggle.setText("\u25c9")
        self.view_toggle.setToolTip("Viewed / unconfirmed")
        self.view_toggle.setFixedSize(26, 26)
        self.view_toggle.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {UI_BORDER};
                border-radius: 13px;
                color: {UI_TEXT};
                background: #0C1320;
                font-weight: 900;
            }}
            QToolButton:hover {{
                border-color: {UI_ACCENT_HOVER};
                background: #11203A;
            }}
            QToolButton:checked {{
                background: {UI_SUCCESS};
                color: #07111F;
                border-color: {UI_SUCCESS};
            }}
        """)
        bottom.addWidget(self.template_no)
        bottom.addStretch()
        bottom.addWidget(self.view_toggle)
        layout.addLayout(bottom)

        self.id_edit.editingFinished.connect(lambda: self.template_id_changed.emit(self, self.id_edit.text()))
        self.class_combo.currentTextChanged.connect(lambda text: self.class_changed.emit(self, text))
        self.view_toggle.toggled.connect(self._on_view_toggle)

        for widget in [self.id_edit, self.class_combo, self.count_pill, self.badge_container, self.thumb, self.template_no, self.view_toggle]:
            try:
                widget.installEventFilter(self)
            except Exception:
                pass
        for badge in self.badge_labels.values():
            try:
                badge.installEventFilter(self)
            except Exception:
                pass

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self)
        return super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        host = self._find_template_host()
        if host is not None and hasattr(host, "_show_template_card_menu"):
            host._show_template_card_menu(self, event.globalPos())
            event.accept()
            return
        return super().contextMenuEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and getattr(event, "button", lambda: None)() == Qt.LeftButton:
            self.clicked.emit(self)
        elif event.type() == QEvent.ContextMenu:
            host = self._find_template_host()
            if host is not None and hasattr(host, "_show_template_card_menu"):
                try:
                    global_pos = obj.mapToGlobal(event.pos())
                except Exception:
                    global_pos = self.mapToGlobal(event.pos())
                host._show_template_card_menu(self, global_pos)
                return True
        return super().eventFilter(obj, event)

    def _on_view_toggle(self, checked: bool):
        self.view_toggle.setText("\u25c9" if checked else "\u25cb")
        self.viewed_changed.emit(self, bool(checked))

    def _apply_styles(self):
        if self._selected:
            border = UI_ACCENT_HOVER
            bg_top = "#18263C"
            bg_bottom = "#101B2B"
        else:
            border = "#6EB4FF" if self._hovered else self._accent
            bg_top = "#141F31" if self._hovered else "#121C2D"
            bg_bottom = "#101827" if self._hovered else "#0D1521"
        self.setStyleSheet(self._card_style.format(border=border, bg_top=bg_top, bg_bottom=bg_bottom, ui_text=UI_TEXT, ui_accent=UI_ACCENT))
        self.count_pill.setStyleSheet(f"color:{UI_TEXT};font-size:11px;font-weight:800;background:#152235;border:1px solid {border};border-radius:10px;padding:4px 8px;")
        self.thumb.setStyleSheet(f"background:{COL_BLACK};border:1px solid {border};border-radius:10px;")

    def set_accent(self, accent: str):
        self._accent = accent or UI_BORDER
        self._apply_styles()

    def set_selected(self, selected: bool):
        self._selected = bool(selected)
        self._apply_styles()

    def enterEvent(self, event):
        self._hovered = True
        self._apply_styles()
        return super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._apply_styles()
        return super().leaveEvent(event)

    def set_template_data(self, data: dict):
        self._template_key = str(data.get("template_key") or data.get("template_id") or data.get("id") or "")
        template_id = str(data.get("template_id", data.get("id", "T?")))
        label = str(data.get("label", "N"))
        count = int(data.get("count", 0) or 0)
        self.id_edit.blockSignals(True)
        self.class_combo.blockSignals(True)
        self.view_toggle.blockSignals(True)
        self.id_edit.setText(template_id)
        if label and self.class_combo.findText(label) < 0:
            self.class_combo.addItem(label)
        self.class_combo.setCurrentText(label if self.class_combo.findText(label) >= 0 else (label[:1] if label else "N"))
        self.count_pill.setText(f"{count} beats")
        idx = data.get("index")
        self.template_no.setText(f"#{idx}" if idx is not None else template_id)

        flags = {
            "ambiguous": bool(data.get("ambiguous")),
            "inserted": bool(data.get("inserted")),
            "demix": bool(data.get("demix")),
            "auto_update": bool(data.get("auto_update")),
        }
        any_badge = False
        for key, badge in self.badge_labels.items():
            visible = flags.get(key, False)
            any_badge = any_badge or visible
            badge.setVisible(visible)
            if key == "ambiguous":
                badge.setStyleSheet(f"color:{UI_WARNING};font-size:10px;font-weight:900;background:#221F12;border:1px solid {UI_WARNING};border-radius:8px;padding:2px 6px;")
            elif key == "inserted":
                badge.setStyleSheet(f"color:{UI_TEXT};font-size:10px;font-weight:900;background:#17311F;border:1px solid {UI_SUCCESS};border-radius:8px;padding:2px 6px;")
            elif key == "demix":
                badge.setStyleSheet(f"color:{UI_TEXT};font-size:10px;font-weight:900;background:#122C46;border:1px solid #2D9CDB;border-radius:8px;padding:2px 6px;")
            elif key == "auto_update":
                badge.setStyleSheet(f"color:{UI_TEXT};font-size:10px;font-weight:900;background:#1F2030;border:1px solid {UI_MUTED};border-radius:8px;padding:2px 6px;")
        self.badge_container.setVisible(any_badge)

        self.view_toggle.blockSignals(True)
        self.view_toggle.setChecked(bool(data.get("viewed", True)))
        self.view_toggle.setText("\u25c9" if self.view_toggle.isChecked() else "\u25cb")
        self.view_toggle.blockSignals(False)
        self.id_edit.blockSignals(False)
        self.class_combo.blockSignals(False)

        waveform = data.get("waveform")
        if waveform is not None:
            x = np.linspace(0, len(waveform) / 500.0, len(waveform)) if len(waveform) else []
            self.thumb.set_data(x, waveform)
        else:
            self.thumb.set_data([], [])


class HolterBeatTemplatePanel(QWidget):
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{COL_BG};")
        self._template_rows = []
        self._current_filter = "all"
        self._selected_template_key = ""
        self._selected_template_keys = []
        self._card_widgets = []
        self._waveform_cache = {}
        self._replay_engine = None
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Template System")
        title.setStyleSheet(f"color:#07111F;font-size:13px;font-weight:bold;background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #28E37B, stop:1 #89F7C5);padding:7px 12px;border-radius:8px;")
        layout.addWidget(title)

        stats = QGridLayout()
        stats.setHorizontalSpacing(8)
        stats.setVerticalSpacing(8)
        self._stat_cards = {
            "total": _TemplateMetricCard("Total beats", "0", COL_TEXT),
            "templates": _TemplateMetricCard("Templates", "0", COL_TEXT),
            "unconfirmed": _TemplateMetricCard("Unconfirmed", "0", UI_WARNING),
            "beat_distribution": _TemplateMetricCard("Beat distribution", "N: 0", UI_TEXT),
        }
        stats.addWidget(self._stat_cards["total"], 0, 0)
        stats.addWidget(self._stat_cards["templates"], 0, 1)
        stats.addWidget(self._stat_cards["unconfirmed"], 0, 2)
        stats.addWidget(self._stat_cards["beat_distribution"], 0, 3)
        layout.addLayout(stats)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_lbl = QLabel("Filter")
        filter_lbl.setStyleSheet(f"color:{UI_MUTED};font-size:11px;font-weight:700;border:none;")
        filter_row.addWidget(filter_lbl)
        self._filter_buttons = {}
        for key, text in [
            ("all", "All"),
            ("N", "N"),
            ("S", "S"),
            ("V", "V"),
            ("P", "P"),
            ("AF", "AF"),
            ("X", "X"),
            ("Other", "Other"),
            ("unconfirmed", "Unconfirmed"),
        ]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.setToolTip({
                "all": "Show all templates",
                "N": "Show normal templates",
                "S": "Show supraventricular templates",
                "V": "Show ventricular templates",
                "P": "Show paced templates",
                "AF": "Show atrial fibrillation/flutter templates",
                "X": "Show artifact templates",
                "Other": "Show uncategorized templates",
                "unconfirmed": "Show templates not yet confirmed",
            }.get(key, text))
            btn.setStyleSheet(_style_btn() if key != "all" else _style_active_btn())
            btn.clicked.connect(lambda checked=False, k=key: self._set_filter(k))
            self._filter_buttons[key] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(f"QScrollArea{{background:{COL_BG};border:none;}}")
        self._cards_host = QWidget()
        self._cards_host.setStyleSheet(f"background:{COL_BG};")
        self._cards_layout = QGridLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        self._scroll.setWidget(self._cards_host)
        layout.addWidget(self._scroll, 1)

    def update_from_metrics(self, metrics_list: list, summary: dict):
        class_totals = dict(summary.get('beat_class_totals', {}) or {})
        if not class_totals:
            for metric in metrics_list or []:
                for cls, count in (metric.get('beat_class_counts', {}) or {}).items():
                    class_totals[cls] = class_totals.get(cls, 0) + int(count or 0)
        total_beats = int(summary.get("total_beats", 0) or sum(class_totals.values()) or 0)
        template_map = {}
        for metric in metrics_list or []:
            for row in (metric.get('template_summary', []) or []):
                tkey = str(row.get('template_key') or row.get('template_id') or row.get('label') or 'T')
                item = template_map.setdefault(tkey, {
                    'template_key': tkey,
                    'template_id': row.get('template_id', 'T'),
                    'label': row.get('label', 'N'),
                    'count': 0,
                    'rr': [],
                    'qrs': [],
                    'first_timestamp': float(row.get('first_timestamp', metric.get('t', 0.0)) or 0.0),
                    'viewed': bool(row.get('viewed', True)),
                    'ambiguous': bool(row.get('ambiguous', False)),
                    'inserted': bool(row.get('inserted', False)),
                    'demix': bool(row.get('demix', False)),
                    'auto_update': bool(row.get('auto_update', False)),
                })
                item['count'] += int(row.get('count', 0) or 0)
                item['rr'].append(float(row.get('avg_rr_ms', 0.0) or 0.0))
                item['qrs'].append(float(row.get('avg_qrs_ms', 0.0) or 0.0))
                item['first_timestamp'] = min(item['first_timestamp'], float(row.get('first_timestamp', item['first_timestamp']) or item['first_timestamp']))
        self._template_rows = sorted(template_map.values(), key=lambda x: x['count'], reverse=True)

        unconfirmed = sum(1 for row in self._template_rows if not row.get("viewed", True))
        self._stat_cards["total"].value.setText(f"{total_beats:,}")
        self._stat_cards["templates"].value.setText(str(len(self._template_rows)))
        self._stat_cards["unconfirmed"].value.setText(str(unconfirmed))
        dist_parts = []
        for key in ("N", "V", "S", "F", "Q"):
            if int(class_totals.get(key, 0) or 0) > 0:
                dist_parts.append(f"{key}: {int(class_totals.get(key, 0)):,}")
        self._stat_cards["beat_distribution"].value.setText("  ".join(dist_parts) if dist_parts else "No beat classes")
        self._refresh_stats()
        self._render_cards()

    def set_replay_engine(self, engine):
        self._replay_engine = engine
        self._waveform_cache.clear()
        self._render_cards()

    def _row_key(self, row: dict) -> str:
        return str(row.get("template_key") or row.get("template_id") or row.get("label") or "")

    def _filtered_rows(self):
        filtered = []
        for row in self._template_rows:
            label = str(row.get("label", "N") or "N").strip() or "N"
            code = _template_filter_key(label)
            if self._current_filter == "all":
                filtered.append(row)
            elif self._current_filter == "unconfirmed" and not row.get("viewed", True):
                filtered.append(row)
            elif self._current_filter == "AF" and code in {"AF", "F", "Q"}:
                filtered.append(row)
            elif self._current_filter == "Other" and code == "Other":
                filtered.append(row)
            elif self._current_filter in {"N", "V", "S", "P", "X"} and code == self._current_filter:
                filtered.append(row)
        return filtered

    def _refresh_stats(self):
        total_beats = sum(int(row.get("count", 0) or 0) for row in self._template_rows)
        unconfirmed = sum(1 for row in self._template_rows if not row.get("viewed", True))
        label_totals = {}
        for row in self._template_rows:
            label = str(row.get("label", "N") or "N").strip() or "N"
            label_totals[label] = label_totals.get(label, 0) + int(row.get("count", 0) or 0)
        self._stat_cards["total"].value.setText(f"{int(total_beats):,}")
        self._stat_cards["templates"].value.setText(str(len(self._template_rows)))
        self._stat_cards["unconfirmed"].value.setText(str(unconfirmed))
        preferred = ["N", "S", "V", "P", "AF", "X", "Other", "F", "Q", "R", "O"]
        dist_parts = []
        for key in preferred:
            value = int(label_totals.pop(key, 0) or 0)
            if value > 0:
                dist_parts.append(f"{key}: {value:,}")
        for key in sorted(label_totals):
            value = int(label_totals.get(key, 0) or 0)
            if value > 0:
                dist_parts.append(f"{key}: {value:,}")
        self._stat_cards["beat_distribution"].value.setText("  ".join(dist_parts) if dist_parts else "No beat classes")

    def _set_selected_keys(self, keys):
        ordered = []
        for key in keys or []:
            value = str(key or "").strip()
            if value and value not in ordered:
                ordered.append(value)
        self._selected_template_keys = ordered
        self._selected_template_key = ordered[0] if ordered else ""
        self._sync_card_selection()

    def _sync_card_selection(self):
        selected = set(self._selected_template_keys)
        visible = []
        for card in self._card_widgets:
            try:
                is_selected = card._template_key in selected
                card.set_selected(is_selected)
                if is_selected:
                    visible.append(card._template_key)
            except Exception:
                pass
        if visible:
            self._selected_template_key = visible[0]
        elif self._selected_template_keys:
            self._selected_template_key = self._selected_template_keys[0]
        else:
            self._selected_template_key = ""

    def _row_for_key(self, template_key: str):
        template_key = str(template_key or "")
        for row in self._template_rows:
            if self._row_key(row) == template_key:
                return row
        return None

    def _selected_rows(self):
        selected = set(self._selected_template_keys)
        return [row for row in self._template_rows if self._row_key(row) in selected]

    def _selected_keys_for_card(self, card):
        card_key = str(getattr(card, "_template_key", "") or "")
        if self._selected_template_keys and card_key in set(self._selected_template_keys):
            return list(self._selected_template_keys)
        return [card_key] if card_key else []

    def _rename_template_key(self, old_key: str, new_key: str):
        old_key = str(old_key or "")
        new_key = str(new_key or "")
        if not old_key or not new_key or old_key == new_key:
            return
        for row in self._template_rows:
            if self._row_key(row) == old_key:
                row["template_key"] = new_key
        if old_key in self._waveform_cache:
            self._waveform_cache[new_key] = self._waveform_cache.pop(old_key)
        self._selected_template_keys = [new_key if key == old_key else key for key in self._selected_template_keys]
        if self._selected_template_key == old_key:
            self._selected_template_key = new_key

    def _apply_template_label(self, keys, label: str):
        key_set = set(keys or [])
        changed = False
        for row in self._template_rows:
            if self._row_key(row) in key_set:
                row["label"] = str(label or "N").strip() or "N"
                changed = True
        if changed:
            self._refresh_stats()
            self._render_cards()

    def _apply_template_viewed(self, keys, viewed: bool):
        key_set = set(keys or [])
        changed = False
        for row in self._template_rows:
            if self._row_key(row) in key_set:
                row["viewed"] = bool(viewed)
                changed = True
        if changed:
            self._refresh_stats()
            self._render_cards()

    def _select_all_visible(self):
        self._set_selected_keys([self._row_key(row) for row in self._filtered_rows()])

    def _reverse_visible_selection(self):
        visible = [self._row_key(row) for row in self._filtered_rows()]
        selected = set(self._selected_template_keys)
        new_keys = [key for key in self._selected_template_keys if key not in visible]
        new_keys.extend(key for key in visible if key not in selected)
        self._set_selected_keys(new_keys)
    def _set_filter(self, key: str):
        self._current_filter = key
        for k, btn in self._filter_buttons.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(_style_active_btn() if k == key else _style_btn())
        self._refresh_stats()
        self._render_cards()

    def _on_card_template_id_changed(self, card, text: str):
        old_key = str(getattr(card, "_template_key", "") or "")
        new_id = str(text or "").strip() or old_key
        row = self._row_for_key(old_key)
        if row is None:
            return
        row["template_id"] = new_id
        row["template_key"] = new_id
        if old_key != new_id:
            self._rename_template_key(old_key, new_id)
        self._refresh_stats()
        self._render_cards()

    def _on_card_class_changed(self, card, text: str):
        key = str(getattr(card, "_template_key", "") or "")
        row = self._row_for_key(key)
        if row is None:
            return
        row["label"] = str(text or "N").strip() or "N"
        self._refresh_stats()
        self._render_cards()

    def _on_card_viewed_changed(self, card, viewed: bool):
        key = str(getattr(card, "_template_key", "") or "")
        row = self._row_for_key(key)
        if row is None:
            return
        row["viewed"] = bool(viewed)
        self._refresh_stats()
        self._render_cards()

    def _delete_selected_templates(self, keys=None):
        keys = list(keys or self._selected_template_keys)
        if not keys:
            return
        if QMessageBox.question(self, "Delete templates", f"Delete {len(keys)} selected template(s)?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        key_set = set(keys)
        self._template_rows = [row for row in self._template_rows if self._row_key(row) not in key_set]
        for key in key_set:
            self._waveform_cache.pop(key, None)
        self._selected_template_keys = []
        self._selected_template_key = ""
        self._refresh_stats()
        self._render_cards()

    def _confirm_delete_templates(self, count: int) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Delete templates")
        box.setText(f"Delete {count} selected template(s)?")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        box.setStyleSheet(f"""
            QMessageBox {{ background: {COL_BLACK}; }}
            QMessageBox QLabel {{ color: {COL_WHITE}; font-size: 12px; }}
            QMessageBox QPushButton {{
                background: #1B2740;
                color: {COL_WHITE};
                border: 1px solid {UI_BORDER};
                border-radius: 6px;
                padding: 6px 14px;
                min-width: 64px;
            }}
            QMessageBox QPushButton:hover {{
                background: #243552;
                border-color: {UI_ACCENT};
            }}
            QMessageBox QPushButton:pressed {{
                background: #132033;
            }}
        """)
        return box.exec_() == QMessageBox.Yes
    def _merge_selected_templates(self, keys=None):
        keys = list(keys or self._selected_template_keys)
        key_set = set(keys)
        rows = [row for row in self._template_rows if self._row_key(row) in key_set]
        if len(rows) < 2:
            return
        options = [
            ("Normal", "N"),
            ("Atrial Premature", "S"),
            ("Ventricular Premature", "V"),
            ("Artifact", "X"),
            ("Atrial Fibrillation", "Q"),
            ("Atrial Flutter", "R"),
            ("Blocked PAC", "O"),
            ("Paced", "P"),
            ("Other", "Other"),
        ]
        labels = []
        for row in rows:
            label = str(row.get("label", "N") or "N").strip() or "N"
            if label not in labels:
                labels.append(label)
        if len(labels) == 1:
            merged_label = labels[0]
        else:
            items = [f"{name} ({code})" if code != "Other" else name for name, code in options]
            choice, ok = QInputDialog.getItem(self, "Merge template", "Choose the merged template type:", items, 0, False)
            if not ok:
                return
            merged_label = choice[choice.rfind("(") + 1:-1] if "(" in choice and choice.endswith(")") else choice
        base = dict(rows[0])
        total_count = sum(int(row.get("count", 0) or 0) for row in rows)
        rr_values = []
        qrs_values = []
        for row in rows:
            rr_values.extend([float(v) for v in (row.get("rr", []) or []) if v is not None])
            qrs_values.extend([float(v) for v in (row.get("qrs", []) or []) if v is not None])
        base["label"] = merged_label
        base["count"] = total_count
        base["rr"] = rr_values
        base["qrs"] = qrs_values
        base["first_timestamp"] = min(float(row.get("first_timestamp", 0.0) or 0.0) for row in rows)
        base["viewed"] = all(bool(row.get("viewed", True)) for row in rows)
        base["ambiguous"] = any(bool(row.get("ambiguous", False)) for row in rows)
        base["inserted"] = any(bool(row.get("inserted", False)) for row in rows)
        base["demix"] = any(bool(row.get("demix", False)) for row in rows)
        base["auto_update"] = any(bool(row.get("auto_update", False)) for row in rows)
        base.setdefault("template_id", base.get("template_id") or f"T{len(self._template_rows) + 1}")
        base["template_key"] = base.get("template_id") or base.get("label") or "T"
        new_rows = []
        inserted = False
        for row in self._template_rows:
            key = self._row_key(row)
            if key in key_set:
                self._waveform_cache.pop(key, None)
                if not inserted:
                    new_rows.append(base)
                    inserted = True
            else:
                new_rows.append(row)
        self._template_rows = new_rows
        self._selected_template_keys = [base["template_key"]]
        self._selected_template_key = base["template_key"]
        self._refresh_stats()
        self._render_cards()

    def _open_overlay_analysis(self, card):
        host = self.window()
        if host is None:
            return
        try:
            if hasattr(host, "_focus_tab"):
                host._focus_tab("REPLAY")
            template_key = str(getattr(card, "_template_key", "") or "")
            row = self._row_for_key(template_key)
            if row is not None and hasattr(host, "set_magnifier_focus"):
                host.set_magnifier_focus(card.thumb, card.thumb._magnifier_source_payload(), QPoint(max(8, card.thumb.width() // 2), max(8, card.thumb.height() // 2)))
                self.seek_requested.emit(float(row.get("first_timestamp", 0.0) or 0.0))
        except Exception:
            pass

    def _open_lorenz_plots(self, card):
        host = self.window()
        if host is None:
            return
        try:
            if hasattr(host, "_focus_tab"):
                host._focus_tab("REPLAY")
            row = self._row_for_key(str(getattr(card, "_template_key", "") or ""))
            if row is not None:
                self.seek_requested.emit(float(row.get("first_timestamp", 0.0) or 0.0))
        except Exception:
            pass

    def _show_template_card_menu(self, card, global_pos):
        card_key = str(getattr(card, "_template_key", "") or "")
        if not card_key:
            return
        if not self._selected_template_keys or card_key not in set(self._selected_template_keys):
            self._set_selected_keys([card_key])
        target_keys = list(self._selected_template_keys) or [card_key]
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background: #0B1220; color: {UI_TEXT}; border: 1px solid {UI_BORDER}; padding: 6px; }} QMenu::item {{ padding: 6px 20px 6px 18px; border-radius: 4px; }} QMenu::item:selected {{ background: {UI_ACCENT}; color: #07111F; }} QMenu::separator {{ height: 1px; background: {UI_BORDER}; margin: 6px 4px; }}")
        prop_menu = menu.addMenu("Template properties")
        for title, code in [("Normal (N)", "N"), ("Atrial Premature (S)", "S"), ("Ventricular Premature (V)", "V"), ("Artifact (X)", "X"), ("Atrial Fibrillation (Q)", "Q"), ("Atrial Flutter (R)", "R"), ("Blocked PAC (O)", "O"), ("Paced (P)", "P"), ("Other", "Other")]:
            action = prop_menu.addAction(title)
            action.triggered.connect(lambda checked=False, c=code: self._apply_template_label(target_keys, c))
        func_menu = menu.addMenu("Function")
        func_menu.addAction("Delete").triggered.connect(lambda: self._delete_selected_templates(target_keys))
        func_menu.addAction("Select All").triggered.connect(self._select_all_visible)
        func_menu.addAction("Reverse Selection").triggered.connect(self._reverse_visible_selection)
        merge_action = menu.addAction("Merge template")
        merge_action.setEnabled(len(target_keys) >= 2)
        merge_action.triggered.connect(lambda: self._merge_selected_templates(target_keys))
        ok_menu = menu.addMenu("Template OK/Cancel")
        ok_menu.addAction("Confirm").triggered.connect(lambda: self._apply_template_viewed(target_keys, True))
        ok_menu.addAction("Unconfirm").triggered.connect(lambda: self._apply_template_viewed(target_keys, False))
        menu.addAction("Overlay beat analysis").triggered.connect(lambda: self._open_overlay_analysis(card))
        menu.addAction("Lorenz plots").triggered.connect(lambda: self._open_lorenz_plots(card))
        menu.exec_(global_pos)
    def _on_card_clicked(self, card):
        template_key = str(getattr(card, "_template_key", "") or "")
        if template_key:
            self._set_selected_keys([template_key])
        row = self._row_for_key(template_key)
        if template_key:
            self.seek_requested.emit(float(row.get("first_timestamp", 0.0) or 0.0) if row is not None else 0.0)

    def _render_cards(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._card_widgets = []
        filtered = self._filtered_rows()
        columns = 3 if len(filtered) <= 6 else 4
        filtered_keys = [self._row_key(row) for row in filtered]
        selected_visible = [key for key in filtered_keys if key in set(self._selected_template_keys)]
        if filtered and not selected_visible:
            self._set_selected_keys([filtered_keys[0]])
        elif selected_visible:
            self._selected_template_key = selected_visible[0]
        elif not self._selected_template_keys:
            self._selected_template_key = ""

        for idx, row in enumerate(filtered):
            label = str(row.get("label", "N") or "N").strip() or "N"
            label_code = label[:1].upper() if label else "N"
            accent = {"N": "#2D9CDB", "V": "#F2994A", "S": "#E2B93B", "F": "#7F8C8D", "Q": "#B06CFD", "R": "#A97FFF", "O": "#F2C94C", "P": "#56CCF2", "X": "#EB5757"}.get(label_code, UI_BORDER)
            card = TemplateCardWidget(accent=accent)
            rr = row.get("rr", []) or []
            qrs = row.get("qrs", []) or []
            rr_med = float(np.median(rr)) if rr else 0.0
            qrs_med = float(np.median(qrs)) if qrs else 0.0
            waveform = self._resolve_template_waveform(row, rr_med, qrs_med)
            template_key = self._row_key(row)
            card.clicked.connect(self._on_card_clicked)
            card.template_id_changed.connect(self._on_card_template_id_changed)
            card.class_changed.connect(self._on_card_class_changed)
            card.viewed_changed.connect(self._on_card_viewed_changed)
            card.set_template_data({
                "template_key": template_key,
                "index": idx + 1,
                "template_id": row.get("template_id", f"T{idx+1}"),
                "label": row.get("label", "N"),
                "count": row.get("count", 0),
                "viewed": row.get("viewed", True),
                "ambiguous": row.get("ambiguous", False),
                "inserted": row.get("inserted", False),
                "demix": row.get("demix", False),
                "auto_update": row.get("auto_update", False),
                "waveform": waveform,
            })
            card.set_selected(template_key in set(self._selected_template_keys))
            row_idx, col_idx = divmod(len(self._card_widgets), columns)
            self._cards_layout.addWidget(card, row_idx, col_idx)
            self._card_widgets.append(card)
        if self._card_widgets:
            self._cards_layout.setRowStretch(max(0, (len(self._card_widgets) + columns - 1) // columns), 1)
        for c in range(columns, 6):
            self._cards_layout.setColumnStretch(c, 1)
        self._sync_card_selection()

    def _resolve_template_waveform(self, row: dict, rr_ms: float, qrs_ms: float):
        key = str(row.get("template_key") or row.get("template_id") or row.get("label") or "T")
        cached = self._waveform_cache.get(key)
        if cached is not None:
            return cached
        first_ts = float(row.get("first_timestamp", 0.0) or 0.0)
        waveform = None
        engine = getattr(self, "_replay_engine", None)
        try:
            if engine is not None and hasattr(engine, "_reader"):
                fs = float(getattr(engine, "fs", 500.0) or 500.0)
                pre = 0.18
                post = 0.34
                data = engine._reader.read_range(max(0.0, first_ts - pre), min(float(engine.duration_sec), first_ts + post))
                if isinstance(data, np.ndarray) and data.ndim == 2 and data.shape[0] > 1 and data.shape[1] > 8:
                    lead = np.asarray(data[1], dtype=float)
                    baseline = float(np.median(lead))
                    centered = lead - baseline
                    if np.ptp(centered) > 1.0:
                        x_old = np.linspace(0.0, 1.0, centered.size)
                        x_new = np.linspace(0.0, 1.0, 240)
                        centered = np.interp(x_new, x_old, centered)
                        centered = centered - float(np.median(centered))
                        peak = max(float(np.max(np.abs(centered))), 1.0)
                        centered = np.clip(centered / peak * 420.0, -650.0, 650.0)
                        waveform = 2048.0 + centered
        except Exception:
            waveform = None
        if waveform is None:
            waveform = self._make_thumbnail_waveform(rr_ms, qrs_ms)
        self._waveform_cache[key] = waveform
        return waveform

    def _make_thumbnail_waveform(self, rr_ms: float, qrs_ms: float):
        t = np.linspace(0, 1.2, 240)
        rr_scale = np.clip(rr_ms / 900.0, 0.55, 1.8) if rr_ms > 0 else 1.0
        qrs_scale = np.clip(qrs_ms / 80.0, 0.6, 1.8) if qrs_ms > 0 else 1.0
        p = 0.04 * np.exp(-((t - 0.14) / 0.028) ** 2)
        q = -0.14 * np.exp(-((t - 0.275) / 0.010) ** 2)
        r = 1.35 * np.exp(-((t - 0.31) / (0.014 / qrs_scale)) ** 2)
        s = -0.36 * np.exp(-((t - 0.335) / 0.014) ** 2)
        tw = 0.22 * np.exp(-((t - 0.63) / (0.09 * rr_scale)) ** 2)
        st = 0.025 * np.exp(-((t - 0.45) / 0.05) ** 2)
        wave = p + q + r + s + tw + st
        return 2048.0 + wave * 480.0

    def _on_template_clicked(self, row, _col):
        if 0 <= row < len(self._template_rows):
            self.seek_requested.emit(float(self._template_rows[row].get("first_timestamp", 0.0)))


# ?????????????????????????????????????????????????????????????????????????????
# 9. HOLTER INSIGHT PANEL  (report preview)
# ?????????????????????????????????????????????????????????????????????????????
# 9. HOLTER INSIGHT PANEL  (report preview)
# -----------------------------------------------------------------------------

class HolterInsightPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:10px;}}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        title = QLabel("Comprehensive Report Preview")
        title.setStyleSheet(f"color:{COL_GREEN};font-size:14px;font-weight:bold;background:{COL_DARK};"
                            f"padding:7px;border-radius:4px;border:none;")
        layout.addWidget(title)
        self._report = QTextEdit()
        self._report.setReadOnly(True)
        self._report.setStyleSheet(f"""
            QTextEdit{{background:{COL_BLACK};color:{COL_GREEN};
              border:1px solid {COL_GREEN_DRK};border-radius:8px;padding:10px;font-size:13px;}}
        """)
        layout.addWidget(self._report)

    def update_text(self, patient_info: dict, summary: dict):
        name = patient_info.get("patient_name") or patient_info.get("name") or "Unknown patient"
        age = patient_info.get("age", "-")
        sex = patient_info.get("gender") or patient_info.get("sex") or "-"
        email = patient_info.get("email", "-")
        dur = summary.get("duration_sec", 0) / 3600
        avg_hr = summary.get("avg_hr", 0)
        min_hr = summary.get("min_hr", 0)
        max_hr = summary.get("max_hr", 0)
        quality = summary.get("avg_quality", 0) * 100
        arrhythmias = summary.get("arrhythmia_counts", {})
        top = ", ".join(f"{k} ({v})" for k, v in sorted(arrhythmias.items(), key=lambda x: -x[1])[:4]) \
              or "No clinically significant arrhythmia burden detected."
        rhythm = ("predominantly tachycardic trend" if avg_hr >= 100
                  else "predominantly bradycardic trend" if 0 < avg_hr <= 60
                  else "predominantly sinus-range rhythm")
        text = (
            f"Patient: {name} | Age/Sex: {age}/{sex} | Email: {email}\n\n"
            f"Study summary:\n"
            f"- Recording duration: {dur:.1f} hours\n"
            f"- Average heart rate: {avg_hr:.0f} bpm (range {min_hr:.0f}-{max_hr:.0f} bpm)\n"
            f"- Signal quality: {quality:.1f}%\n"
            f"- Longest RR interval: {summary.get('longest_rr_ms',0):.0f} ms\n"
            f"- HRV profile: SDNN {summary.get('sdnn',0):.1f} ms, "
            f"rMSSD {summary.get('rmssd',0):.1f} ms, pNN50 {summary.get('pnn50',0):.2f}%\n\n"
            f"Interpretation:\n"
            f"The recording demonstrates a {rhythm}. Key events: {top}\n\n"
            f"Suggested final report wording:\n"
            f'"Comprehensive ECG Analysis monitoring for {name} shows {rhythm} with an average heart rate of '
            f'{avg_hr:.0f} bpm. The minimum recorded rate was {min_hr:.0f} bpm and the '
            f'maximum recorded rate was {max_hr:.0f} bpm. Overall signal quality was '
            f'{quality:.1f}%, enabling comprehensive review of the 12-lead trends and event strips."'
        )
        self._report.setPlainText(text)


# -----------------------------------------------------------------------------
# 10. RECORD MANAGEMENT PANEL
# -----------------------------------------------------------------------------

class HolterRecordManagementPanel(QWidget):
    session_selected = pyqtSignal(str)  # session dir path

    def __init__(self, output_dir: str = "recordings"):
        super().__init__()
        self.output_dir = output_dir
        self._selected_session = ""
        self._build_ui()
        self.refresh_records()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search patient / reporter / status")
        self._search.setStyleSheet(f"QLineEdit{{background:{COL_DARK};color:{COL_GREEN};border:1px solid {COL_GREEN_DRK};"
                                   f"border-radius:4px;padding:6px;font-size:12px;}}")
        self._search.textChanged.connect(self.refresh_records)
        self._filter = QComboBox()
        self._filter.addItems(["All", "Today", "Yesterday", "This Week", "This Month", "This Year"])
        self._filter.setStyleSheet(f"""
            QComboBox {{
                background:{COL_DARK}; color:{COL_GREEN}; border:1px solid {COL_GREEN_DRK};
                border-radius:4px; padding:6px; font-size:12px;
            }}
            QComboBox QAbstractItemView {{
                background:{COL_DARK}; color:white; selection-background-color:{COL_GREEN_DRK};
            }}
        """)
        self._filter.currentTextChanged.connect(self.refresh_records)
        actions.addWidget(QLabel("Search:", styleSheet=f"color:{COL_GREEN};font-size:12px;"))
        actions.addWidget(self._search, 2)
        actions.addWidget(QLabel("Filter:", styleSheet=f"color:{COL_GREEN};font-size:12px;"))
        actions.addWidget(self._filter)
        self._action_buttons = {}
        for txt in ["Browse", "Import", "Export", "Backup", "Delete"]:
            btn = QPushButton(txt)
            btn.setStyleSheet(_style_btn())
            self._action_buttons[txt] = btn
            actions.addWidget(btn)
        layout.addLayout(actions)

        cols = ["Name","Age","Gender","Record Time","Duration","Channel","Import Time","Status","Reporter","Conclusion"]
        self._table = QTableWidget(0, len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setStyleSheet(_table_style())
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._table.verticalScrollBar().setSingleStep(1)
        self._table.itemSelectionChanged.connect(self._sync_selected_session)
        self._table.cellClicked.connect(self._open_row)
        self._table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table, 1)
        self._action_buttons["Browse"].clicked.connect(self._browse_root)
        self._action_buttons["Import"].clicked.connect(self._import_session)
        self._action_buttons["Export"].clicked.connect(self._export_session)
        self._action_buttons["Backup"].clicked.connect(self._backup_root)
        self._action_buttons["Delete"].clicked.connect(self._delete_session)

    def refresh_records(self):
        self._table.setRowCount(0)
        self._selected_session = ""
        if not os.path.isdir(self.output_dir): return
        query = self._search.text().strip().lower()
        filter_label = self._filter.currentText()
        now = datetime.now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        rows = []
        for name in sorted(os.listdir(self.output_dir), reverse=True):
            session_dir = os.path.join(self.output_dir, name)
            if not os.path.isdir(session_dir): continue
            if not os.path.exists(os.path.join(session_dir, "recording.ecgh")): continue
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(os.path.join(session_dir, "recording.ecgh")))
            except Exception:
                mtime = datetime.fromtimestamp(os.path.getmtime(session_dir))
            delta_days = (now - mtime).days
            if filter_label == "Today" and mtime.date() != today:
                continue
            if filter_label == "Yesterday" and mtime.date() != yesterday:
                continue
            if filter_label == "This Week" and delta_days > 6:
                continue
            if filter_label == "This Month" and (mtime.year != now.year or mtime.month != now.month):
                continue
            if filter_label == "This Year" and mtime.year != now.year:
                continue
            parts = name.split("_", 3)
            rec_time = "_".join(parts[:2]).replace("_", " ") if len(parts) >= 2 else name[:19]
            p_name = parts[-1].replace("_", " ") if len(parts) >= 3 else "Unknown"
            age = "-"
            gender = "-"
            dur_str = "-"
            
            import json
            # Check patient.json first (created by Save dialog)
            patient_json = os.path.join(session_dir, "patient.json")
            if os.path.exists(patient_json):
                try:
                    with open(patient_json, 'r') as f:
                        pdata = json.load(f)
                    saved_name = pdata.get('name') or pdata.get('patient_name') or pdata.get('full_name')
                    if saved_name and str(saved_name).strip() and str(saved_name).strip().lower() != "unknown":
                        p_name = str(saved_name).strip()
                    saved_age = pdata.get('age')
                    if saved_age: age = str(saved_age)
                    saved_gender = pdata.get('gender') or pdata.get('sex')
                    if saved_gender: gender = str(saved_gender)
                except Exception:
                    pass

            try:
                session_json = os.path.join(session_dir, "session.json")
                if os.path.exists(session_json):
                    with open(session_json, 'r') as f:
                        sdata = json.load(f)
                        
                    # If we didn't find good name in patient.json, check session.json
                    if p_name.lower() == "unknown":
                        p_info = sdata.get('patient_info') or sdata.get('summary', {}).get('patient_info') or {}
                        saved_name = p_info.get('name') or p_info.get('patient_name') or p_info.get('full_name')
                        if saved_name and str(saved_name).strip() and str(saved_name).strip().lower() != "unknown":
                            p_name = str(saved_name).strip()
                        saved_age = p_info.get('age')
                        if saved_age and age == "-": age = str(saved_age)
                        saved_gender = p_info.get('gender') or p_info.get('sex')
                        if saved_gender and gender == "-": gender = str(saved_gender)

                    dur_sec = sdata.get('summary', {}).get('duration_sec', 0)
                    if dur_sec > 0:
                        h = int(dur_sec // 3600)
                        m = int((dur_sec % 3600) // 60)
                        s = int(dur_sec % 60)
                        if h > 0:
                            dur_str = f"{h}h {m:02d}m"
                        elif m > 0:
                            dur_str = f"{m}m {s:02d}s"
                        else:
                            dur_str = f"{s}s"
            except Exception:
                pass

            row_values = [p_name, age, gender, rec_time, dur_str, "3", rec_time, "Completed", "System", "-"]
            if query and not any(query in str(v).lower() for v in row_values): continue
            rows.append((row_values, session_dir))

        for row_values, session_dir in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            for c, v in enumerate(row_values):
                item = QTableWidgetItem(str(v))
                item.setForeground(QColor(COL_GREEN if c == 0 else COL_WHITE))
                item.setData(Qt.UserRole, session_dir)
                self._table.setItem(r, c, item)
        if self._table.rowCount() > 0:
            self._table.selectRow(0)
            self._sync_selected_session()

    def _open_row(self, row, _column=0):
        item = self._table.item(row, 0)
        if item:
            path = item.data(Qt.UserRole)
            if path:
                self._selected_session = path
                self.session_selected.emit(path)

    def _on_double_click(self, index):
        self._open_row(index.row())

    def _sync_selected_session(self):
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if rows:
            item = self._table.item(rows[0].row(), 0)
            if item:
                self._selected_session = item.data(Qt.UserRole) or ""

    def _selected_path(self) -> str:
        self._sync_selected_session()
        return self._selected_session

    def _browse_root(self):
        d = QFileDialog.getExistingDirectory(self, "Select Recordings Root", self.output_dir or os.getcwd())
        if d:
            self.output_dir = d
            self.refresh_records()

    def _import_session(self):
        src = QFileDialog.getExistingDirectory(self, "Import Session Folder")
        if not src:
            return
        if not os.path.exists(os.path.join(src, "recording.ecgh")):
            QMessageBox.warning(self, "Import Session", "Select a session folder that contains recording.ecgh.")
            return
        os.makedirs(self.output_dir, exist_ok=True)
        dest = os.path.join(self.output_dir, os.path.basename(os.path.normpath(src)))
        if os.path.exists(dest):
            QMessageBox.warning(self, "Import Session", "That session already exists in the recordings folder.")
            return
        shutil.copytree(src, dest)
        self.refresh_records()
        self.session_selected.emit(dest)

    def _export_session(self):
        src = self._selected_path()
        if not src:
            QMessageBox.information(self, "Export Session", "Select a recording to export first.")
            return
        dest_root = QFileDialog.getExistingDirectory(self, "Export Session To")
        if not dest_root:
            return
        dest = os.path.join(dest_root, os.path.basename(os.path.normpath(src)))
        if os.path.exists(dest):
            QMessageBox.warning(self, "Export Session", "That session already exists in the destination.")
            return
        shutil.copytree(src, dest)
        QMessageBox.information(self, "Export Session", f"Session exported to:\n{dest}")

    def _backup_root(self):
        if not os.path.isdir(self.output_dir):
            QMessageBox.information(self, "Backup", "No recordings folder found.")
            return
        dest_root = QFileDialog.getExistingDirectory(self, "Backup Recordings To")
        if not dest_root:
            return
        dest = os.path.join(dest_root, os.path.basename(os.path.normpath(self.output_dir)) or "recordings_backup")
        if os.path.exists(dest):
            QMessageBox.warning(self, "Backup", "That backup folder already exists.")
            return
        shutil.copytree(self.output_dir, dest)
        QMessageBox.information(self, "Backup", f"Recordings backed up to:\n{dest}")

    def _delete_session(self):
        src = self._selected_path()
        if not src:
            QMessageBox.information(self, "Delete Session", "Select a recording to delete first.")
            return
        if QMessageBox.question(self, "Delete Session",
                                f"Delete this recording?\n\n{src}",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        shutil.rmtree(src, ignore_errors=True)
        self.refresh_records()


# -----------------------------------------------------------------------------
# 11. HISTOGRAM PANEL
# -----------------------------------------------------------------------------

class HolterHistogramPanel(QWidget):
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{COL_BG};")
        self._metrics = []
        self._rank_mode = "rri"
        self._selected_point = None
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title_row = QHBoxLayout()
        title = QLabel("Histogram - RR Interval Distribution")
        title.setStyleSheet(f"color:{COL_GREEN};font-size:14px;font-weight:bold;border:none;")
        title_row.addWidget(title, 1)
        self._type_combo = QComboBox()
        self._type_combo.addItems(["RR Interval", "Heart Rate", "RRI Ratio"])
        self._type_combo.setStyleSheet(f"""
            QComboBox {{
                background:{COL_DARK}; color:{COL_GREEN};
                border:1px solid {COL_GREEN_DRK}; padding:4px; border-radius:4px;
            }}
            QComboBox QAbstractItemView {{
                background:{COL_DARK}; color:white; selection-background-color:{COL_GREEN_DRK};
            }}
        """)
        self._type_combo.currentTextChanged.connect(lambda _: self._draw())
        title_row.addWidget(self._type_combo)
        layout.addLayout(title_row)

        btn_row = QHBoxLayout()
        self._rank_buttons = {}
        for lbl, mode in [("RRI Ranking", "rri"), ("Time Ranking", "time"),
                          ("Prematurity Ranking", "prematurity"), ("Similarity Ranking", "similarity")]:
            btn = QPushButton(lbl)
            btn.setCheckable(True)
            btn.setStyleSheet(_style_btn())
            btn.clicked.connect(lambda _, m=mode: self._set_rank_mode(m))
            self._rank_buttons[mode] = btn
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._hist_canvas = HistogramCanvas()
        self._hist_canvas.bar_clicked.connect(self._on_bar_clicked)
        layout.addWidget(self._hist_canvas, 1)
        self._selected_info = QLabel("Selected: none")
        self._selected_info.setStyleSheet(
            f"color:{COL_WHITE};font-size:11px;font-weight:bold;border:none;padding:2px 0;"
        )
        layout.addWidget(self._selected_info)


        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:4px;}}")
        stats_layout = QGridLayout(stats_frame)
        stats_layout.setContentsMargins(10, 6, 10, 6)
        self._hist_stats = {}
        for i, (key, lbl) in enumerate([("nns","NNs"),("mean_nn","Mean NN"),
                                         ("sdnn","SDNN"),("sdann","SDANN"),
                                         ("rmssd","rMSSD"),("pnn50","pNN50"),
                                         ("triidx","TRIIDX"),("sdnnidx","SDNNIDX")]):
            col = i % 4
            row = i // 4
            l = QLabel(f"{lbl}:")
            l.setStyleSheet(f"color:{COL_GREEN};font-size:11px;font-weight:bold;border:none;")
            v = QLabel("?")
            v.setStyleSheet(f"color:{COL_WHITE};font-size:13px;font-weight:bold;border:none;")
            stats_layout.addWidget(l, row*2, col)
            stats_layout.addWidget(v, row*2+1, col)
            self._hist_stats[key] = v
        layout.addWidget(stats_frame)

        self._strip = ECGStripCanvas(height=60)
        layout.addWidget(self._strip)
        self._set_rank_mode("rri")

    def _set_rank_mode(self, mode: str):
        self._rank_mode = mode
        for key, btn in getattr(self, "_rank_buttons", {}).items():
            active = key == mode
            btn.setChecked(active)
            btn.setStyleSheet(_style_active_btn() if active else _style_btn())
        self._draw()

    def update_from_metrics(self, metrics_list: list):
        self._metrics = list(metrics_list or [])
        self._draw()

    def _build_points(self):
        points = []
        for metric_idx, m in enumerate(self._metrics):
            base_t = float(m.get('t', 0.0) or 0.0)
            label = str((m.get('arrhythmias') or [m.get('label', '')])[0] or '')
            rr_list = [float(v) for v in (m.get('rr_intervals_list') or []) if float(v) > 0]
            if rr_list:
                dur = float(m.get('duration', 0.0) or 0.0)
                step = (dur / max(1, len(rr_list))) if dur > 0 else 0.2
                for sample_idx, rr in enumerate(rr_list):
                    points.append({
                        't': base_t + sample_idx * step,
                        'rr': rr,
                        'metric_idx': metric_idx,
                        'sample_idx': sample_idx,
                        'label': label,
                    })
                continue
            rr_val = float(m.get('rr_ms', 0) or 0)
            if rr_val > 200:
                points.append({
                    't': base_t,
                    'rr': rr_val,
                    'metric_idx': metric_idx,
                    'sample_idx': 0,
                    'label': label,
                })
        return points

    def _draw(self):
        points = self._build_points()
        rr_vals = [p['rr'] for p in points if p['rr'] > 200]
        if not rr_vals:
            self._hist_canvas.set_histogram_data([], mode=self._rank_mode)
            for key in self._hist_stats:
                self._hist_stats[key].setText('?')
            return

        rr_arr = np.array(rr_vals, dtype=float)
        median_rr = float(np.median(rr_arr)) if rr_arr.size else 0.0
        mean_rr = float(np.mean(rr_arr)) if rr_arr.size else 0.0
        if self._rank_mode == 'time':
            ranked = sorted(points, key=lambda x: x['t'])
        elif self._rank_mode == 'prematurity':
            ranked = sorted(points, key=lambda x: max(0.0, mean_rr - x['rr']), reverse=True)
        elif self._rank_mode == 'similarity':
            ranked = sorted(points, key=lambda x: abs(x['rr'] - median_rr))
        else:
            ranked = sorted(points, key=lambda x: x['rr'], reverse=True)

        self._hist_canvas.set_histogram_data(ranked, mode=self._rank_mode)

        self._hist_stats['nns'].setText(str(len(rr_arr)))
        self._hist_stats['mean_nn'].setText(f"{rr_arr.mean():.0f} ms")
        self._hist_stats['sdnn'].setText(f"{rr_arr.std():.0f} ms")
        self._hist_stats['sdann'].setText('?')
        d = np.diff(rr_arr)
        rmssd = np.sqrt(np.mean(d ** 2)) if len(d) > 0 else 0.0
        self._hist_stats['rmssd'].setText(f"{rmssd:.0f} ms")
        pnn50 = 100.0 * np.sum(np.abs(d) > 50) / len(d) if len(d) > 0 else 0.0
        self._hist_stats['pnn50'].setText(f"{pnn50:.2f}%")
        self._hist_stats['triidx'].setText('?')
        self._hist_stats['sdnnidx'].setText('?')

    def _on_bar_clicked(self, payload: dict):
        if not payload:
            self._selected_point = None
            self._selected_info.setText("Selected: none")
            return
        count = int(payload.get('count', 0) or 0)
        lo, hi = payload.get('range', (0.0, 0.0))
        rr_center = float(payload.get('center_rr', 0.0) or 0.0)
        times = [float(t) for t in (payload.get('times', []) or []) if float(t) >= 0]
        if times:
            target = float(np.median(times))
        else:
            target = float(payload.get('center_t', 0.0) or 0.0)
        self._selected_point = payload
        self._selected_info.setText(
            f"Selected: {count} beats in {lo:.0f}-{hi:.0f} ms range | center {rr_center:.0f} ms"
        )
        if target > 0:
            self.seek_requested.emit(target)

    def set_replay_frame(self, data):
        if data is None or data.shape[0] < 1:
            return
        N = data.shape[1]
        x = np.linspace(0, N / 500.0, N) if N > 0 else []
        if N > 0:
            self._strip.set_data(x, data[0].copy())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._hist_canvas._selected_index = -1
            self._hist_canvas.update()
            self._on_bar_clicked(None)
        super().mousePressEvent(event)


class HistogramCanvas(QWidget):
    bar_clicked = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._mode = 'rri'
        self._selected_index = -1
        self._bar_rects = []
        self._bin_payloads = []
        self._bin_edges = []
        self._bins = []
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self.setStyleSheet(f"background:{COL_BLACK};border:none;")

    def set_data(self, rr_values):
        points = [{'t': float(i), 'rr': float(v)} for i, v in enumerate(rr_values or [])]
        self.set_histogram_data(points, mode='rri')

    def set_ranked_data(self, ranked_points, mode: str = 'rri'):
        self.set_histogram_data(ranked_points, mode=mode)

    def set_histogram_data(self, items, mode: str = 'rri'):
        self._mode = mode
        normalized = []
        for item in items or []:
            if isinstance(item, dict):
                normalized.append({
                    't': float(item.get('t', 0.0) or 0.0),
                    'rr': float(item.get('rr', 0.0) or 0.0),
                    'label': str(item.get('label', '')),
                })
            else:
                try:
                    t, rr = item
                    normalized.append({'t': float(t), 'rr': float(rr), 'label': ''})
                except Exception:
                    continue
        self._items = normalized
        self.update()

    def _palette(self):
        if self._mode == 'time':
            return QColor('#33D6FF'), QColor('#5AA7FF')
        if self._mode == 'prematurity':
            return QColor('#FF8A1E'), QColor('#FFB347')
        if self._mode == 'similarity':
            return QColor('#8A6CFF'), QColor('#B197FC')
        return QColor('#2F80ED'), QColor('#66A3FF')

    def _build_histogram(self):
        values = [float(item['rr']) for item in self._items if float(item.get('rr', 0.0) or 0.0) > 0]
        if not values:
            self._bins = []
            self._bin_edges = []
            self._bin_payloads = []
            return np.array([]), np.array([])
        arr = np.asarray(values, dtype=float)
        if arr.size < 2:
            self._bins = [(arr[0], arr[0] + 1.0, 1)]
            self._bin_edges = [arr[0], arr[0] + 1.0]
            self._bin_payloads = [list(self._items)]
            return np.array([1]), np.array(self._bin_edges)
        bins = int(min(36, max(12, round(math.sqrt(arr.size) * 2))))
        hist, edges = np.histogram(arr, bins=bins)
        bin_ids = np.clip(np.digitize(arr, edges, right=False) - 1, 0, bins - 1)
        payloads = [[] for _ in range(bins)]
        for item, bidx in zip(self._items, bin_ids):
            payloads[int(bidx)].append(item)
        self._bins = list(hist)
        self._bin_edges = list(edges)
        self._bin_payloads = payloads
        return hist, edges

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            clicked_bar = False
            for idx, rect in enumerate(self._bar_rects):
                if rect.contains(event.pos()) and idx < len(self._bin_payloads):
                    payload = self._payload_for_bin(idx)
                    self._selected_index = idx
                    self.bar_clicked.emit(payload)
                    clicked_bar = True
                    self.update()
                    break
            if not clicked_bar:
                self._selected_index = -1
                self.bar_clicked.emit(None)
                self.update()
        super().mousePressEvent(event)

    def _payload_for_bin(self, idx: int) -> dict:
        points = self._bin_payloads[idx] if idx < len(self._bin_payloads) else []
        if not points:
            left = self._bin_edges[idx] if idx < len(self._bin_edges) else 0.0
            right = self._bin_edges[idx + 1] if idx + 1 < len(self._bin_edges) else left
            return {'index': idx, 'range': (left, right), 'count': 0, 'times': [], 'center_rr': (left + right) / 2.0, 'center_t': 0.0}
        rr_vals = [float(p['rr']) for p in points]
        times = [float(p['t']) for p in points]
        left = self._bin_edges[idx] if idx < len(self._bin_edges) else min(rr_vals)
        right = self._bin_edges[idx + 1] if idx + 1 < len(self._bin_edges) else max(rr_vals)
        return {
            'index': idx,
            'range': (float(left), float(right)),
            'count': len(points),
            'times': times,
            'center_rr': float(np.median(rr_vals)),
            'center_t': float(np.median(times)),
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(COL_BLACK))
        w, h = self.width(), self.height()

        left, top, right, bottom = 46, 22, 18, 28
        plot_w = max(1, w - left - right)
        plot_h = max(1, h - top - bottom)

        hist, edges = self._build_histogram()
        if hist.size == 0:
            painter.setPen(QPen(QColor(COL_GREEN_DRK)))
            painter.drawText(self.rect(), Qt.AlignCenter, 'No RR data')
            return

        counts = hist.astype(int).tolist()
        max_count = max(counts) if counts else 1
        if max_count <= 0:
            max_count = 1

        values = [float(item['rr']) for item in self._items if float(item.get('rr', 0.0) or 0.0) > 0]
        min_rr = float(min(values))
        max_rr = float(max(values))

        painter.setPen(QPen(QColor('#22324B'), 1))
        for frac in (0.25, 0.5, 0.75):
            y = int(top + frac * plot_h)
            painter.drawLine(left, y, left + plot_w, y)
        for frac in (0.25, 0.5, 0.75):
            x = int(left + frac * plot_w)
            painter.drawLine(x, top, x, top + plot_h)

        x_label_left = 'low RR'
        x_label_right = 'high RR'
        if self._mode == 'time':
            x_label_left = 'early'
            x_label_right = 'late'
        elif self._mode == 'prematurity':
            x_label_left = 'less premature'
            x_label_right = 'more premature'
        elif self._mode == 'similarity':
            x_label_left = 'less similar'
            x_label_right = 'more similar'

        palette, highlight = self._palette()
        self._bar_rects = []
        bin_count = len(counts)
        gap = 2
        bar_w = max(2, int((plot_w - gap * (bin_count - 1)) / max(1, bin_count)))
        x0 = left
        for idx, count in enumerate(counts):
            bar_h = int((count / max_count) * max(10, plot_h - 8))
            x = int(x0 + idx * (bar_w + gap))
            y = int(top + plot_h - bar_h)
            rect = QRect(x, y, bar_w, bar_h)
            self._bar_rects.append(rect)
            selected = idx == self._selected_index
            color = highlight if selected else palette
            alpha = 255 if selected else 180
            painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), alpha)))
            painter.setPen(QPen(QColor(color.lighter(130)), 1))
            painter.drawRect(rect)
            if selected:
                painter.setPen(QPen(QColor('#F5D76E'), 2))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
            if count > 0 and (bin_count <= 20 or idx % max(1, bin_count // 10) == 0 or selected):
                painter.setPen(QPen(QColor(COL_WHITE)))
                painter.drawText(rect.adjusted(0, -18, 0, -2), Qt.AlignCenter, str(count))

        painter.setPen(QPen(QColor(COL_GREEN_DRK)))
        painter.drawText(left, 14, x_label_left)
        painter.drawText(w - 118, 14, x_label_right)
        painter.drawText(left, h - 5, f'{min_rr:.0f} ms')
        painter.drawText(w - 70, h - 5, f'{max_rr:.0f} ms')
        painter.setPen(QPen(QColor(UI_MUTED)))
        painter.drawText(left + 110, 14, f'RR Interval Range {min_rr:.0f}-{max_rr:.0f} ms')
# 12. AF ANALYSIS PANEL
# -----------------------------------------------------------------------------

class HolterAFPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{COL_BG};")
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Left: AF event list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        title = QLabel("AF Analysis")
        title.setStyleSheet(f"color:#07111F;font-size:13px;font-weight:bold;background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #28E37B, stop:1 #89F7C5);padding:6px 10px;border-radius:6px;")
        left_layout.addWidget(title)

        cols = ["Start time", "Duration", "Type"]
        self._af_table = QTableWidget(0, len(cols))
        self._af_table.setHorizontalHeaderLabels(cols)
        self._af_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._af_table.setStyleSheet(_table_style())
        self._af_table.verticalHeader().setVisible(False)
        self._af_table.setEditTriggers(QTableWidget.NoEditTriggers)
        left_layout.addWidget(self._af_table, 1)

        no_items = QLabel("There are no items to show.")
        no_items.setStyleSheet(f"color:{COL_GREEN_DRK};font-style:italic;padding:8px;border:none;")
        self._no_items_lbl = no_items
        left_layout.addWidget(no_items)

        nav_row = QHBoxLayout()
        for lbl in ["AF Analysis", "Parameters", "Prev Event", "Next Event", "Remove All", "Remove"]:

            btn = QPushButton(lbl)
            btn.setStyleSheet(_style_btn())
            nav_row.addWidget(btn)
        left_layout.addLayout(nav_row)
        layout.addWidget(left, 2)

        # Right: ECG strip + Lorenz
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(f"QScrollArea{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background:transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(4)
        
        self._thumb_strips = []
        lead_names = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
        for i in range(12):
            lbl = QLabel(f"Lead {lead_names[i]}")
            lbl.setStyleSheet(f"color:{COL_GREEN};font-size:11px;font-weight:bold;border:none;")
            scroll_layout.addWidget(lbl)
            
            strip = ECGStripCanvas(height=120)
            strip.lead_name = lead_names[i]
            scroll_layout.addWidget(strip)
            self._thumb_strips.append(strip)
            
        scroll_area.setWidget(scroll_content)
        right_layout.addWidget(scroll_area, 1)

        self._af_ecg_strip = ECGStripCanvas(height=70)
        right_layout.addWidget(self._af_ecg_strip)

        self._af_lorenz = LorenzCanvas()
        self._af_lorenz.setFixedHeight(160)
        right_layout.addWidget(self._af_lorenz)
        layout.addWidget(right, 3)

    def update_from_metrics(self, metrics_list: list, duration_sec: float = 0):
        af_events = [(m['t'], m.get('arrhythmias', [])) for m in metrics_list
                     if any('AF' in a or 'Fibrill' in a for a in m.get('arrhythmias', []))]
        self._af_table.setRowCount(len(af_events))
        if af_events:
            self._no_items_lbl.hide()
            for i, (t, arrhy) in enumerate(af_events):
                for j, val in enumerate([_sec_to_hms(t), "30s", "AF/Af"]):
                    item = QTableWidgetItem(val)
                    item.setForeground(QColor(COL_WHITE))
                    self._af_table.setItem(i, j, item)
        else:
            self._no_items_lbl.show()

    def set_replay_frame(self, data):
        if data is None or data.shape[0] < 1: return
        N = data.shape[1]
        fs = 500.0
        n_samples = min(N, int(10 * fs))
        x = np.linspace(0, n_samples/fs, n_samples) if n_samples > 0 else []
        if n_samples > 0:
            lead2_idx = 1 if data.shape[0] > 1 else 0
            self._af_ecg_strip.set_data(x, data[lead2_idx, :n_samples].copy())
            for i, ts in enumerate(self._thumb_strips):
                if i < data.shape[0]:
                    ts.set_data(x, data[i, :n_samples].copy())


# -----------------------------------------------------------------------------
# 13. ST TENDENCY PANEL
# -----------------------------------------------------------------------------

class HolterSTPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{COL_BG};")
        self._metrics = []
        self._current_tendency_mode = "ST"
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Left: ECG strip + controls
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(f"QScrollArea{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background:transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(4)
        
        self._ch_strips = []
        lead_names = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
        for i in range(12):
            lbl = QLabel(f"Lead {lead_names[i]}")
            lbl.setStyleSheet(f"color:{COL_GREEN};font-size:11px;font-weight:bold;border:none;")
            scroll_layout.addWidget(lbl)
            
            strip = ECGStripCanvas(height=80)
            strip.lead_name = lead_names[i]
            scroll_layout.addWidget(strip)
            self._ch_strips.append(strip)
            
        scroll_area.setWidget(scroll_content)
        left_layout.addWidget(scroll_area, 1)

        # Mini overview
        self._mini_strip = ECGStripCanvas(height=60, color="#00AA00")
        left_layout.addWidget(self._mini_strip)

        nav_row = QHBoxLayout()
        for lbl in ["ReScan", "Next Event", "Remove All", "Remove", "Reset"]:
            btn = QPushButton(lbl)
            btn.setStyleSheet(_style_btn())
            btn.setFixedHeight(30)
            nav_row.addWidget(btn)
        left_layout.addLayout(nav_row)
        layout.addWidget(left, 3)

        # Right: ST tendency charts + conclusion
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        mode_row = QHBoxLayout()
        self._st_btn = QPushButton("ST")
        self._st_btn.setStyleSheet(_style_active_btn())
        self._st_btn.setFixedWidth(50)
        self._t_btn = QPushButton("T")
        self._t_btn.setStyleSheet(_style_btn())
        self._t_btn.setFixedWidth(40)
        
        self._st_btn.clicked.connect(lambda: self._set_tendency_mode("ST"))
        self._t_btn.clicked.connect(lambda: self._set_tendency_mode("T"))

        mode_row.addWidget(self._st_btn)
        mode_row.addWidget(self._t_btn)
        mode_row.addStretch()
        right_layout.addLayout(mode_row)

        self._st_title = QLabel("ST tendency(mV)")
        self._st_title.setStyleSheet(f"color:{COL_GREEN};font-size:12px;font-weight:bold;border:none;")
        right_layout.addWidget(self._st_title)

        self._st_canvases = []
        st_scroll = QScrollArea()
        st_scroll.setWidgetResizable(True)
        st_scroll.setStyleSheet(f"QScrollArea{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}")
        st_scroll_content = QWidget()
        st_scroll_content.setStyleSheet("background:transparent;")
        st_scroll_layout = QVBoxLayout(st_scroll_content)
        st_scroll_layout.setContentsMargins(4, 4, 4, 4)
        st_scroll_layout.setSpacing(4)
        lead_names = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
        for name in lead_names:
            ch_lbl = QLabel(f"Lead {name}")
            ch_lbl.setStyleSheet(f"color:{COL_GREEN};font-size:10px;border:none;")
            st_scroll_layout.addWidget(ch_lbl)
            canvas = STCanvas(height=70)
            st_scroll_layout.addWidget(canvas)
            self._st_canvases.append(canvas)
        st_scroll.setWidget(st_scroll_content)
        right_layout.addWidget(st_scroll, 1)

        conclusion_frame = QFrame()
        conclusion_frame.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:4px;}}")
        cf_layout = QVBoxLayout(conclusion_frame)
        cf_layout.setContentsMargins(8, 6, 8, 6)
        cf_lbl = QLabel("Conclusion")
        cf_lbl.setStyleSheet(f"color:{COL_GREEN};font-size:11px;font-weight:bold;border:none;")
        cf_layout.addWidget(cf_lbl)
        self._conclusion_edit = QTextEdit()
        self._conclusion_edit.setFixedHeight(60)
        self._conclusion_edit.setStyleSheet(f"QTextEdit{{background:{COL_DARK};color:{COL_GREEN};"
                                             f"border:none;font-size:11px;padding:4px;}}")
        cf_layout.addWidget(self._conclusion_edit)
        save_row = QHBoxLayout()
        for lbl in ["Save as template", "Quote templates"]:
            btn = QPushButton(lbl)
            btn.setStyleSheet(_style_btn())
            save_row.addWidget(btn)
        cf_layout.addLayout(save_row)
        right_layout.addWidget(conclusion_frame)
        layout.addWidget(right, 2)

    def _set_tendency_mode(self, mode: str):
        self._current_tendency_mode = mode
        if mode == "ST":
            self._st_btn.setStyleSheet(_style_active_btn())
            self._t_btn.setStyleSheet(_style_btn())
            self._st_title.setText("ST tendency(mV)")
        else:
            self._t_btn.setStyleSheet(_style_active_btn())
            self._st_btn.setStyleSheet(_style_btn())
            self._st_title.setText("T tendency(mV)")
        self._refresh_plot()

    def update_from_metrics(self, metrics_list: list):
        self._metrics = metrics_list
        self._refresh_plot()

    def _refresh_plot(self):
        if self._current_tendency_mode == "ST":
            vals = [m.get('st_mv', 0.0) for m in self._metrics]
        else:
            vals = [m.get('t_mv', 0.0) for m in self._metrics]
        for canvas in self._st_canvases:
            canvas.set_data(vals)

    def set_replay_frame(self, data):
        if data is None or data.shape[0] < 1: return
        N = data.shape[1]
        fs = 500.0
        n_samples = min(N, int(10 * fs))
        x = np.linspace(0, n_samples/fs, n_samples) if n_samples > 0 else []
        if n_samples > 0:
            lead2_idx = 1 if data.shape[0] > 1 else 0
            self._mini_strip.set_data(x, data[lead2_idx, :n_samples].copy())
            for i, strip in enumerate(self._ch_strips):
                if i < data.shape[0]:
                    strip.set_data(x, data[i, :n_samples].copy())


class STCanvas(QWidget):
    def __init__(self, parent=None, height: int = 70):
        super().__init__(parent)
        self._data = []
        self.setFixedHeight(height)
        self.setStyleSheet(f"background:{COL_BLACK};border:none;")

    def set_data(self, vals):
        self._data = vals
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COL_BLACK))
        w, h = self.width(), self.height()
        # Zero line
        pen = QPen(QColor(COL_GREEN_DRK))
        pen.setWidth(1)
        painter.setPen(pen)
        mid = h // 2
        painter.drawLine(0, mid, w, mid)
        if not self._data: return
        d = np.array(self._data)
        mn, mx = min(d.min(), -0.1), max(d.max(), 0.1)
        rng = max(mx - mn, 0.2)
        pen = QPen(QColor(COL_GREEN))
        pen.setWidth(2)
        painter.setPen(pen)
        n = len(d)
        x_scale = w / max(n - 1, 1)
        for i in range(1, n):
            x1 = int((i-1) * x_scale)
            y1 = int(h - 5 - (d[i-1] - mn) / rng * (h - 10))
            x2 = int(i * x_scale)
            y2 = int(h - 5 - (d[i] - mn) / rng * (h - 10))
            painter.drawLine(x1, y1, x2, y2)
        # mV label
        painter.setPen(QPen(QColor(COL_GREEN_DRK)))
        if len(d) > 0:
            painter.drawText(w - 70, 14, f"{d[min(len(d)//2,len(d)-1)]:.3f}mV")


# -----------------------------------------------------------------------------
# 14. EDIT EVENT PANEL
# -----------------------------------------------------------------------------

class HolterEditEventPanel(QWidget):
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{COL_BG};")
        self._events = []
        self._session_dir = ""
        self._selected_payload = {}
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Left: event list + stats
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        cols = ["Event name", "Start Time", "Chan.", "Print Len.", "Source", "Conf."]
        self._ev_table = QTableWidget(0, len(cols))
        self._ev_table.setHorizontalHeaderLabels(cols)
        self._ev_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._ev_table.setStyleSheet(_table_style())
        self._ev_table.verticalHeader().setVisible(False)
        self._ev_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._ev_table.cellClicked.connect(self._on_click)
        left_layout.addWidget(self._ev_table, 1)

        # Stats
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"QFrame{{background:{COL_DARK};border:1px solid {COL_GREEN_DRK};border-radius:4px;}}")
        sf_layout = QGridLayout(stats_frame)
        sf_layout.setContentsMargins(8, 6, 8, 6)
        sf_layout.setSpacing(4)
        self._stat_labels = {}
        for i, (key, lbl) in enumerate([
            ("atrial_ecto","Atrial Ectopic"),("rr_int","Longest RR Interval"),
            ("hr","HR"),("max_hr","HR Max"),("min_hr","HR Min"),
            ("smax_hr","Sinus Max HR"),("smin_hr","Sinus Min HR"),
            ("brady","Bradycardia"),("user_ev","User Event"),("event","Event"),
        ]):
            r, c = divmod(i, 2)
            l = QLabel(f"{lbl}:")
            l.setStyleSheet(f"color:{UI_MUTED};font-size:10px;font-weight:bold;letter-spacing:0.5px;border:none;")
            v = QLabel("-")
            v.setStyleSheet(f"color:{COL_GREEN};font-size:12px;font-weight:bold;border:none;")
            sf_layout.addWidget(l, r*2, c)
            sf_layout.addWidget(v, r*2+1, c)
            self._stat_labels[key] = v
        left_layout.addWidget(stats_frame)
        layout.addWidget(left, 1)

        # Right: ECG strip + thumbnail
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # Tool buttons row
        tool_row = QHBoxLayout()
        for icon in ["Refresh", "Menu", "Prev", "Next", "<<", ">>", "Up", "Down"]:
            btn = QPushButton(icon)
            btn.setStyleSheet(_style_btn())
            btn.setFixedSize(30, 30)
            tool_row.addWidget(btn)
        tool_row.addStretch()
        right_layout.addLayout(tool_row)

        # 12-lead ECG strips in a vertical scroll area (3 visible at once)
        leads_scroll = QScrollArea()
        leads_scroll.setWidgetResizable(True)
        leads_scroll.setFrameShape(QFrame.NoFrame)
        leads_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        leads_scroll.setStyleSheet(f"QScrollArea{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}")
        leads_host = QWidget()
        leads_host.setStyleSheet(f"background:{COL_BLACK};")
        leads_layout = QVBoxLayout(leads_host)
        leads_layout.setContentsMargins(4, 4, 4, 4)
        leads_layout.setSpacing(2)
        self._ch_strips = []
        _all_lead_names = ["Lead I", "Lead II", "Lead III", "aVR", "aVL", "aVF",
                           "V1", "V2", "V3", "V4", "V5", "V6"]
        for name in _all_lead_names:
            lbl = QLabel(name)
            lbl.setStyleSheet(f"color:{COL_GREEN};font-size:11px;font-weight:bold;border:none;padding:2px 0;")
            leads_layout.addWidget(lbl)
            strip = ECGStripCanvas(height=80)
            strip.setFixedHeight(80)
            leads_layout.addWidget(strip)
            self._ch_strips.append(strip)
        leads_scroll.setWidget(leads_host)
        right_layout.addWidget(leads_scroll, 1)

        annot_box = QFrame()
        annot_box.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}")
        annot_layout = QGridLayout(annot_box)
        annot_layout.setContentsMargins(8, 6, 8, 6)
        annot_layout.setSpacing(6)
        annot_title = QLabel("Beat Annotation Editor")
        annot_title.setStyleSheet(f"color:{COL_GREEN};font-size:12px;font-weight:bold;border:none;")
        annot_layout.addWidget(annot_title, 0, 0, 1, 2)
        self._annot_event_id = QLineEdit()
        self._annot_event_id.setPlaceholderText("beat_id / event id")
        self._annot_event_id.setStyleSheet(f"QLineEdit{{background:{COL_DARK};color:{COL_GREEN};border:1px solid {COL_GREEN_DRK};padding:5px;border-radius:4px;}}")
        self._annot_auto = QLineEdit()
        self._annot_auto.setPlaceholderText("auto label")
        self._annot_auto.setStyleSheet(self._annot_event_id.styleSheet())
        self._annot_clin = QComboBox()
        self._annot_clin.addItems(["", "N", "S", "V", "AF", "Pause", "Tachy", "Brady", "Other"])
        self._annot_clin.setStyleSheet(f"""
            QComboBox {{
                background:{COL_DARK}; color:{COL_GREEN}; border:1px solid {COL_GREEN_DRK};
                padding:5px; border-radius:4px;
            }}
            QComboBox QAbstractItemView {{
                background:{COL_DARK}; color:white; selection-background-color:{COL_GREEN_DRK};
            }}
        """)
        self._annot_conf = QDoubleSpinBox()
        self._annot_conf.setRange(0.0, 1.0)
        self._annot_conf.setSingleStep(0.05)
        self._annot_conf.setDecimals(2)
        self._annot_conf.setValue(0.0)
        self._annot_conf.setStyleSheet(f"QDoubleSpinBox{{background:{COL_DARK};color:{COL_GREEN};border:1px solid {COL_GREEN_DRK};padding:5px;border-radius:4px;}}")
        self._annot_editor = QTextEdit()
        self._annot_editor.setPlaceholderText("Optional note or reviewer context")
        self._annot_editor.setFixedHeight(56)
        self._annot_editor.setStyleSheet(f"QTextEdit{{background:{COL_DARK};color:{COL_WHITE};border:1px solid {COL_GREEN_DRK};padding:5px;border-radius:4px;}}")
        self._annot_save_btn = QPushButton("Save Annotation")
        self._annot_save_btn.setStyleSheet(_style_active_btn())
        self._annot_save_btn.clicked.connect(self._save_annotation)
        annot_lbl = QLabel("Beat ID:")
        annot_lbl.setStyleSheet(f"color:{COL_WHITE};border:none;")
        annot_layout.addWidget(annot_lbl, 1, 0)
        annot_layout.addWidget(self._annot_event_id, 1, 1)
        annot_lbl = QLabel("Auto label:")
        annot_lbl.setStyleSheet(f"color:{COL_WHITE};border:none;")
        annot_layout.addWidget(annot_lbl, 2, 0)
        annot_layout.addWidget(self._annot_auto, 2, 1)
        annot_lbl = QLabel("Clinician label:")
        annot_lbl.setStyleSheet(f"color:{COL_WHITE};border:none;")
        annot_layout.addWidget(annot_lbl, 3, 0)
        annot_layout.addWidget(self._annot_clin, 3, 1)
        annot_lbl = QLabel("Confidence:")
        annot_lbl.setStyleSheet(f"color:{COL_WHITE};border:none;")
        annot_layout.addWidget(annot_lbl, 4, 0)
        annot_layout.addWidget(self._annot_conf, 4, 1)
        annot_layout.addWidget(self._annot_editor, 5, 0, 1, 2)
        annot_layout.addWidget(self._annot_save_btn, 6, 0, 1, 2)
        right_layout.addWidget(annot_box)

        nav_row = QHBoxLayout()
        for lbl in ["Prev Event", "Next Event", "Remove All", "Remove"]:
            btn = QPushButton(lbl)
            btn.setStyleSheet(_style_btn())
            nav_row.addWidget(btn)
        right_layout.addLayout(nav_row)
        layout.addWidget(right, 2)

    def load_events(self, events: list, summary: dict):
        self._events = events
        self._ev_table.setRowCount(len(events))
        for i, ev in enumerate(events):
            source = str(ev.get("source", "analysis"))
            conf = float(ev.get("confidence", 0.0) or 0.0)
            for j, val in enumerate([ev['label'], _sec_to_hms(ev['timestamp']), "3", "7s", source, f"{conf:.2f}"]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(COL_WHITE))
                if j == 0:
                    item.setData(Qt.UserRole, {
                        "beat_id": str(ev.get("beat_id", ev.get("template_label", ev.get("label", "")))),
                        "auto_label": str(ev.get("template_label", ev.get("label", ""))),
                        "clinician_label": str(ev.get("label", "")),
                        "confidence": conf,
                        "timestamp": float(ev.get("timestamp", 0.0) or 0.0),
                        "source": source,
                    })
                self._ev_table.setItem(i, j, item)
        s = summary
        for key, fmt in [("hr",f"{s.get('avg_hr',0):.0f} bpm"),
                          ("max_hr",f"{s.get('max_hr',0):.0f} bpm"),
                          ("min_hr",f"{s.get('min_hr',0):.0f} bpm"),
                          ("smax_hr",f"{s.get('max_hr',0):.0f} bpm"),
                          ("smin_hr",f"{s.get('min_hr',0):.0f} bpm"),
                          ("brady",str(s.get('brady_beats',0))),
                          ("user_ev","1"),("event","1"),
                          ("rr_int",f"{s.get('longest_rr_ms',0):.0f} ms"),
                          ("atrial_ecto","1")]:
            if key in self._stat_labels:
                self._stat_labels[key].setText(fmt)

    def _on_click(self, row, col):
        if row < len(self._events):
            self.seek_requested.emit(self._events[row]['timestamp'])
            item = self._ev_table.item(row, 0)
            if item:
                payload = item.data(Qt.UserRole) or {}
                self._selected_payload = dict(payload)
                self._annot_event_id.setText(str(payload.get("beat_id", "")))
                self._annot_auto.setText(str(payload.get("auto_label", "")))
                self._annot_clin.setCurrentText(str(payload.get("clinician_label", "")))
                self._annot_conf.setValue(float(payload.get("confidence", 0.0) or 0.0))
                self._annot_editor.setPlainText(
                    f"Source: {payload.get('source', '')}\n"
                    f"Timestamp: {_sec_to_hms(float(payload.get('timestamp', 0.0) or 0.0))}"
                )

    def set_session_dir(self, session_dir: str):
        self._session_dir = session_dir or ""

    def _save_annotation(self):
        if not self._session_dir:
            QMessageBox.information(self, "Annotation", "No session directory is available for saving.")
            return
        beat_id = self._annot_event_id.text().strip()
        if not beat_id:
            QMessageBox.information(self, "Annotation", "Select an event or enter a beat ID first.")
            return
        annotation = {
            "beat_id": beat_id,
            "auto_label": self._annot_auto.text().strip(),
            "clinician_label": self._annot_clin.currentText().strip() or self._annot_auto.text().strip(),
            "confidence": float(self._annot_conf.value()),
            "edited_by": "clinician",
            "timestamp": float(self._selected_payload.get("timestamp", self._events[0].get("timestamp", 0.0) if self._events else 0.0)),
            "note": self._annot_editor.toPlainText().strip(),
        }
        try:
            append_annotation(self._session_dir, annotation)
            QMessageBox.information(self, "Annotation", "Annotation saved to session database.")
        except Exception as e:
            QMessageBox.warning(self, "Annotation", f"Could not save annotation: {e}")

    def set_replay_frame(self, data):
        if data is None or data.shape[0] < 1: return
        N = data.shape[1]
        x = np.linspace(0, N/500.0, N) if N > 0 else []
        for i, strip in enumerate(self._ch_strips):
            if i < data.shape[0] and N > 0:
                strip.set_data(x, data[i].copy())
            elif N > 0:
                strip.set_data([], [])


class ClickableSummaryTile(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, tile_key: str, parent=None):
        super().__init__(parent)
        self.tile_key = tile_key
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.tile_key)
        super().mousePressEvent(event)


# -----------------------------------------------------------------------------
# 15. EDIT STRIPS PANEL
# -----------------------------------------------------------------------------

class HolterEditStripsPanel(QWidget):
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{COL_BG};")
        self._events = []
        self._summary = {}
        self._metrics_list = []
        self._focus_cards = {}
        self._selected_focus_key = "max_hr"
        self._selected_payload = {}
        self._tile_widgets = {}
        self._stat_labels = {}
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # --- LEFT: Event List (20% width) ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        cols = ["Event name", "Start Time", "Chan.", "Print Len."]
        self._ev_table = QTableWidget(0, len(cols))
        self._ev_table.setHorizontalHeaderLabels(cols)
        self._ev_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._ev_table.setStyleSheet(_table_style())
        self._ev_table.verticalHeader().setVisible(False)
        left_layout.addWidget(self._ev_table, 1)

        nav_row = QHBoxLayout()
        for lbl in ["Prev", "Next", "Remove All", "Remove"]:
            btn = QPushButton(lbl)
            btn.setStyleSheet(_style_btn())
            nav_row.addWidget(btn)
        left_layout.addLayout(nav_row)

        stats_frame = QFrame()
        stats_frame.setStyleSheet(
            f"QFrame{{background:{COL_DARK};border:1px solid {COL_GREEN_DRK};border-radius:6px;}}"
        )
        sf_layout = QGridLayout(stats_frame)
        sf_layout.setContentsMargins(8, 6, 8, 6)
        sf_layout.setSpacing(6)
        for i, (key, label) in enumerate([
            ("hr", "Avg HR"),
            ("max_hr", "HR Max"),
            ("min_hr", "HR Min"),
            ("smax_hr", "Sinus Max HR"),
            ("smin_hr", "Sinus Min HR"),
            ("rr_int", "Longest RR"),
            ("brady", "Brady"),
            ("user_ev", "User Event"),
        ]):
            row, col = divmod(i, 2)
            l = QLabel(f"{label}:")
            l.setStyleSheet(f"color:{UI_MUTED};font-size:10px;font-weight:bold;letter-spacing:0.5px;border:none;")
            v = QLabel("-")
            v.setStyleSheet(f"color:{COL_GREEN};font-size:12px;font-weight:bold;border:none;")
            sf_layout.addWidget(l, row * 2, col)
            sf_layout.addWidget(v, row * 2 + 1, col)
            self._stat_labels[key] = v
        left_layout.addWidget(stats_frame)
        layout.addWidget(left, 2)

        # --- CENTER: 2x2 Thumbnail Boxes (30% width) ---
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)

        # Tool buttons
        tool_row = QHBoxLayout()
        for icon in ["Refresh", "Menu", "Prev", "Next", "<<", ">>", "Up", "Down", "End"]:
            btn = QPushButton(icon)
            btn.setStyleSheet(_style_btn())
            btn.setFixedSize(28, 28)
            tool_row.addWidget(btn)
        tool_row.addStretch()
        center_layout.addLayout(tool_row)

        thumb_grid = QGridLayout()
        thumb_grid.setSpacing(12)
        thumb_grid.setHorizontalSpacing(12)
        thumb_grid.setVerticalSpacing(12)
        self._thumb_frames = []
        self._tile_style_normal = f"QFrame{{background:{COL_DARK};border:1px solid #888888;border-radius:8px;}}"
        self._tile_style_active = f"QFrame{{background:{COL_BLACK};border:2px solid {COL_YELLOW};border-radius:8px;}}"
        self._tile_widgets = {}
        tile_specs = [
            (0, 0, "max_hr", "Maximum Heart Rate"),
            (0, 1, "min_hr", "Minimum Heart Rate"),
            (1, 0, "smax_hr", "Sinus Max HR"),
            (1, 1, "smin_hr", "Sinus Min HR"),
        ]
        for row, col, key, title in tile_specs:
            frame = ClickableSummaryTile(key)
            frame.setMinimumHeight(210)
            frame.setMinimumWidth(280)
            frame.setStyleSheet(self._tile_style_normal)
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(8, 8, 8, 8)
            fl.setSpacing(4)

            header_w = QWidget()
            header_w.setStyleSheet("border:none;")
            hl = QHBoxLayout(header_w)
            hl.setContentsMargins(0, 0, 0, 0)
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet("color:#FFFFFF;font-size:12px;font-weight:bold;")
            hl.addWidget(t_lbl)
            hl.addStretch()
            hr_lbl = QLabel("HR: --")
            hr_lbl.setStyleSheet("color:#FFFF00;font-size:11px;font-weight:bold;")
            hl.addWidget(hr_lbl)
            fl.addWidget(header_w)

            time_lbl = QLabel("--:--:--")
            time_lbl.setStyleSheet("color:#AAAAAA;font-size:10px;")
            fl.addWidget(time_lbl)

            strips = []
            for _ in range(3):
                strip = ECGStripCanvas(height=40)
                strip.setStyleSheet("border:1px solid #444444;")
                fl.addWidget(strip)
                strips.append(strip)
                self._thumb_frames.append(strip)

            self._tile_widgets[key] = {
                "frame": frame,
                "title": t_lbl,
                "hr": hr_lbl,
                "time": time_lbl,
                "strips": strips,
            }
            frame.clicked.connect(self._select_focus_tile)
            thumb_grid.addWidget(frame, row, col)

        thumb_grid.setColumnStretch(0, 1)
        thumb_grid.setColumnStretch(1, 1)
        center_layout.addLayout(thumb_grid)
        center_layout.addStretch()
        layout.addWidget(center, 4)

        # --- RIGHT: Large Clinical Strip View (50% width) ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        detail_frame = QFrame()
        detail_frame.setStyleSheet(
            f"QFrame{{background:{COL_BLACK};border:1px solid {COL_GREEN_DRK};border-radius:8px;}}"
        )
        df_layout = QGridLayout(detail_frame)
        df_layout.setContentsMargins(10, 8, 10, 8)
        df_layout.setHorizontalSpacing(10)
        df_layout.setVerticalSpacing(4)
        self._detail_title = QLabel("Select a heart-rate tile")
        self._detail_title.setStyleSheet(
            f"color:{COL_YELLOW};font-size:14px;font-weight:bold;border:none;"
        )
        self._detail_value = QLabel("-- bpm")
        self._detail_value.setStyleSheet(
            f"color:{COL_GREEN};font-size:26px;font-weight:bold;border:none;"
        )
        self._detail_time = QLabel("-")
        self._detail_time.setStyleSheet(
            f"color:{COL_TIMESTAMP};font-size:11px;font-weight:bold;border:none;"
        )
        self._detail_note = QLabel("Click any tile to expand the matching strip view here.")
        self._detail_note.setStyleSheet(
            f"color:{COL_WHITE};font-size:11px;border:none;"
        )
        self._detail_note.setWordWrap(True)
        df_layout.addWidget(self._detail_title, 0, 0, 1, 2)
        df_layout.addWidget(self._detail_value, 1, 0, 1, 1)
        df_layout.addWidget(self._detail_time, 1, 1, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
        df_layout.addWidget(self._detail_note, 2, 0, 1, 2)
        right_layout.addWidget(detail_frame, 0)

        main_frame = QFrame()
        main_frame.setStyleSheet(f"QFrame{{background:{COL_BLACK};border:1px solid #888888;border-radius:4px;}}")
        ml = QVBoxLayout(main_frame)
        ml.setContentsMargins(8, 8, 8, 8)

        self._detail_header_lbl = QLabel("Detailed View")
        self._detail_header_lbl.setStyleSheet("color:#FFFF00;font-size:12px;font-weight:bold;border:none;")
        ml.addWidget(self._detail_header_lbl)

        self._main_strips = []
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(6)
        
        lead_names = ["Lead I", "Lead II", "Lead III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
        
        for name in lead_names:
            lbl = QLabel(name)
            lbl.setStyleSheet(f"color:{COL_GREEN};border:none;font-weight:bold;")
            strip = ECGStripCanvas(height=95)
            scroll_layout.addWidget(lbl)
            scroll_layout.addWidget(strip)
            self._main_strips.append(strip)
            
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        ml.addWidget(scroll_area)

        right_layout.addWidget(main_frame, 1)

        self._mini_lbl = QLabel("Lead II")
        self._mini_lbl.setStyleSheet(f"color:{COL_GREEN};border:none;font-weight:bold;")
        right_layout.addWidget(self._mini_lbl)

        self._mini = ECGStripCanvas(height=40, color="#00AA00")
        right_layout.addWidget(self._mini)
        layout.addWidget(right, 5)

    def _format_bpm(self, value: float) -> str:
        if value and value > 0:
            return f"{float(value):.0f} bpm"
        return "-- bpm"

    def _build_focus_cards(self):
        summary = self._summary or {}
        focus = derive_hr_focus_summary(self._metrics_list or [])

        def _metric_value(*keys, default=0.0):
            for key in keys:
                for source in (summary, focus):
                    if source.get(key) is not None:
                        try:
                            value = float(source.get(key) or 0.0)
                            if value > 0:
                                return value
                        except Exception:
                            continue
            return float(default)

        def _metric_time(*keys):
            for key in keys:
                for source in (summary, focus):
                    val = source.get(f"{key}_time")
                    if val:
                        return str(val)
            return ""

        def _metric_timestamp(*keys):
            for key in keys:
                for source in (summary, focus):
                    val = source.get(f"{key}_timestamp")
                    if val is not None:
                        try:
                            ts = float(val or 0.0)
                            if ts > 0:
                                return ts
                        except Exception:
                            continue
            return 0.0

        self._focus_cards = {
            "max_hr": {
                "title": "Maximum Heart Rate",
                "value": _metric_value("max_hr"),
                "time": _metric_time("max_hr"),
                "timestamp": _metric_timestamp("max_hr"),
                "note": "Highest overall heart rate found in the recording.",
            },
            "min_hr": {
                "title": "Minimum Heart Rate",
                "value": _metric_value("min_hr"),
                "time": _metric_time("min_hr"),
                "timestamp": _metric_timestamp("min_hr"),
                "note": "Lowest overall heart rate found in the recording.",
            },
            "smax_hr": {
                "title": "Sinus Max HR",
                "value": _metric_value("sinus_max_hr", "max_hr"),
                "time": _metric_time("sinus_max_hr", "max_hr"),
                "timestamp": _metric_timestamp("sinus_max_hr", "max_hr"),
                "note": "Highest heart rate from sinus-like beats.",
            },
            "smin_hr": {
                "title": "Sinus Min HR",
                "value": _metric_value("sinus_min_hr", "min_hr"),
                "time": _metric_time("sinus_min_hr", "min_hr"),
                "timestamp": _metric_timestamp("sinus_min_hr", "min_hr"),
                "note": "Lowest heart rate from sinus-like beats.",
            },
        }

    def _refresh_focus_tiles(self):
        for key, widget in self._tile_widgets.items():
            card = self._focus_cards.get(key, {})
            widget["hr"].setText(f"HR: {self._format_bpm(card.get('value', 0.0))}")
            widget["time"].setText(card.get("time") or "-")
            widget["frame"].setStyleSheet(
                self._tile_style_active if key == self._selected_focus_key else self._tile_style_normal
            )

    def _update_detail_panel(self, key: str):
        card = self._focus_cards.get(key) or self._focus_cards.get("max_hr") or {}
        title = card.get("title", "Heart Rate Detail")
        value = card.get("value", 0.0)
        time_str = card.get("time") or "-"
        note = card.get("note", "")
        self._detail_title.setText(title)
        self._detail_value.setText(self._format_bpm(value))
        self._detail_time.setText(time_str)
        self._detail_note.setText(note or "Click a tile to expand the matching strip view here.")
        self._detail_header_lbl.setText(f"Detailed View  -  {title}  -  {time_str}")

    def _select_focus_tile(self, tile_key: str, emit_seek: bool = True):
        if tile_key not in self._focus_cards:
            return
        self._selected_focus_key = tile_key
        self._refresh_focus_tiles()
        self._update_detail_panel(tile_key)
        if emit_seek:
            timestamp = float(self._focus_cards.get(tile_key, {}).get("timestamp", 0.0) or 0.0)
            if timestamp > 0:
                self.seek_requested.emit(timestamp)

    def load_events(self, events: list, summary: dict, metrics_list: Optional[list] = None):
        self._events = events
        self._summary = dict(summary or {})
        self._metrics_list = list(metrics_list or [])
        self._build_focus_cards()
        self._ev_table.setRowCount(len(events))
        for i, ev in enumerate(events):
            for j, val in enumerate([ev['label'], _sec_to_hms(ev['timestamp']), "3", "7s"]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(COL_WHITE))
                self._ev_table.setItem(i, j, item)
        if self._selected_focus_key not in self._focus_cards:
            self._selected_focus_key = "max_hr"
        self._refresh_focus_tiles()
        self._update_detail_panel(self._selected_focus_key)
        s = self._summary
        max_card = self._focus_cards.get("max_hr", {})
        min_card = self._focus_cards.get("min_hr", {})
        smax_card = self._focus_cards.get("smax_hr", {})
        smin_card = self._focus_cards.get("smin_hr", {})
        for key, fmt in [("hr",f"{s.get('avg_hr',0):.0f} bpm"),
                          ("max_hr",self._format_bpm(float(max_card.get('value', s.get('max_hr',0)) or 0.0))),
                          ("min_hr",self._format_bpm(float(min_card.get('value', s.get('min_hr',0)) or 0.0))),
                          ("smax_hr",self._format_bpm(float(smax_card.get('value', s.get('sinus_max_hr', s.get('max_hr',0))) or 0.0))),
                          ("smin_hr",self._format_bpm(float(smin_card.get('value', s.get('sinus_min_hr', s.get('min_hr',0))) or 0.0))),
                          ("brady",str(s.get('brady_beats',0))),
                          ("user_ev","1"),("event","1"),
                          ("rr_int",f"{s.get('longest_rr_ms',0):.0f} ms"),
                          ("atrial_ecto","1")]:
            if key in self._stat_labels:
                self._stat_labels[key].setText(fmt)

    def set_replay_frame(self, data, metrics_dict=None, current_sec=0.0):
        if data is None or data.shape[0] < 1: return
        N = data.shape[1]
        x = np.linspace(0, N/250.0, N) if N > 0 else []
        
        start_sec = max(0.0, current_sec - 5.0) # 10s window centered
        all_beats = metrics_dict.get('all_beats', []) if metrics_dict else []
        
        if N > 0:
            # Update thumbnails (cycle through CH1, CH2, CH3 if available)
            for i, strip in enumerate(self._thumb_frames):
                ch_idx = i % 3
                if ch_idx < data.shape[0]:
                    strip.set_data(x, data[ch_idx].copy(), beat_annotations=all_beats, start_sec=start_sec)
                else:
                    strip.set_data(x, data[0].copy(), beat_annotations=all_beats, start_sec=start_sec)
            
            # Update large main strips
            if hasattr(self, "_main_strips"):
                for idx, strip in enumerate(self._main_strips):
                    if idx < data.shape[0]:
                        strip.set_data(x, data[idx].copy(), beat_annotations=all_beats, start_sec=start_sec)
                    elif data.shape[0] > 0:
                        strip.set_data(x, np.zeros_like(data[0]), beat_annotations=all_beats, start_sec=start_sec)
                
            if data.shape[0] > 1:
                self._mini.set_data(x, data[1].copy(), beat_annotations=all_beats, start_sec=start_sec)
            else:
                self._mini.set_data(x, data[0].copy(), beat_annotations=all_beats, start_sec=start_sec)


# -----------------------------------------------------------------------------
# 16. REPORT TABLE PANEL
# -----------------------------------------------------------------------------

class HolterReportTablePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{COL_BG};")
        self._build_ui()

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Hour-by-Hour Report Table")
        title.setStyleSheet(f"color:{COL_GREEN};font-size:14px;font-weight:bold;border:none;")
        layout.addWidget(title)

        cols = ["Hour", "Beats", "HR Min", "HR Avg", "HR Max",
                "VE Iso.", "VE Coup.", "VE Runs", "VE Total", "VE %",
                "SVE Iso.", "SVE Coup.", "SVE Total", "Pauses"]
        self._table = QTableWidget(0, len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.setStyleSheet(_table_style())
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._table, 1)

    def update_from_metrics(self, metrics_list: list):
        hourly: Dict[int, list] = {}
        for m in metrics_list:
            h = int(m.get('t', 0) // 3600)
            hourly.setdefault(h, []).append(m)

        rows = []
        total_beats = total_pauses = 0
        for h in sorted(hourly.keys()):
            chunks = hourly[h]
            beats = sum(c.get('beat_count', 0) for c in chunks)
            hr_vals = [c.get('hr_mean', 0) for c in chunks if c.get('hr_mean', 0) > 0]
            hr_min_vals = [c.get('hr_min', 0) for c in chunks if c.get('hr_min', 0) > 0]
            hr_max_vals = [c.get('hr_max', 0) for c in chunks if c.get('hr_max', 0) > 0]
            pauses = sum(c.get('pauses', 0) for c in chunks)
            avg_hr = int(np.mean(hr_vals)) if hr_vals else 0
            min_hr = int(np.min(hr_min_vals)) if hr_min_vals else 0
            max_hr = int(np.max(hr_max_vals)) if hr_max_vals else 0
            total_beats += beats
            total_pauses += pauses
            rows.append([f"{h:02d}:00", str(beats), str(min_hr), str(avg_hr), str(max_hr),
                          "0","0","0","0","0%","0","0","0", str(pauses)])

        # Total row
        rows.append(["Total", str(total_beats), "-", "-", "-",
                      "0","0","0","0","0%","0","0","0", str(total_pauses)])

        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            is_total = (i == len(rows) - 1)
            for j, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(COL_GREEN if j == 0 or is_total else COL_WHITE))
                if is_total:
                    item.setBackground(QColor(COL_GREEN_DRK))
                self._table.setItem(i, j, item)

# -----------------------------------------------------------------------------
# 17. HOLTER MAIN WINDOW  - Orchestrates everything
# -----------------------------------------------------------------------------

class HolterMainWindow(QDialog):
    def __init__(self, parent=None, session_dir: str = "",
                 patient_info: dict = None,
                 writer=None,
                 live_source=None,
                 duration_hours: int = 24):
        super().__init__(parent)
        self.setWindowTitle("Comprehensive ECG Analysis Monitor & Analysis")
        self.setMinimumSize(900, 620)

        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.resize(max(1100, int(g.width() * 0.92)), max(750, int(g.height() * 0.92)))
        else:
            self.resize(1400, 900)

        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet(f"QDialog{{background:{UI_BG};}}")
        self.showMaximized()

        self.session_dir = session_dir
        self.patient_info = _normalize_patient_info(patient_info or (writer.patient_info if writer else {}))
        self._writer = writer
        self._live_source = live_source
        self._duration_hours = duration_hours
        self._replay_engine = None
        self._metrics_list = []
        self._summary = {}
        self._last_live_seq = -1
        self._tab_name_map = {}

        if not self.session_dir and writer:
            self.session_dir = getattr(writer, 'session_dir', '')

        self._load_session()
        self._build_ui()

        if self._writer:
            self._live_timer = QTimer(self)
            self._live_timer.timeout.connect(self._update_live_ui)
            self._live_timer.start(1000)

    # ---- Session loading -----------------------------------------------------------------------------

    def _load_session(self):
        self._metrics_list = []
        metadata = read_session_metadata(self.session_dir) if self.session_dir else {}
        self.patient_info = _load_patient_info_from_session(self.session_dir, self.patient_info)
        layered_metrics = load_metrics(self.session_dir) if self.session_dir else []
        if layered_metrics:
            self._metrics_list = layered_metrics
        jsonl_path = os.path.join(self.session_dir, 'metrics.jsonl') if self.session_dir else ''
        if not self._metrics_list and os.path.exists(jsonl_path):
            try:
                with open(jsonl_path) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._metrics_list.append(json.loads(line))
            except Exception as e:
                print(f"[HolterUI] Could not load metrics: {e}")

        ecgh_path = os.path.join(self.session_dir, 'recording.ecgh') if self.session_dir else ''
        if os.path.exists(ecgh_path):
            try:
                from .file_format import ECGHFileReader
                from .replay_engine import HolterReplayEngine
                self._replay_engine = HolterReplayEngine(ecgh_path)
                self._summary = self._replay_engine.get_summary()
            except Exception as e:
                print(f"[HolterUI] Replay engine error: {e}")
                self._summary = self._build_summary_from_metrics()
        else:
            self._summary = self._build_summary_from_metrics()
        if metadata and isinstance(metadata.get("summary"), dict):
            meta_sum = dict(metadata.get("summary"))
            if self._summary:
                meta_sum.update(self._summary)
            self._summary = meta_sum
        if self._summary is not None:
            self._summary["patient_info"] = dict(self.patient_info or {})

    def _build_summary_from_metrics(self) -> dict:
        if not self._metrics_list:
            return {}
        ml = self._metrics_list
        hr_vals = [m['hr_mean'] for m in ml if m.get('hr_mean', 0) > 0]
        beat_counts = [m.get('beat_count', 0) for m in ml]
        rr_stds = [m['rr_std'] for m in ml if m.get('rr_std', 0) > 0]
        rmssds = [m['rmssd'] for m in ml if m.get('rmssd', 0) > 0]
        pnn50s = [m['pnn50'] for m in ml if m.get('pnn50', 0) >= 0]
        qualities = [m['quality'] for m in ml if m.get('quality', 0) > 0]
        arrhy_counts: Dict[str, int] = {}
        beat_class_totals: Dict[str, int] = {}
        template_counts = []
        tachy_sec = 0.0
        brady_sec = 0.0
        for m in ml:
            for a in m.get('arrhythmias', []):
                arrhy_counts[a] = arrhy_counts.get(a, 0) + 1
            for cls, count in (m.get('beat_class_counts', {}) or {}).items():
                beat_class_totals[cls] = beat_class_totals.get(cls, 0) + int(count or 0)
            template_counts.append(int(m.get('template_count', 0) or 0))
            chunk_dur = float(m.get('duration', 4.0) or 4.0)
            hr_m = float(m.get('hr_mean', 0) or 0)
            if hr_m > 100:
                tachy_sec += chunk_dur
            elif 0 < hr_m < 60:
                brady_sec += chunk_dur
        all_rr = [m.get('longest_rr', 0) for m in ml]
        # Find max/min HR chunks for timestamps
        max_hr_chunk = max((m for m in ml if m.get('hr_mean', 0) > 0), key=lambda m: m.get('hr_mean', 0), default={})
        min_hr_chunk = min((m for m in ml if m.get('hr_mean', 0) > 0), key=lambda m: m.get('hr_mean', 0), default={})
        max_hr_t = float(max_hr_chunk.get('t', 0.0) or 0.0)
        min_hr_t = float(min_hr_chunk.get('t', 0.0) or 0.0)
        focus = derive_hr_focus_summary(ml)
        total_dur = _metrics_duration_sec(ml)
        tachy_pct = (tachy_sec / total_dur * 100) if total_dur > 0 else 0.0
        brady_pct = (brady_sec / total_dur * 100) if total_dur > 0 else 0.0
        return {
            'duration_sec': total_dur,
            'total_beats': sum(beat_counts),
            'avg_hr': float(np.mean(hr_vals)) if hr_vals else 0.0,
            'max_hr': float(np.max(hr_vals)) if hr_vals else 0.0,
            'min_hr': float(np.min(hr_vals)) if hr_vals else 0.0,
            'max_hr_time': _sec_to_hms(max_hr_t),
            'max_hr_timestamp': max_hr_t,
            'min_hr_time': _sec_to_hms(min_hr_t),
            'min_hr_timestamp': min_hr_t,
            'sinus_max_hr': focus.get('sinus_max_hr', float(np.max(hr_vals)) if hr_vals else 0.0),
            'sinus_min_hr': focus.get('sinus_min_hr', float(np.min(hr_vals)) if hr_vals else 0.0),
            'sinus_max_hr_time': focus.get('sinus_max_hr_time', _sec_to_hms(max_hr_t)),
            'sinus_max_hr_timestamp': focus.get('sinus_max_hr_timestamp', max_hr_t),
            'sinus_min_hr_time': focus.get('sinus_min_hr_time', _sec_to_hms(min_hr_t)),
            'sinus_min_hr_timestamp': focus.get('sinus_min_hr_timestamp', min_hr_t),
            'sdnn': float(np.mean(rr_stds)) if rr_stds else 0.0,
            'rmssd': float(np.mean(rmssds)) if rmssds else 0.0,
            'pnn50': float(np.mean(pnn50s)) if pnn50s else 0.0,
            'avg_quality': float(np.mean(qualities)) if qualities else 1.0,
            'arrhythmia_counts': arrhy_counts,
            'longest_rr_ms': max(all_rr) if all_rr else 0,
            'tachy_beats': sum(m.get('tachy_beats', 0) for m in ml),
            'brady_beats': sum(m.get('brady_beats', 0) for m in ml),
            'tachy_sec': tachy_sec,
            'brady_sec': brady_sec,
            'tachy_pct': tachy_pct,
            'brady_pct': brady_pct,
            'pauses': sum(m.get('pauses', 0) for m in ml),
            'avg_st_mv': float(np.mean([m.get('st_mv', 0) for m in ml])),
            'patient_info': self.patient_info,
            'chunks_analyzed': len(ml),
            'beat_class_totals': beat_class_totals,
            've_beats': int(beat_class_totals.get('VE', 0)),
            'sve_beats': int(beat_class_totals.get('SVE', 0)),
            'template_count': max(template_counts) if template_counts else 0,
        }

    def _tab_index_for(self, name: str) -> int:
        if not hasattr(self, '_tabs'):
            return -1
        target = (name or '').strip().lower()
        aliases = {
            'overview': 'overview',
            'view': 'preview',
            'report': 'preview',
            'preview': 'preview',
            'lorenz': 'lorenz',
            'histogram': 'histogram',
            'template': 'template',
            'af analysis': 'af analysis',
            'st tendency': 'st tendency',
            'edit event': 'edit event',
            'edit strips': 'edit strips',
            'report table': 'report table',
            'hrv': 'hrv',
            'recordings': 'recordings',
            'record settings': 'recordings',
            'replay': 'replay',
            'lorenz': 'replay',
        }
        target = aliases.get(target, target)
        for idx in range(self._tabs.count()):
            if self._tabs.tabText(idx).strip().lower() == target:
                return idx
        return -1

    def _focus_tab(self, name: str):
        idx = self._tab_index_for(name)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _recordings_panel(self):
        return getattr(self, '_record_mgmt_panel', None)

    def _open_recordings_folder(self):
        if self._is_replay_active():
            return
        self._focus_tab('RECORDINGS')

    def _search_recordings(self):
        if self._is_replay_active():
            return
        self._focus_tab('RECORDINGS')
        panel = self._recordings_panel()
        if panel and hasattr(panel, '_search'):
            panel._search.setFocus()
            panel._search.selectAll()

    def _apply_recordings_filter(self, label: str):
        if self._is_replay_active():
            return
        self._focus_tab('RECORDINGS')
        panel = self._recordings_panel()
        if panel and hasattr(panel, '_filter'):
            idx = panel._filter.findText(label)
            if idx >= 0:
                panel._filter.setCurrentIndex(idx)

    def _import_recording(self):
        if self._is_replay_active():
            return
        panel = self._recordings_panel()
        if panel and hasattr(panel, '_import_session'):
            panel._import_session()

    def _backup_recordings(self):
        if self._is_replay_active():
            return
        panel = self._recordings_panel()
        if panel and hasattr(panel, '_backup_root'):
            panel._backup_root()

    def _delete_recording(self):
        if self._is_replay_active():
            return
        panel = self._recordings_panel()
        if panel and hasattr(panel, '_delete_session'):
            panel._delete_session()

    def _is_replay_active(self) -> bool:
        panel = getattr(self, "_replay_panel", None)
        engine = getattr(self, "_replay_engine", None)
        return bool(panel and engine and engine.is_playing())

    def _set_record_browser_enabled(self, enabled: bool):
        panel = self._recordings_panel()
        if panel is not None:
            for name in ("Browse", "Import", "Export", "Backup", "Delete"):
                btn = getattr(panel, "_action_buttons", {}).get(name)
                if btn is not None:
                    btn.setEnabled(bool(enabled))
            table = getattr(panel, "_table", None)
            if table is not None:
                table.setEnabled(bool(enabled))
        top_browse = getattr(self, "_action_buttons", {}).get("Browse")
        if top_browse is not None:
            top_browse.setEnabled(bool(enabled))

    def _generate_from_current(self):
        self._focus_tab('PREVIEW')
        self._generate_report()

    def _refresh_current_session(self):
        self._load_session()
        self._refresh_ui()

    def _confirm_reanalysis(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Reanalyse Data")
        msg_box.setText("Would you like to reanalyse the data?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background:{COL_BG};
                border:2px solid {COL_GREEN_DRK};
            }}
            QMessageBox QLabel {{
                color:{COL_WHITE};
                font-size:13px;
                font-weight:bold;
                border:none;
            }}
            QPushButton {{
                background:{COL_DARK};
                color:{COL_GREEN};
                border:1px solid {COL_GREEN_DRK};
                padding:6px 22px;
                border-radius:5px;
                font-size:12px;
                font-weight:bold;
            }}
            QPushButton:hover {{
                background:{COL_GREEN_DRK};
                color:{COL_WHITE};
            }}
            QPushButton:pressed {{
                background:{COL_GREEN};
                color:{COL_BLACK};
            }}
        """)
        reply = msg_box.exec_()
        if reply == QMessageBox.Yes:
            self._run_reanalysis_with_progress()

    def _run_reanalysis_with_progress(self):
        # --- Progress dialog ---
        dlg = QDialog(self, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        dlg.setFixedSize(480, 160)
        dlg.setStyleSheet("""
            QDialog {
                background: #0D1117;
                border: 1px solid #00CC66;
                border-radius: 12px;
            }
        """)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(28, 22, 28, 22)
        dlg_layout.setSpacing(10)

        # Header row
        hdr_row = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet("color:#00FF00; font-size:14px; border:none;")
        hdr_row.addWidget(dot)
        title_lbl = QLabel("ECG Reanalysis")
        title_lbl.setStyleSheet("color:#00FF00; font-size:14px; font-weight:bold; border:none; letter-spacing:1px;")
        hdr_row.addWidget(title_lbl)
        hdr_row.addStretch()
        pct_lbl = QLabel("0%")
        pct_lbl.setStyleSheet("color:#00CC66; font-size:12px; font-weight:bold; border:none;")
        hdr_row.addWidget(pct_lbl)
        dlg_layout.addLayout(hdr_row)

        # Progress bar
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(False)
        progress.setFixedHeight(10)
        progress.setStyleSheet("""
            QProgressBar {
                background: #161B22;
                border: 1px solid #444444;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00CC66, stop:0.6 #00FF00, stop:1 #66FFB3);
                border-radius: 5px;
            }
        """)
        dlg_layout.addWidget(progress)

        # Status label
        status_lbl = QLabel("Initialising…")
        status_lbl.setStyleSheet("color:#888888; font-size:11px; border:none;")
        dlg_layout.addWidget(status_lbl)

        # Sub info
        sub_lbl = QLabel("This may take a few moments depending on recording length.")
        sub_lbl.setStyleSheet("color:#444444; font-size:10px; border:none;")
        dlg_layout.addWidget(sub_lbl)

        dlg.setModal(True)
        dlg.show()
        QApplication.processEvents()

        # --- Worker thread ---
        class _ReanalysisWorker(QThread):
            progress_changed = pyqtSignal(int, str)
            finished_ok = pyqtSignal()

            def __init__(self, fn):
                super().__init__()
                self._fn = fn

            def run(self):
                self.progress_changed.emit(10, "Loading session metadata…")
                try:
                    self._fn()
                    self.progress_changed.emit(90, "Finalising…")
                except Exception as e:
                    print(f"[Reanalysis] Error: {e}")
                self.progress_changed.emit(100, "Done!")
                self.finished_ok.emit()

        def _on_progress(val, txt):
            progress.setValue(val)
            pct_lbl.setText(f"{val}%")
            status_lbl.setText(txt)
            QApplication.processEvents()

        def _on_done():
            progress.setValue(100)
            pct_lbl.setText("100%")
            status_lbl.setText("Complete — loading replay…")
            QApplication.processEvents()
            QTimer.singleShot(450, lambda: (dlg.accept(), _navigate_replay()))

        def _navigate_replay():
            try:
                self._refresh_ui()
            except Exception as e:
                print(f"[Reanalysis] _refresh_ui error: {e}")
            self._focus_tab('REPLAY')

        self._reanalysis_worker = _ReanalysisWorker(self._load_session)
        self._reanalysis_worker.progress_changed.connect(_on_progress)
        self._reanalysis_worker.finished_ok.connect(_on_done)

        # Animate progress bar smoothly with a timer while the thread runs
        _tick_val = [10]
        _anim_timer = QTimer(self)
        def _tick():
            if _tick_val[0] < 88:
                _tick_val[0] += 1
                progress.setValue(_tick_val[0])
                msg = ("Loading recorded data…" if _tick_val[0] < 30 else
                       "Running beat classification…" if _tick_val[0] < 55 else
                       "Computing HRV metrics…" if _tick_val[0] < 75 else
                       "Building summary…")
                status_lbl.setText(msg)
                pct_lbl.setText(f"{_tick_val[0]}%")
        _anim_timer.timeout.connect(_tick)
        _anim_timer.start(40)  # ~25 fps smooth fill

        self._reanalysis_worker.finished_ok.connect(_anim_timer.stop)
        self._reanalysis_worker.start()

    def _on_workspace_section_requested(self, section: str):
        key = (section or '').strip().lower()
        if key == 'quit':
            self.close()
        elif key in {'reanalysis', 'replay'}:
            self._confirm_reanalysis()
        elif key in {'overview'}:
            self._focus_tab('OVERVIEW')
        elif key in {'preview', 'view', 'report', 'edit report'}:
            self._focus_tab('PREVIEW')
        elif key == 'template':
            self._focus_tab('TEMPLATE')
        elif key == 'histogram':
            self._focus_tab('HISTOGRAM')
        elif key == 'lorenz':
            self._focus_tab('REPLAY')
        elif key == 'af analysis':
            self._focus_tab('AF ANALYSIS')
        elif key in {'tend. chart', 'st tendency'}:
            self._focus_tab('ST TENDENCY')
        elif key in {'edit event', 'pace spike', 'add event'}:
            self._focus_tab('EDIT EVENT')
        elif key == 'edit strips':
            self._focus_tab('EDIT STRIPS')
        elif key == 'report table':
            self._focus_tab('REPORT TABLE')
        elif key == 'hrv':
            self._focus_tab('HRV')
        elif key in {'record settings', 'advance tools'}:
            self._focus_tab('RECORDINGS')
        elif key == 'print':
            self._generate_report()
        else:
            self._focus_tab('REPLAY')

    # ----- Build UI -----------------------------------------------------------------------------

    def _find_template_host(self):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "_show_template_card_menu"):
                return parent
            parent = parent.parentWidget()
        window = self.window()
        if window is not None and hasattr(window, "_show_template_card_menu"):
            return window
        return None
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # â”€â”€ Top title bar â”€â”€
        title_bar = QFrame()
        title_bar.setStyleSheet(f"QFrame{{background:{UI_PANEL};border-bottom:1px solid {UI_BORDER};}}")
        title_bar.setFixedHeight(52)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(16, 0, 16, 0)
        tb_layout.setSpacing(14)
        self._mode_badge = QLabel("LIVE" if self._writer else "REVIEW")
        self._mode_badge.setStyleSheet(
            f"background:{'#7A2633' if self._writer else '#124936'};color:{UI_TEXT};"
            f"border:1px solid {UI_BORDER};border-radius:12px;padding:5px 12px;font-size:11px;font-weight:700;"
        )
        tb_layout.addWidget(self._mode_badge)
        app_title = QLabel("Comprehensive ECG Analysis")
        app_title.setStyleSheet(f"color:{UI_TEXT};font-size:18px;font-weight:700;border:none;")
        tb_layout.addWidget(app_title)
        dur_text = self._summary.get('duration_sec', 0)
        dur_h = int(dur_text // 3600)
        dur_m = int((dur_text % 3600) // 60)
        self._dur_label = QLabel(f"{dur_h:02d}h {dur_m:02d}m")
        self._dur_label.setStyleSheet(
            f"color:{UI_TEXT};font-size:13px;font-weight:700;background:{UI_PANEL_ALT};"
            f"padding:7px 12px;border-radius:8px;border:1px solid {UI_BORDER};"
        )
        tb_layout.addWidget(self._dur_label)
        tb_layout.addStretch()
        gen_report_btn = QPushButton("Generate Report")
        gen_report_btn.setStyleSheet(
            f"QPushButton{{background:{UI_ACCENT};color:{UI_TEXT};border:1px solid #61a8ff;border-radius:8px;padding:8px 14px;font-size:12px;font-weight:700;}}"
            f"QPushButton:hover{{background:{UI_ACCENT_HOVER};}}"
        )
        gen_report_btn.setFixedHeight(34)
        gen_report_btn.clicked.connect(self._generate_report)
        tb_layout.addWidget(gen_report_btn)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            f"QPushButton{{background:{UI_PANEL_ALT};color:{UI_TEXT};border:1px solid {UI_BORDER};border-radius:8px;padding:8px 14px;font-size:12px;font-weight:600;}}"
            "QPushButton:hover{background:#2A3D61;}"
        )
        close_btn.setFixedHeight(34)
        close_btn.clicked.connect(self.close)
        tb_layout.addWidget(close_btn)
        main_layout.addWidget(title_bar)

        session_bar = QFrame()
        session_bar.setStyleSheet(f"QFrame{{background:{UI_PANEL_ALT};border-bottom:1px solid {UI_BORDER};}}")
        sb_layout = QHBoxLayout(session_bar)
        sb_layout.setContentsMargins(14, 8, 14, 8)
        sb_layout.setSpacing(10)
        patient_name = self.patient_info.get("patient_name") or self.patient_info.get("name") or "Unknown Patient"
        doctor_name = self.patient_info.get("doctor") or "No referring doctor"
        session_name = os.path.basename(self.session_dir) if self.session_dir else "Active Session"
        self._patient_chip = QLabel(f"Patient: {patient_name}")
        self._patient_chip.setStyleSheet(f"background:#123B2D;color:{UI_TEXT};border:1px solid #206B51;border-radius:14px;padding:6px 12px;font-size:11px;font-weight:700;")
        sb_layout.addWidget(self._patient_chip)
        self._doctor_chip = QLabel(f"Doctor: {doctor_name}")
        self._doctor_chip.setStyleSheet(f"background:{UI_PANEL};color:{UI_MUTED};border:1px solid {UI_BORDER};border-radius:14px;padding:6px 12px;font-size:11px;font-weight:600;")
        sb_layout.addWidget(self._doctor_chip)
        self._session_chip = QLabel(f"Session: {session_name}")
        self._session_chip.setStyleSheet(f"background:{UI_PANEL};color:{UI_MUTED};border:1px solid {UI_BORDER};border-radius:14px;padding:6px 12px;font-size:11px;font-weight:600;")
        sb_layout.addWidget(self._session_chip)
        sb_layout.addStretch()
        self._analysis_state = QLabel("Clinical review mode")
        self._analysis_state.setStyleSheet(f"color:{UI_MUTED};font-size:11px;font-weight:600;border:none;")
        sb_layout.addWidget(self._analysis_state)
        main_layout.addWidget(session_bar)

        action_bar = QFrame()
        action_bar.setStyleSheet(f"QFrame{{background:{UI_PANEL};border-bottom:1px solid {UI_BORDER};}}")
        ab_layout = QHBoxLayout(action_bar)
        ab_layout.setContentsMargins(8, 6, 8, 6)
        ab_layout.setSpacing(6)
        self._action_buttons = {}
        for label in ["Browse", "Search", "Analyse", "View", "Import", "Backup", "Delete"]:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setStyleSheet(_style_btn())
            self._action_buttons[label] = btn
            ab_layout.addWidget(btn)
        ab_layout.addStretch()
        self._filter_buttons = {}
        for label in ["All", "Today", "Yesterday", "This Week", "This Month", "This Year"]:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setStyleSheet(_style_btn(UI_PANEL_ALT, UI_MUTED, "#1A2C49"))
            self._filter_buttons[label] = btn
            ab_layout.addWidget(btn)
        main_layout.addWidget(action_bar)

        # ----- Status bar (if recording) ------------------------------------------------------------
        if self._writer:
            self._status_bar = HolterStatusBar(self, target_hours=self._duration_hours)
            self._status_bar.stop_requested.connect(self._stop_recording)
            main_layout.addWidget(self._status_bar)

        # ----- Summary KPI cards ----------------------------------------------------------------------------

        # ----- Body: tabs fill full width (12-lead grid is inside HolterReplayPanel) -----------------------------------------
        right_frame = QFrame()
        right_frame.setStyleSheet(f"QFrame{{background:{UI_BG};}}")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setUsesScrollButtons(True)

        # Make the tab bar scrollable with the mouse wheel instead of changing tabs
        class TabBarScroller(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Wheel:
                    # In QTabBar, there is a private QScrollArea, but sending the wheel event 
                    # as horizontal scroll to the tabbar doesn't always work cleanly.
                    # Alternatively, if we just want to suppress changing tabs, we can return True,
                    # but to scroll, we need to find the scroll buttons or adjust the scroll offset.
                    # A simple way to trigger the internal scroll is to post a wheel event to the 
                    # tab widget's internal scroll widget, but PyQt doesn't expose it easily.
                    # Wait, if usesScrollButtons is True, QTabBar has two QToolButtons as children.
                    # We can simulate clicks on them based on wheel direction.
                    delta = event.angleDelta().y()
                    if delta == 0:
                        delta = event.angleDelta().x()
                    if delta != 0:
                        buttons = obj.findChildren(QToolButton)
                        if len(buttons) >= 2:
                            # Usually button 0 is left, 1 is right
                            if delta > 0:
                                buttons[0].click()
                                buttons[0].click()
                            else:
                                buttons[1].click()
                                buttons[1].click()
                    return True # Consume event to prevent changing the selected tab
                return super().eventFilter(obj, event)

        self._tab_scroller = TabBarScroller(self)
        self._tabs.tabBar().installEventFilter(self._tab_scroller)

        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background:{UI_BG};
                border:1px solid {UI_BORDER};
                border-top:none;
            }}
            QTabBar::tab {{
                background:{UI_PANEL};
                color:{UI_MUTED};
                border:1px solid {UI_BORDER};
                border-radius:8px;
                padding:9px 14px;
                font-size:11px;
                font-weight:700;
                margin:6px 6px 8px 0;
                min-width:96px;
                text-align:center;
            }}
            QTabBar::tab:selected {{
                color:{UI_TEXT};
                background:{UI_ACCENT};
                border-color:#6EB4FF;
            }}
            QTabBar::tab:hover:!selected {{
                background:#1A2C49;
                color:{UI_TEXT};
            }}
            QGroupBox {{
                border: none;
                border-top: 1px solid {UI_BORDER};
                margin-top: 20px;
                font-weight: bold;
                font-size: 14px;
                color: {UI_TEXT};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }}
        """)

        # â”€â”€ OVERVIEW tab (12-lead scrollable expert view) â”€â”€
        self._expert_panel = HolterExpertReviewPanel()
        self._expert_panel.update_from_metrics(self._metrics_list, self._summary)
        self._expert_panel.seek_requested.connect(self._on_seek_requested)
        self._tabs.addTab(self._expert_panel, "OVERVIEW")

        # Replay
        duration = self._summary.get('duration_sec', self._duration_hours * 3600)
        self._replay_panel = HolterReplayPanel(duration_sec=duration)
        if self._replay_engine:
            self._replay_panel.set_replay_engine(self._replay_engine)
            self._replay_panel.seek_requested.connect(self._on_seek_requested)
        self._replay_panel.section_requested.connect(self._on_workspace_section_requested)
        self._replay_panel.playback_state_changed.connect(self._set_record_browser_enabled)
        self._replay_panel.update_lorenz(self._metrics_list)
        self._replay_panel.update_summary(self._summary)
        self._tabs.addTab(self._replay_panel, "REPLAY")
        self._lorenz_panel = self._replay_panel

        # Beat Templates
        self._template_panel = HolterBeatTemplatePanel()
        if self._replay_engine:
            try:
                self._template_panel.set_replay_engine(self._replay_engine)
            except Exception:
                pass
        self._template_panel.update_from_metrics(self._metrics_list, self._summary)
        self._template_panel.seek_requested.connect(self._on_seek_requested)
        self._tabs.addTab(self._template_panel, "TEMPLATE")

        # Histogram
        self._hist_panel = HolterHistogramPanel()
        self._hist_panel.update_from_metrics(self._metrics_list)
        self._hist_panel.seek_requested.connect(self._on_seek_requested)
        self._tabs.addTab(self._hist_panel, "HISTOGRAM")


        # AF Analysis
        self._af_panel = HolterAFPanel()
        self._af_panel.update_from_metrics(self._metrics_list, duration)
        self._tabs.addTab(self._af_panel, "AF ANALYSIS")

        events = self._build_linked_events()

        # Event timeline
        self._events_panel = HolterEventsPanel()
        self._events_panel.load_events(events, self._summary)
        self._events_panel.seek_requested.connect(self._on_seek_requested)
        self._tabs.addTab(self._events_panel, "EVENTS")

        # ST Tendency
        self._st_panel = HolterSTPanel()
        self._st_panel.update_from_metrics(self._metrics_list)
        self._tabs.addTab(self._st_panel, "ST TENDENCY")

        # Edit Event
        self._edit_event_panel = HolterEditEventPanel()
        self._edit_event_panel.set_session_dir(self.session_dir)
        self._edit_event_panel.load_events(events, self._summary)
        self._edit_event_panel.seek_requested.connect(self._on_seek_requested)
        self._tabs.addTab(self._edit_event_panel, "EDIT EVENT")

        # Edit Strips
        self._edit_strips_panel = HolterEditStripsPanel()
        self._edit_strips_panel.seek_requested.connect(self._on_seek_requested)
        self._edit_strips_panel.load_events(events, self._summary, self._metrics_list)
        self._tabs.addTab(self._edit_strips_panel, "EDIT STRIPS")

        # Report Tendency
        self._report_tendency_panel = HolterSTPanel()
        self._tabs.addTab(self._report_tendency_panel, "REPORT TENDENCY")

        # Report Table
        self._report_table_panel = HolterReportTablePanel()
        self._report_table_panel.update_from_metrics(self._metrics_list)
        self._tabs.addTab(self._report_table_panel, "REPORT TABLE")

        # Expert Review (OVERVIEW tab) already added as first tab above
        # kept here as comment for clarity â€“ see OVERVIEW tab creation at top of tabs section

        # HRV Analysis
        self._hrv_panel = HolterHRVPanel()
        self._hrv_panel.update_hrv(self._metrics_list, self._summary)
        self._tabs.addTab(self._hrv_panel, "HRV")

        # Record browser
        self._record_mgmt_panel = HolterRecordManagementPanel(
            output_dir=_resolve_recordings_dir(self.session_dir)
        )
        self._record_mgmt_panel.session_selected.connect(self.load_completed_session)
        self._tabs.addTab(self._record_mgmt_panel, "RECORDINGS")

        # Report Preview
        scroll_insight = QScrollArea()
        scroll_insight.setWidgetResizable(True)
        scroll_insight.setFrameShape(QFrame.NoFrame)
        scroll_insight.setStyleSheet(f"QScrollArea{{background:{COL_BLACK};border:none;}}")
        self._insight_panel = HolterInsightPanel()
        self._insight_panel.update_text(self.patient_info, self._summary)
        scroll_insight.setWidget(self._insight_panel)
        self._tabs.addTab(scroll_insight, "PREVIEW")
        self._tabs.addTab(QWidget(), "PRINT")
        self._tabs.addTab(QWidget(), "REANALYSIS")
        self._tabs.addTab(QWidget(), "QUIT")

        # Track the last active content tab
        self._last_active_tab_name = "OVERVIEW"
        def _on_tab_changed(index):
            tab_name = self._tabs.tabText(index)
            if tab_name in {"PRINT", "REANALYSIS", "QUIT"}:
                if hasattr(self, "_last_active_tab_name"):
                    self._focus_tab(self._last_active_tab_name)
                if tab_name == "PRINT":
                    QTimer.singleShot(0, self._generate_report)
                elif tab_name == "REANALYSIS":
                    QTimer.singleShot(0, self._confirm_reanalysis)
                elif tab_name == "QUIT":
                    QTimer.singleShot(0, self.close)
            else:
                self._last_active_tab_name = tab_name
                if tab_name == "RECORDINGS":
                    self._tabs.tabBar().setVisible(False)
                else:
                    self._tabs.tabBar().setVisible(True)
        self._tabs.currentChanged.connect(_on_tab_changed)
        # Ensure initial state is correct
        _on_tab_changed(self._tabs.currentIndex())

        right_layout.addWidget(self._tabs)
        self._tabs.currentChanged.connect(
            lambda idx: hasattr(self, '_analysis_state') and self._analysis_state.setText(
                f"Focused view: {self._tabs.tabText(idx)}"
            )
        )
        self._action_buttons["Browse"].clicked.connect(self._open_recordings_folder)
        self._action_buttons["Search"].clicked.connect(self._search_recordings)
        self._action_buttons["Analyse"].clicked.connect(lambda: self._focus_tab("REPLAY"))
        self._action_buttons["View"].clicked.connect(lambda: self._focus_tab("PREVIEW"))
        self._action_buttons["Import"].clicked.connect(self._import_recording)
        self._action_buttons["Backup"].clicked.connect(self._backup_recordings)
        self._action_buttons["Delete"].clicked.connect(self._delete_recording)
        for label, btn in self._filter_buttons.items():
            btn.clicked.connect(lambda _, t=label: self._apply_recordings_filter(t))

        main_layout.addWidget(right_frame, 1)
        if hasattr(self, '_analysis_state'):
            self._analysis_state.setText(f"Focused view: {self._tabs.tabText(self._tabs.currentIndex())}")


    # ----- Callbacks ----------------------------------------------------------------------------

    def _current_replay_window_sec(self) -> float:
        panel = getattr(self, '_replay_panel', None)
        if panel is not None:
            try:
                return float(getattr(panel, '_strip_length_sec', 10.0) or 10.0)
            except Exception:
                pass
        return float(getattr(self, '_strip_length_sec', 10.0) or 10.0)

    def _sync_replay_window_length(self):
        if getattr(self, '_replay_engine', None) and hasattr(self._replay_engine, 'set_window_length'):
            try:
                self._replay_engine.set_window_length(self._current_replay_window_sec())
            except Exception:
                pass

    def _on_seek_requested(self, target_sec: float):
        if self._replay_engine:
            self._sync_replay_window_length()
            self._replay_engine.seek(target_sec)
            try:
                # Use the replay panel's current strip length (changes with paper speed)
                window_sec = self._current_replay_window_sec()
                data = self._replay_engine.get_all_leads_data(window_sec=float(window_sec))
                if hasattr(self, '_wave_panel'):
                    self._wave_panel.set_replay_frame(data)
                self._broadcast_replay_frame(data)
            except Exception:
                pass


    def _broadcast_replay_frame(self, data):
        for panel in [getattr(self, p, None) for p in [
            '_replay_panel', '_lorenz_panel', '_hist_panel', '_af_panel',
            '_st_panel', '_edit_event_panel', '_edit_strips_panel', '_events_panel',
            '_expert_panel', '_template_panel', '_report_tendency_panel', '_hrv_panel'
        ]]:
            if panel and hasattr(panel, 'set_replay_frame'):
                try:
                    panel.set_replay_frame(data)
                except Exception:
                    pass

    def _build_linked_events(self) -> list:
        events = []
        if self._replay_engine:
            try:
                events.extend(self._replay_engine.get_events_list() or [])
            except Exception:
                pass
        for metric in self._metrics_list or []:
            base_t = float(metric.get('t', 0.0) or 0.0)
            for label in metric.get('arrhythmias', []) or []:
                events.append({
                    'timestamp': base_t,
                    'label': str(label),
                    'time_str': _sec_to_hms(base_t),
                })
            for ev in metric.get('classified_events', []) or []:
                t_val = float(ev.get('timestamp', base_t) or base_t)
                events.append({
                    'timestamp': t_val,
                    'label': str(ev.get('label', ev.get('template_label', 'Beat Event'))),
                    'time_str': _sec_to_hms(t_val),
                })

        events.sort(key=lambda e: float(e.get('timestamp', 0.0) or 0.0))
        dedup = []
        seen = set()
        for ev in events:
            key = (round(float(ev.get('timestamp', 0.0) or 0.0), 3), str(ev.get('label', '')))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(ev)
        return dedup

    def _update_live_ui(self):
        if not self._writer or not self._writer.is_running:
            if hasattr(self, '_live_timer'):
                self._live_timer.stop()
            self._load_session()
            self._refresh_ui()
            return
        stats = self._writer.get_live_stats()
        if hasattr(self, '_status_bar'):
            self._status_bar.update_stats(stats['bpm'], stats['arrhythmias'])
        snapshot = None
        if hasattr(self._writer, 'get_live_analysis_snapshot'):
            snapshot = self._writer.get_live_analysis_snapshot(getattr(self, '_last_live_seq', -1))
        if snapshot:
            self._last_live_seq = snapshot.get('seq', self._last_live_seq)
            self._metrics_list = snapshot.get('metrics', [])
            self._summary = snapshot.get('summary', {})
            self._refresh_ui()
        if hasattr(self, '_wave_panel'):
            self._wave_panel.refresh_waveforms()
        # Also refresh _replay_panel lead strips from live data on every tick
        if hasattr(self, '_replay_panel') and not self._replay_engine and self._live_source is not None:
            try:
                raw = getattr(self._live_source, 'data', None)
                if raw is not None and hasattr(raw, '__len__') and len(raw) > 0:
                    import numpy as _np
                    n_samp = max(len(raw[i]) for i in range(min(12, len(raw))))
                    arr = _np.full((12, n_samp), 2048.0)
                    for i in range(min(12, len(raw))):
                        ch = _np.asarray(raw[i], dtype=float)
                        arr[i, :len(ch)] = ch
                    self._replay_panel.set_replay_frame(arr)
            except Exception:
                pass
        if snapshot is None and stats['elapsed'] % 15 < 2:
            self._load_session()
            self._refresh_ui()

    def _refresh_ui(self):
        if hasattr(self, '_summary_cards'):
            self._summary_cards.update_summary(self._summary)
        if hasattr(self, '_insight_panel'):
            self._insight_panel.update_text(self.patient_info, self._summary)
        if hasattr(self, '_overview_panel'):
            self._overview_panel.update_summary(self._summary)
        if hasattr(self, '_expert_panel'):
            self._expert_panel.update_from_metrics(self._metrics_list, self._summary)
        if hasattr(self, '_hrv_panel'):
            self._hrv_panel.update_hrv(self._metrics_list, self._summary)
        if hasattr(self, '_replay_panel'):
            self._replay_panel.update_lorenz(self._metrics_list)
            self._replay_panel.update_summary(self._summary)
            # During live recording (no replay engine), push current live ECG frame
            if not self._replay_engine and self._live_source is not None:
                try:
                    raw = getattr(self._live_source, 'data', None)
                    if raw is not None and hasattr(raw, '__len__') and len(raw) > 0:
                        import numpy as _np
                        # Build a 12-channel array from live_source.data
                        n_samp = max(len(raw[i]) for i in range(min(12, len(raw))))
                        arr = _np.full((12, n_samp), 2048.0)
                        for i in range(min(12, len(raw))):
                            ch = _np.asarray(raw[i], dtype=float)
                            arr[i, :len(ch)] = ch
                        self._replay_panel.set_replay_frame(arr)
                except Exception:
                    pass
        if hasattr(self, '_hist_panel'):
            self._hist_panel.update_from_metrics(self._metrics_list)
        if hasattr(self, '_af_panel'):
            self._af_panel.update_from_metrics(self._metrics_list, self._summary.get('duration_sec', 0))
        if hasattr(self, '_st_panel'):
            self._st_panel.update_from_metrics(self._metrics_list)
        if hasattr(self, '_report_table_panel'):
            self._report_table_panel.update_from_metrics(self._metrics_list)
        events = self._build_linked_events()
        if hasattr(self, '_events_panel'):
            self._events_panel.load_events(events, self._summary)
        if hasattr(self, '_template_panel'):
            self._template_panel.update_from_metrics(self._metrics_list, self._summary)
        if hasattr(self, '_edit_event_panel'):
            self._edit_event_panel.load_events(events, self._summary)
        if hasattr(self, '_edit_strips_panel'):
            self._edit_strips_panel.load_events(events, self._summary, self._metrics_list)
        if hasattr(self, '_wave_panel'):
            self._wave_panel.set_live_source(self._live_source)
        if hasattr(self, '_record_mgmt_panel'):
            self._record_mgmt_panel.output_dir = _resolve_recordings_dir(self.session_dir)
            self._record_mgmt_panel.refresh_records()
        if hasattr(self, '_wave_panel') and self._replay_engine:
            try:
                self._wave_panel.set_replay_engine(self._replay_engine)
            except Exception:
                pass
            self._wave_panel.refresh_waveforms()
        if hasattr(self, '_expert_panel') and self._replay_engine:
            try:
                self._expert_panel.set_replay_frame(self._replay_engine.get_all_leads_data(window_sec=self._current_replay_window_sec()))
            except Exception:
                pass
        if self._replay_engine:
            try:
                self._broadcast_replay_frame(self._replay_engine.get_all_leads_data(window_sec=self._current_replay_window_sec()))
            except Exception:
                pass

        # Update duration label
        dur = self._summary.get('duration_sec', 0)
        dur_h = int(dur // 3600)
        dur_m = int((dur % 3600) // 60)
        if hasattr(self, '_dur_label'):
            self._dur_label.setText(f"{dur_h:02d}h {dur_m:02d}m")
        if hasattr(self, '_patient_chip'):
            patient_name = self.patient_info.get("patient_name") or self.patient_info.get("name") or "Unknown Patient"
            self._patient_chip.setText(f"Patient: {patient_name}")
        if hasattr(self, '_doctor_chip'):
            doctor_name = self.patient_info.get("doctor") or "No referring doctor"
            self._doctor_chip.setText(f"Doctor: {doctor_name}")
        if hasattr(self, '_session_chip'):
            session_name = os.path.basename(self.session_dir) if self.session_dir else "Active Session"
            self._session_chip.setText(f"Session: {session_name}")
        if hasattr(self, '_analysis_state') and hasattr(self, '_tabs'):
            self._analysis_state.setText(f"Focused view: {self._tabs.tabText(self._tabs.currentIndex())}")

    def _finalize_live_writer(self) -> dict:
        summary = {}
        if not self._writer:
            return summary
        try:
            stop_fn = getattr(self._writer, "stop", None)
            if callable(stop_fn):
                summary = stop_fn() or {}
            else:
                close_fn = getattr(self._writer, "close", None)
                if callable(close_fn):
                    summary = close_fn() or {}
        finally:
            self._writer = None
        return summary

    def _stop_recording(self):
        if self._writer:
            summary = self._finalize_live_writer()
            if hasattr(self, '_status_bar') and self._status_bar is not None:
                self._status_bar.setVisible(False)
                if hasattr(self._status_bar, 'cleanup'):
                    self._status_bar.cleanup()
            
            # Show dialog to collect patient info AFTER recording
            dialog = HolterStartDialog(self, patient_info=self.patient_info or {}, output_dir=self.session_dir)
            dialog.setWindowTitle("Save Comprehensive ECG Analysis Recording Details")
            if dialog.exec_() == QDialog.Accepted:
                patient_info, dur, out_dir = dialog.get_result()
                summary['patient_info'] = patient_info
                self.patient_info = patient_info
                import json
                try:
                    with open(os.path.join(summary.get('session_dir', ''), "patient.json"), 'w') as f:
                        json.dump(patient_info, f, indent=4)
                except Exception as e:
                    print(f"Failed to save patient.json: {e}")

            QMessageBox.information(self, "Recording Complete",
                                    f"Comprehensive ECG Analysis recording saved to:\n{summary.get('session_dir', '')}")
            self.load_completed_session(summary.get('session_dir', ''), summary.get('patient_info', {}))
            
            # Auto-generate report when recording is stopped
            self._generate_report()

    def _generate_report(self):
        from PyQt5.QtWidgets import QProgressDialog
        from PyQt5.QtCore import QThread, pyqtSignal
        
        progress = QProgressDialog("Generating Comprehensive ECG Analysis Report. Please wait...", None, 0, 0, self)
        progress.setWindowTitle("Please Wait")
        progress.setWindowModality(Qt.WindowModal)
        progress.setStyleSheet(f"QProgressDialog{{background:{COL_DARK};color:{COL_GREEN};}}")
        progress.setRange(0, 0)
        progress.show()
        
        class ReportWorker(QThread):
            finished = pyqtSignal(str)
            error = pyqtSignal(str)
            
            def __init__(self, session_dir, patient_info, summary):
                super().__init__()
                self.session_dir = session_dir
                self.patient_info = patient_info
                self.summary = summary
                
            def run(self):
                try:
                    from .report_generator import generate_holter_report
                    path = generate_holter_report(
                        session_dir=self.session_dir,
                        patient_info=self.patient_info,
                        summary=self.summary,
                    )
                    self.finished.emit(path)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.error.emit(str(e))
                    
        self._report_worker = ReportWorker(self.session_dir, self.patient_info, self._summary)
        
        def on_finished(path):
            progress.close()
            try:
                from dashboard.history_window import append_history_entry
                h_pat = self.patient_info.copy() if self.patient_info else {}
                if 'patient_name' not in h_pat and 'name' in h_pat:
                    h_pat['patient_name'] = h_pat['name']
                _p = self.parent()
                _uname = getattr(_p, "username", "") if _p is not None else ""
                _full = (getattr(_p, "user_details", {}) or {}).get("full_name") or _uname
                append_history_entry(
                    h_pat, path, report_type="Comprehensive ECG Analysis",
                    username=_uname, owner_full_name=_full
                )
            except Exception as h_err:
                print(f"Failed to append Holter history: {h_err}")
                
            msg = QMessageBox(self)
            msg.setWindowTitle("Report Generated")
            msg.setText(f"Comprehensive ECG Analysis report saved:\n{path}")
            msg.setIcon(QMessageBox.Information)
            msg.setStyleSheet(f"QMessageBox {{ background: {COL_BLACK}; }} QLabel {{ color: {COL_WHITE}; font-size: 12px; }}")
            msg.exec_()
            
        def on_error(err_str):
            progress.close()
            msg = QMessageBox(self)
            msg.setWindowTitle("Report Error")
            msg.setText(f"Could not generate report:\n{err_str}")
            msg.setIcon(QMessageBox.Warning)
            msg.setStyleSheet(f"QMessageBox {{ background: {COL_BLACK}; }} QLabel {{ color: {COL_WHITE}; font-size: 12px; }}")
            msg.exec_()
            
        self._report_worker.finished.connect(on_finished)
        self._report_worker.error.connect(on_error)
        self._report_worker.start()

    def attach_writer(self, writer, session_dir: str = "", patient_info: dict = None):
        self._writer = writer
        self._last_live_seq = -1
        if session_dir:
            self.session_dir = session_dir
        if patient_info is not None:
            self.patient_info = _normalize_patient_info(patient_info)
        if hasattr(self, '_edit_event_panel'):
            self._edit_event_panel.set_session_dir(self.session_dir)
        if writer and not hasattr(self, '_status_bar'):
            self._status_bar = HolterStatusBar(self, target_hours=self._duration_hours)
            self._status_bar.stop_requested.connect(self._stop_recording)
            self.layout().insertWidget(1, self._status_bar)
        if writer and not hasattr(self, '_live_timer'):
            self._live_timer = QTimer(self)
            self._live_timer.timeout.connect(self._update_live_ui)
        if writer and hasattr(self, '_live_timer') and not self._live_timer.isActive():
            self._live_timer.start(1000)
        self._refresh_ui()

    def load_completed_session(self, session_dir: str, patient_info: dict = None):
        self.session_dir = session_dir
        self._last_live_seq = -1
        self.patient_info = _normalize_patient_info(patient_info or {})
        if hasattr(self, '_edit_event_panel'):
            self._edit_event_panel.set_session_dir(self.session_dir)
        if getattr(self, "_replay_engine", None) and self._replay_engine.is_playing():
            self._replay_engine.pause()
        if hasattr(self, "_replay_panel"):
            try:
                self._replay_panel._slider.blockSignals(True)
                self._replay_panel._slider.setValue(self._replay_panel._slider_sec_to_value(0))
                self._replay_panel._slider.blockSignals(False)
                self._replay_panel._pos_label.setText(_sec_to_hms(0))
                self._replay_panel._play_btn.setText("Play")
            except Exception:
                pass
            self._set_record_browser_enabled(True)
        self._writer = None
        self._load_session()
        if hasattr(self, '_record_mgmt_panel'):
            self._record_mgmt_panel.output_dir = _resolve_recordings_dir(session_dir)
            self._record_mgmt_panel.refresh_records()
        if hasattr(self, '_replay_panel') and getattr(self, '_replay_engine', None):
            self._replay_panel.set_replay_engine(self._replay_engine)
            try:
                self._replay_panel.seek_requested.disconnect(self._on_seek_requested)
            except Exception:
                pass
            self._replay_panel.seek_requested.connect(self._on_seek_requested)
        self._refresh_ui()
        if hasattr(self, '_tabs'):
            self._tabs.setCurrentIndex(0)

    def closeEvent(self, event):
        if self._writer:
            try:
                self._finalize_live_writer()
            except Exception:
                pass
        if self._replay_engine:
            try:
                self._replay_engine.close()
            except Exception:
                pass
        super().closeEvent(event)