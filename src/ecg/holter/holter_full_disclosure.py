"""
ecg/holter/holter_full_disclosure.py
=====================================
Full Disclosure ECG viewer - standalone dialog module.

Classes:
  - FullDisclosureOverlay         : Transparent selection-box overlay drawn over the ECG canvas
  - HolterFullDisclosureDialog    : 12-lead scrollable Full Disclosure ECG viewer dialog
"""

import numpy as np
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSpinBox, QScrollBar, QSizePolicy, QApplication, QTabBar,
)
from PyQt5.QtCore import Qt, QEvent, QRect
from PyQt5.QtGui import QPainter, QPen, QColor

try:
    from .theme import (COL_BLACK, COL_DARK, COL_GREEN, COL_GREEN_DRK,
                        TOOL_RULER, TOOL_CALIPER, TOOL_MAGNIFY, TOOL_SELECT)
    from .holter_ui import ECGStripCanvas, MagnifierOverlay
except ImportError:
    from ecg.holter.theme import (COL_BLACK, COL_DARK, COL_GREEN, COL_GREEN_DRK,
                                   TOOL_RULER, TOOL_CALIPER, TOOL_MAGNIFY, TOOL_SELECT)
    from ecg.holter.holter_ui import ECGStripCanvas, MagnifierOverlay


from PyQt5.QtCore import pyqtSignal

class FullDisclosureOverlay(QWidget):
    """Transparent overlay to draw a fixed-width square selection box over the channels."""
    
    double_clicked = pyqtSignal(float, float)  # Emits start_sec, duration_sec

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mouse_enabled = True
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._selection_center_x = 0.0
        self._selection_center_y = 0.0
        self._strip_length_sec = 3.0
        self._pixels_per_sec = 25.0
        self._is_dragging = False
        self.on_selection_made = None
        
    def set_mouse_enabled(self, enabled):
        self._mouse_enabled = enabled
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not enabled)
        self.update()

    def set_pixels_per_sec(self, pps):
        self._pixels_per_sec = max(1.0, pps)
        if self._selection_center_x == 0.0:
            width = self._strip_length_sec * self._pixels_per_sec
            self._selection_center_x = 48.0 + width / 2.0
            self._selection_center_y = width / 2.0
        self.update()

    def set_strip_length(self, length_sec):
        self._strip_length_sec = length_sec
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._selection_center_x = event.pos().x()
            self._selection_center_y = event.pos().y()
            self.update()
            self._emit_selection()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self._selection_center_x = event.pos().x()
            self._selection_center_y = event.pos().y()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self._emit_selection()
            
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            width = self._strip_length_sec * self._pixels_per_sec
            start = self._selection_center_x - width / 2.0
            start = max(48, min(start, self.width() - width))
            start_sec = max(0.0, (start - 48) / self._pixels_per_sec)
            self.double_clicked.emit(start_sec, self._strip_length_sec)

    def _emit_selection(self):
        if self.on_selection_made and self._selection_center_x is not None:
            width = self._strip_length_sec * self._pixels_per_sec
            start = self._selection_center_x - width / 2.0
            start = max(48, min(start, self.width() - width))
            start_sec = max(0.0, (start - 48) / self._pixels_per_sec)
            self.on_selection_made(start_sec, self._strip_length_sec)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self._strip_length_sec * self._pixels_per_sec
        height = 186.0
        start_x = self._selection_center_x - width / 2.0
        start_y = self._selection_center_y - height / 2.0
        start_x = max(48, min(start_x, self.width() - width))
        start_y = max(0, min(start_y, self.height() - height))
        rect = QRect(int(start_x), int(start_y), int(width), int(height))
        painter.setBrush(QColor(0, 120, 215, 80))
        painter.setPen(QPen(QColor(0, 120, 215, 180), 2))
        painter.drawRect(rect)


class HolterFullDisclosureDialog(QDialog):
    """Full Disclosure view: 12-lead scrollable ECG viewer."""

    _GAIN_STEPS  = [(0.5, "5mm/mV"), (1.0, "10mm/mV"), (2.0, "20mm/mV")]
    _SPEED_STEPS = [12.5, 25.0, 50.0]
    _BASE_WIN_SEC = 10.0

    def __init__(self, replay_engine, parent=None):
        super().__init__(parent)
        self._engine      = replay_engine
        self._reader      = replay_engine._reader
        self._paper_speed = 25.0
        self._gain        = 1.0
        self._gain_label  = "10mm/mV"
        self._strip_length = 2.0
        self._current_start = 0.0
        self._window_sec  = self._BASE_WIN_SEC
        self._selected_duration = None
        self._active_tool = TOOL_SELECT
        self._active_tool_btn = None

        self.setWindowTitle("Full Disclosure ECG")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setWindowState(Qt.WindowMaximized)

        screen = QApplication.primaryScreen()
        if screen:
            self.resize(screen.availableGeometry().size())

        self.setStyleSheet(f"QDialog {{ background: {COL_BLACK}; }}")
        self._build_ui()

        # Shared magnifier overlay (covers the whole dialog, used by TOOL_MAGNIFY)
        self._magnifier_overlay = MagnifierOverlay(self)
        self._magnifier_overlay.setGeometry(self.rect())
        self._magnifier_overlay.hide()

        self._update_canvases(0.0)

    def _recalc_window(self):
        idx = self.time_tabs.currentIndex() if hasattr(self, 'time_tabs') else 0
        text = self.time_tabs.tabText(idx) if hasattr(self, 'time_tabs') else "Full disc"
        
        if "Full disc" in text:
            self._window_sec = self._BASE_WIN_SEC * (25.0 / self._paper_speed)
        else:
            # When a specific time tab is selected, the window size remains fixed
            # to that duration, ignoring paper speed changes.
            pass

    def _update_scrollbar_range(self):
        total = max(0.0, self._engine.duration_sec - self._window_sec)
        self.time_scrollbar.setRange(0, max(0, int(total * 100)))
        self.time_scrollbar.setSingleStep(100)
        self.time_scrollbar.setPageStep(int(self._window_sec * 100))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setStyleSheet(f"background: {COL_DARK}; border-bottom: 1px solid {COL_GREEN_DRK};")
        top_bar.setFixedHeight(44)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(14, 4, 14, 4)
        top_layout.setSpacing(12)

        self.lbl_time = QLabel("Time:  00:00:00")
        self.lbl_time.setStyleSheet(f"color: {COL_GREEN}; font-weight: bold; font-size: 15px;")
        top_layout.addWidget(self.lbl_time)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet(f"color: {COL_GREEN_DRK};")
        top_layout.addWidget(sep1)

        lbl_sl = QLabel("Selection window (s):")
        lbl_sl.setStyleSheet("color: #a0c4e8; font-size: 13px;")
        top_layout.addWidget(lbl_sl)

        self.spin_strip = QSpinBox()
        self.spin_strip.setRange(1, 60)
        self.spin_strip.setValue(int(self._strip_length))
        self.spin_strip.setFixedWidth(58)
        self.spin_strip.setStyleSheet(f"""
            QSpinBox {{
                background: #0d1b2a; color: {COL_GREEN};
                border: 1px solid {COL_GREEN_DRK}; border-radius: 4px;
                padding: 3px 6px; font-size: 13px; font-weight: bold;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; background: #162a3a; }}
        """)
        self.spin_strip.valueChanged.connect(self._on_strip_length_changed)
        top_layout.addWidget(self.spin_strip)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet(f"color: {COL_GREEN_DRK};")
        top_layout.addWidget(sep2)

        self.time_tabs = QTabBar()
        self.time_tabs.addTab("Full disc")
        self.time_tabs.addTab("30 Sec")
        self.time_tabs.addTab("1 Min")
        self.time_tabs.addTab("2 Min")
        self.time_tabs.addTab("5 Min")
        self.time_tabs.addTab("10 Min")
        self.time_tabs.addTab("15 Min")
        self.time_tabs.setStyleSheet(f"""
            QTabBar::tab {{
                background: #0d1b2a; color: #a0c4e8;
                border: 1px solid {COL_GREEN_DRK};
                padding: 4px 10px;
                border-radius: 4px;
                margin-right: 4px;
                font-size: 13px; font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background: {COL_GREEN_DRK}; color: {COL_GREEN};
            }}
            QTabBar::tab:hover:!selected {{
                background: #162a3a;
            }}
        """)
        self.time_tabs.currentChanged.connect(self._on_time_tab_changed)
        top_layout.addWidget(self.time_tabs)

        top_layout.addStretch()

        # Real-time display right of time tabs
        self.lbl_real_time = QLabel("Real Time: --:--:--")
        self.lbl_real_time.setStyleSheet(f"color: {COL_GREEN}; font-weight: bold; font-size: 13px;")
        top_layout.addWidget(self.lbl_real_time)
        layout.addWidget(top_bar)

        canvas_frame = QFrame()
        canvas_frame.setStyleSheet(f"background: {COL_BLACK};")
        self.canvas_layout = QVBoxLayout(canvas_frame)
        self.canvas_layout.setContentsMargins(4, 6, 4, 6)
        self.canvas_layout.setSpacing(2)

        self._canvases = []
        leads = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
        for lead in leads:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)

            lbl = QLabel(lead)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet(
                f"color: {COL_GREEN}; font-weight: bold; font-size: 14px;"
                f" background: #0a0f18; border-right: 1px solid {COL_GREEN_DRK};"
                f" padding-right: 4px;"
            )
            lbl.setFixedWidth(44)

            canvas = ECGStripCanvas(canvas_frame, height=60, color=COL_GREEN, lead_name=lead)
            canvas.set_paper_speed(25)
            canvas.set_gain(self._gain)
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            row.addWidget(lbl)
            row.addWidget(canvas, 1)
            self.canvas_layout.addLayout(row)
            self._canvases.append(canvas)

        self.overlay = FullDisclosureOverlay(canvas_frame)
        self.overlay.set_strip_length(self._strip_length)
        self.overlay.on_selection_made = self._on_selection
        self.overlay.double_clicked.connect(self._on_overlay_double_clicked)
        # Enable mouse on overlay initially
        self.overlay.set_mouse_enabled(True)
        canvas_frame.installEventFilter(self)
        self._canvas_frame = canvas_frame
        layout.addWidget(canvas_frame, 1)

        self.time_scrollbar = QScrollBar(Qt.Horizontal)
        self.time_scrollbar.setFixedHeight(12)
        self.time_scrollbar.setStyleSheet(f"""
            QScrollBar:horizontal {{
                background: #0d1b2a; height: 12px; border-radius: 5px; margin: 0 4px;
            }}
            QScrollBar::handle:horizontal {{
                background: {COL_GREEN_DRK}; min-width: 24px; border-radius: 5px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)
        self._update_scrollbar_range()
        self.time_scrollbar.valueChanged.connect(self._on_scrollbar_moved)
        layout.addWidget(self.time_scrollbar)

        bot_bar = QFrame()
        bot_bar.setStyleSheet(f"background: {COL_DARK}; border-top: 1px solid {COL_GREEN_DRK};")
        bot_bar.setFixedHeight(40)
        bot_layout = QHBoxLayout(bot_bar)
        bot_layout.setContentsMargins(14, 5, 14, 5)
        bot_layout.setSpacing(8)

        def _tool_btn(text):
            b = QPushButton(text)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: #0d1b2a; color: {COL_GREEN};
                    border: 1px solid {COL_GREEN_DRK}; padding: 5px 14px;
                    font-size: 13px; font-weight: bold; border-radius: 4px;
                }}
            """)
            return b

        self.btn_gain  = _tool_btn(f"Gain: {self._gain_label}")
        self.btn_speed = _tool_btn(f"Speed: {self._paper_speed}mm/s")
        self.btn_gain.clicked.connect(self._cycle_gain)
        self.btn_speed.clicked.connect(self._cycle_speed)
        bot_layout.addWidget(self.btn_gain)
        bot_layout.addWidget(self.btn_speed)

        sep_tools = QFrame()
        sep_tools.setFrameShape(QFrame.VLine)
        sep_tools.setStyleSheet(f"color: {COL_GREEN_DRK};")
        bot_layout.addWidget(sep_tools)

        def _tool_toggle_btn(text, tool_id):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: #0d1b2a; color: #a0c4e8;
                    border: 1px solid {COL_GREEN_DRK}; padding: 5px 14px;
                    font-size: 13px; font-weight: bold; border-radius: 4px;
                }}
                QPushButton:checked {{
                    background: {COL_GREEN_DRK}; color: {COL_GREEN};
                    border: 1px solid {COL_GREEN};
                }}
                QPushButton:hover:!checked {{ background: #162a3a; }}
            """)
            b.clicked.connect(lambda checked, t=tool_id, btn=b: self._set_tool_mode(t, btn))
            return b

        self.btn_ruler   = _tool_toggle_btn("Measuring Ruler",  TOOL_RULER)
        self.btn_caliper = _tool_toggle_btn("Parallel Ruler",   TOOL_CALIPER)
        self.btn_magnify = _tool_toggle_btn("Magnifying Glass", TOOL_MAGNIFY)
        bot_layout.addWidget(self.btn_ruler)
        bot_layout.addWidget(self.btn_caliper)
        bot_layout.addWidget(self.btn_magnify)

        # Arrhythmia indicator left of Recording label
        self.lbl_arrhythmia = QLabel("")
        self.lbl_arrhythmia.setStyleSheet("color: #ff6b6b; font-weight: bold; font-size: 12px;")
        bot_layout.addStretch()
        bot_layout.addWidget(self.lbl_arrhythmia)
        
        self.lbl_dur = QLabel(f"Recording: {self._engine._sec_to_hms(self._engine.duration_sec)}")
        self.lbl_dur.setStyleSheet("color: #8ab4d0; font-size: 12px;")
        bot_layout.addWidget(self.lbl_dur)
        layout.addWidget(bot_bar)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_magnifier_overlay") and self._magnifier_overlay is not None:
            self._magnifier_overlay.setGeometry(self.rect())

    def set_magnifier_focus(self, source_widget, payload: dict, focus_pos):
        """Called by ECGStripCanvas when magnify tool is active."""
        if hasattr(self, "_magnifier_overlay") and self._magnifier_overlay is not None:
            self._magnifier_overlay.setGeometry(self.rect())
            self._magnifier_overlay.set_focus(source_widget, payload, focus_pos)

    def clear_magnifier_focus(self, source_widget=None):
        """Clear the shared magnifier overlay."""
        if hasattr(self, "_magnifier_overlay") and self._magnifier_overlay is not None:
            self._magnifier_overlay.clear_focus(source_widget)

    def eventFilter(self, obj, event):
        if obj == self._canvas_frame and event.type() == QEvent.Resize:
            self.overlay.resize(obj.size())
            pps = (obj.width() - 48) / max(1.0, self._window_sec)
            self.overlay.set_pixels_per_sec(pps)
        return super().eventFilter(obj, event)

    def _on_strip_length_changed(self, val):
        self._strip_length = float(val)
        self.overlay.set_strip_length(self._strip_length)

    def _cycle_gain(self):
        multipliers = [g[0] for g in self._GAIN_STEPS]
        try:
            idx = multipliers.index(self._gain)
        except ValueError:
            idx = 0
        next_step = self._GAIN_STEPS[(idx + 1) % len(self._GAIN_STEPS)]
        self._gain, self._gain_label = next_step
        self.btn_gain.setText(f"Gain: {self._gain_label}")
        for c in self._canvases:
            c.set_gain(self._gain)
        # Restore selection box when gain is changed
        self._deactivate_tools()

    def _cycle_speed(self):
        try:
            idx = self._SPEED_STEPS.index(self._paper_speed)
        except ValueError:
            idx = 1
        self._paper_speed = self._SPEED_STEPS[(idx + 1) % len(self._SPEED_STEPS)]
        self.btn_speed.setText(f"Speed: {self._paper_speed}mm/s")
        self._recalc_window()
        self._update_scrollbar_range()
        for c in self._canvases:
            c.set_paper_speed(25)
        self._update_canvases(self._current_start)
        # Restore selection box when speed is changed
        self._deactivate_tools()

    def _deactivate_tools(self):
        """Deactivate all measurement tools and restore the selection box overlay."""
        self._active_tool = TOOL_SELECT
        self._active_tool_btn = None
        for btn in [self.btn_ruler, self.btn_caliper, self.btn_magnify]:
            btn.setChecked(False)
        for c in self._canvases:
            if hasattr(c, 'set_mode'):
                c.set_mode(TOOL_SELECT)
        self.clear_magnifier_focus()
        self.overlay.show()

    def _on_scrollbar_moved(self, val):
        start_sec = float(val) / 100.0
        self._update_canvases(start_sec)

    def _on_time_tab_changed(self, index):
        text = self.time_tabs.tabText(index)
        if "30 Sec" in text: self._window_sec = 30.0
        elif "1 Min" in text: self._window_sec = 60.0
        elif "2 Min" in text: self._window_sec = 120.0
        elif "5 Min" in text: self._window_sec = 300.0
        elif "10 Min" in text: self._window_sec = 600.0
        elif "15 Min" in text: self._window_sec = 900.0
        else: self._window_sec = self._BASE_WIN_SEC * (25.0 / self._paper_speed)
        
        # Always enable mouse on overlay for dragging
        self.overlay.set_mouse_enabled(True)
        
        # When "Full disc" is selected, show the last part of the recording
        if "Full disc" in text:
            self._current_start = max(0.0, self._engine.duration_sec - self._window_sec)
        else:
            self._current_start = 0.0
            
        self._update_scrollbar_range()
        self.time_scrollbar.setValue(int(self._current_start * 100))
        self._update_canvases(self._current_start)
        
        self.lbl_dur.setText(f"Recording: {self._engine._sec_to_hms(self._engine.duration_sec)}")

    def _update_time_and_arrhythmia_labels(self, start_sec: float, end_sec: float):
        # Update real-time display
        if hasattr(self._engine, '_reader') and hasattr(self._engine._reader, 'start_time'):
            start_real = datetime.fromtimestamp(self._engine._reader.start_time + start_sec)
            end_real = datetime.fromtimestamp(self._engine._reader.start_time + end_sec)
            self.lbl_real_time.setText(f"Real Time: {start_real.strftime('%H:%M:%S')} - {end_real.strftime('%H:%M:%S')}")
        
        # Update arrhythmia indicator
        arrhythmia_label = ""
        if hasattr(self._engine, '_structured_events'):
            # Find events in current time window
            events_in_window = []
            for ev in self._engine._structured_events:
                ts = float(ev.get('timestamp', 0.0) or 0.0)
                if start_sec <= ts <= end_sec:
                    events_in_window.append(ev)
            if events_in_window:
                # Take earliest event
                earliest = sorted(events_in_window, key=lambda x: float(x.get('timestamp', 0.0) or 0.0))[0]
                ts_real = datetime.fromtimestamp(self._engine._reader.start_time + float(earliest.get('timestamp', 0.0) or 0.0))
                arrhythmia_label = f"Arrhythmia: {earliest.get('label', 'Event')} at {ts_real.strftime('%H:%M:%S')}"
        self.lbl_arrhythmia.setText(arrhythmia_label)

    def _update_canvases(self, start_sec: float):
        eff_dur = self._engine.duration_sec
        start_sec = max(0.0, min(start_sec, max(0.0, eff_dur - self._window_sec)))
        self._current_start = start_sec
        end_sec = start_sec + self._window_sec

        self.lbl_time.setText(f"Time:  {self._engine._sec_to_hms(start_sec)}")
        self._update_time_and_arrhythmia_labels(start_sec, end_sec)

        read_end_sec = min(end_sec, eff_dur)
        
        # Read data efficiently
        data = self._reader.read_range(start_sec, read_end_sec)
        expected_len = int(self._window_sec * self._engine.fs)
        
        # Get beat annotations for this window
        beat_annotations = []
        try:
            for m in self._engine._metrics:
                all_beats = m.get('all_beats', [])
                if not all_beats:
                    continue
                for beat in all_beats:
                    ts = float(beat.get('timestamp', 0.0))
                    if start_sec <= ts <= end_sec:
                        beat_annotations.append({
                            'timestamp': ts,
                            'label': str(beat.get('label', 'N'))
                        })
            beat_annotations.sort(key=lambda b: b['timestamp'])
        except Exception as e:
            print(f"[Full Disclosure] Error loading beat annotations: {e}")
        
        # Generate time array for ECG strips
        x = np.linspace(0, self._window_sec, expected_len)

        # Optimization: Process data in parallel using numpy vectorization
        for i, c in enumerate(self._canvases):
            if i < data.shape[0] and data.shape[1] > 0:
                d_i = data[i]
                # Use numpy slicing instead of padding for better performance
                if len(d_i) != expected_len:
                    if len(d_i) > expected_len:
                        d_i = d_i[:expected_len]
                    else:
                        # Create padded array more efficiently
                        padded = np.empty(expected_len, dtype=d_i.dtype)
                        padded[:len(d_i)] = d_i
                        padded[len(d_i):] = d_i[-1] if len(d_i) > 0 else 0
                        d_i = padded
                # Convert to float32 for faster rendering and pass beat annotations
                c.set_data(x, np.asarray(d_i, dtype=np.float32), beat_annotations=beat_annotations, start_sec=start_sec)
            else:
                c.set_data(x, np.zeros(expected_len, dtype=np.float32), beat_annotations=beat_annotations, start_sec=start_sec)

    def _set_tool_mode(self, tool_id: str, btn: "QPushButton"):
        """Activate a tool (ruler/caliper/magnify) on all canvases, or deactivate if already active."""
        tool_btns = [self.btn_ruler, self.btn_caliper, self.btn_magnify]
        if self._active_tool == tool_id:
            # Toggle off — return to select mode
            self._active_tool = TOOL_SELECT
            self._active_tool_btn = None
            for b in tool_btns:
                b.setChecked(False)
        else:
            self._active_tool = tool_id
            self._active_tool_btn = btn
            for b in tool_btns:
                b.setChecked(b is btn)
        for c in self._canvases:
            if hasattr(c, 'set_mode'):
                c.set_mode(self._active_tool)
        # Show/hide the strip selection overlay based on tool
        # When a measurement tool is active, hide the selection box
        if self._active_tool == TOOL_SELECT:
            self.overlay.show()
        else:
            self.overlay.hide()
            self.clear_magnifier_focus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            event.ignore()
        else:
            super().keyPressEvent(event)

    def _on_selection(self, start_offset, duration):
        sel_abs = self._current_start + start_offset
        print(f"[Full Disclosure] Strip selected: {duration:.1f}s at {sel_abs:.2f}s")
        
    def _on_overlay_double_clicked(self, start_sec, duration):
        """Open expanded view for the selected time range."""
        dialog = ExpandedViewDialog(self._engine, self._current_start + start_sec, duration, self)
        dialog.exec_()


class ExpandedViewDialog(QDialog):
    """Expanded 12-lead view for selected time range."""
    
    def __init__(self, replay_engine, start_sec: float, duration: float, parent=None):
        super().__init__(parent)
        self._engine = replay_engine
        self._reader = replay_engine._reader
        self._start_sec = start_sec
        self._duration = duration
        
        self.setWindowTitle("Expanded View")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setWindowState(Qt.WindowMaximized)
        
        screen = QApplication.primaryScreen()
        if screen:
            self.resize(screen.availableGeometry().size())
            
        self.setStyleSheet(f"QDialog {{ background: {COL_BLACK}; }}")
        
        self._build_ui()
        self._update_canvases()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        
        top_bar = QFrame()
        top_bar.setStyleSheet(f"background: {COL_DARK}; border-bottom: 1px solid {COL_GREEN_DRK}; border-radius: 4px;")
        top_bar.setFixedHeight(44)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(14, 4, 14, 4)
        top_layout.setSpacing(12)
        
        start_real = datetime.fromtimestamp(self._engine._reader.start_time + self._start_sec)
        end_real = datetime.fromtimestamp(self._engine._reader.start_time + self._start_sec + self._duration)
        self.lbl_time = QLabel(f"Time Range: {start_real.strftime('%H:%M:%S')} - {end_real.strftime('%H:%M:%S')}")
        self.lbl_time.setStyleSheet(f"color: {COL_GREEN}; font-weight: bold; font-size: 15px;")
        top_layout.addWidget(self.lbl_time)
        
        top_layout.addStretch()
        
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("""
            QPushButton {
                background: #0d1b2a; color: #a0c4e8;
                border: 1px solid #2a5a6d; padding: 5px 14px;
                font-size: 13px; font-weight: bold; border-radius: 4px;
            }
            QPushButton:hover {
                background: #162a3a;
            }
        """)
        btn_close.clicked.connect(self.accept)
        top_layout.addWidget(btn_close)
        
        layout.addWidget(top_bar)
        
        canvas_frame = QFrame()
        canvas_frame.setStyleSheet(f"background: {COL_BLACK}; border: 1px solid {COL_GREEN_DRK}; border-radius: 4px;")
        self.canvas_layout = QVBoxLayout(canvas_frame)
        self.canvas_layout.setContentsMargins(8, 12, 8, 12)
        self.canvas_layout.setSpacing(6)
        
        self._canvases = []
        leads = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
        for lead in leads:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            
            lbl = QLabel(lead)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet(
                f"color: {COL_GREEN}; font-weight: bold; font-size: 16px;"
                f" background: #0a0f18; border-right: 1px solid {COL_GREEN_DRK};"
                f" padding-right: 8px; padding-top: 4px; padding-bottom:4px;"
            )
            lbl.setFixedWidth(52)
            
            canvas = ECGStripCanvas(canvas_frame, height=80, color=COL_GREEN, lead_name=lead)
            canvas.set_paper_speed(25)
            canvas.set_gain(2.0)  # Higher gain for expanded view
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            row.addWidget(lbl)
            row.addWidget(canvas, 1)
            self.canvas_layout.addLayout(row)
            self._canvases.append(canvas)
            
        layout.addWidget(canvas_frame, 1)
        
    def _update_canvases(self):
        end_sec = min(self._start_sec + self._duration, self._engine.duration_sec)
        data = self._reader.read_range(self._start_sec, end_sec)
        expected_len = int(self._duration * self._engine.fs)
        
        # Get beat annotations for this window
        beat_annotations = []
        try:
            for m in self._engine._metrics:
                all_beats = m.get('all_beats', [])
                if not all_beats:
                    continue
                for beat in all_beats:
                    ts = float(beat.get('timestamp', 0.0))
                    if self._start_sec <= ts <= end_sec:
                        beat_annotations.append({
                            'timestamp': ts,
                            'label': str(beat.get('label', 'N'))
                        })
            beat_annotations.sort(key=lambda b: b['timestamp'])
        except Exception as e:
            print(f"[Expanded View] Error loading beat annotations: {e}")
        
        # Generate time array for ECG strips
        x = np.linspace(0, self._duration, expected_len)
        
        # Optimization: Process data efficiently with numpy vectorization
        for i, c in enumerate(self._canvases):
            if i < data.shape[0] and data.shape[1] > 0:
                d_i = data[i]
                # Use numpy slicing instead of padding for better performance
                if len(d_i) != expected_len:
                    if len(d_i) > expected_len:
                        d_i = d_i[:expected_len]
                    else:
                        # Create padded array more efficiently
                        padded = np.empty(expected_len, dtype=d_i.dtype)
                        padded[:len(d_i)] = d_i
                        padded[len(d_i):] = d_i[-1] if len(d_i) > 0 else 0
                        d_i = padded
                # Convert to float32 for faster rendering and pass beat annotations
                c.set_data(x, np.asarray(d_i, dtype=np.float32), beat_annotations=beat_annotations, start_sec=self._start_sec)
            else:
                c.set_data(x, np.zeros(expected_len, dtype=np.float32), beat_annotations=beat_annotations, start_sec=self._start_sec)
