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
    from .theme import (COL_BLACK, COL_DARK, COL_GREEN, COL_GREEN_DRK, COL_WHITE, COL_GRID_MAJOR,
                        TOOL_RULER, TOOL_CALIPER, TOOL_MAGNIFY, TOOL_SELECT)
    from .holter_ui import ECGStripCanvas, MagnifierOverlay
except ImportError:
    from ecg.holter.theme import (COL_BLACK, COL_DARK, COL_GREEN, COL_GREEN_DRK, COL_WHITE, COL_GRID_MAJOR,
                                   TOOL_RULER, TOOL_CALIPER, TOOL_MAGNIFY, TOOL_SELECT)
    from ecg.holter.holter_ui import ECGStripCanvas, MagnifierOverlay


from PyQt5.QtCore import pyqtSignal

# TODO: Expanded view / Overlay double click handler - Disabled for now
# def _on_overlay_double_clicked(self, start_sec, duration):
#     """Open expanded view for the selected time range."""
#     # TODO: Expanded view disabled for now
#     # dialog = ExpandedViewDialog(self._engine, self._current_start + start_sec, duration, self)
#     # dialog.exec_()
#     pass

# ============================================================================
# SELECTION BOX OVERLAY - COMMENTED OUT (Not needed for now)
# ============================================================================
# class FullDisclosureOverlay(QWidget):
#     """Transparent overlay to draw a fixed-width square selection box over the channels."""
#     
#     double_clicked = pyqtSignal(float, float)  # Emits start_sec, duration_sec
# 
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self._mouse_enabled = True
#         self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
#         self._selection_center_x = 0.0
#         self._selection_center_y = 0.0
#         self._strip_length_sec = 3.0
#         self._pixels_per_sec = 25.0
#         self._is_dragging = False
#         self.on_selection_made = None
#         
#     def set_mouse_enabled(self, enabled):
#         self._mouse_enabled = enabled
#         self.setAttribute(Qt.WA_TransparentForMouseEvents, not enabled)
#         self.update()
# 
#     def set_pixels_per_sec(self, pps):
#         self._pixels_per_sec = max(1.0, pps)
#         if self._selection_center_x == 0.0:
#             width = self._strip_length_sec * self._pixels_per_sec
#             self._selection_center_x = 48.0 + width / 2.0
#             self._selection_center_y = width / 2.0
#         self.update()
# 
#     def set_strip_length(self, length_sec):
#         self._strip_length_sec = length_sec
#         self.update()
# 
#     def mousePressEvent(self, event):
#         if event.button() == Qt.LeftButton:
#             self._is_dragging = True
#             self._selection_center_x = event.pos().x()
#             self._selection_center_y = event.pos().y()
#             self.update()
#             self._emit_selection()
# 
#     def mouseMoveEvent(self, event):
#         if self._is_dragging:
#             self._selection_center_x = event.pos().x()
#             self._selection_center_y = event.pos().y()
#             self.update()
# 
#     def mouseReleaseEvent(self, event):
#         if event.button() == Qt.LeftButton:
#             self._is_dragging = False
#             self._emit_selection()
#             
#     def mouseDoubleClickEvent(self, event):
#         if event.button() == Qt.LeftButton:
#             width = self._strip_length_sec * self._pixels_per_sec
#             start = self._selection_center_x - width / 2.0
#             start = max(48, min(start, self.width() - width))
#             start_sec = max(0.0, (start - 48) / self._pixels_per_sec)
#             self.double_clicked.emit(start_sec, self._strip_length_sec)
# 
#     def _emit_selection(self):
#         if self.on_selection_made and self._selection_center_x is not None:
#             width = self._strip_length_sec * self._pixels_per_sec
#             start = self._selection_center_x - width / 2.0
#             start = max(48, min(start, self.width() - width))
#             start_sec = max(0.0, (start - 48) / self._pixels_per_sec)
#             self.on_selection_made(start_sec, self._strip_length_sec)
# 
#     def paintEvent(self, event):
#         painter = QPainter(self)
#         painter.setRenderHint(QPainter.Antialiasing)
#         width = self._strip_length_sec * self._pixels_per_sec
#         height = 186.0
#         start_x = self._selection_center_x - width / 2.0
#         start_y = self._selection_center_y - height / 2.0
#         start_x = max(48, min(start_x, self.width() - width))
#         start_y = max(0, min(start_y, self.height() - height))
#         rect = QRect(int(start_x), int(start_y), int(width), int(height))
#         painter.setBrush(QColor(0, 120, 215, 80))
#         painter.setPen(QPen(QColor(0, 120, 215, 180), 2))
#         painter.drawRect(rect)
# ============================================================================


class VerticalLineOverlay(QWidget):
    """Transparent overlay to draw vertical lines on user click/drag across all leads."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # Let clicks pass through
        self._line_positions = []  # List of X positions for multiple vertical lines
        self.setStyleSheet("background: transparent;")
        
    def set_line_position(self, x: int):
        """Set a single X position for the vertical line (backward compatibility)."""
        self._line_positions = [x] if x is not None else []
        self.update()
    
    def set_line_positions(self, positions: list):
        """Set multiple X positions for vertical lines (for drag selection)."""
        self._line_positions = positions if positions else []
        self.update()
        
    def clear_line(self):
        """Clear all vertical lines."""
        self._line_positions = []
        self.update()
        
    def paintEvent(self, event):
        """Draw vertical yellow lines at all set positions."""
        if not self._line_positions:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw continuous vertical yellow lines starting from y=22 (below the N label box)
        # This prevents the line from overlapping with the N label text and square box
        painter.setPen(QPen(QColor("#FFFF00"), 2))
        
        for line_x in self._line_positions:
            if line_x is not None:
                painter.drawLine(line_x, 22, line_x, self.height())


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
        
        # Drag selection state
        self._drag_start_x = None
        self._drag_current_x = None
        self._is_dragging = False
        self._drag_start_timestamp = None
        
        self._detected_r_peaks = []

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

        # TODO: Selection window option disabled for now
        # lbl_sl = QLabel("Selection window (s):")
        # lbl_sl.setStyleSheet("color: #a0c4e8; font-size: 13px;")
        # top_layout.addWidget(lbl_sl)
        # 
        # self.spin_strip = QSpinBox()
        # self.spin_strip.setRange(1, 60)
        # self.spin_strip.setValue(int(self._strip_length))
        # self.spin_strip.setFixedWidth(58)
        # self.spin_strip.setStyleSheet(f"""
        #     QSpinBox {{
        #         background: #0d1b2a; color: {COL_GREEN};
        #         border: 1px solid {COL_GREEN_DRK}; border-radius: 4px;
        #         padding: 3px 6px; font-size: 13px; font-weight: bold;
        #     }}
        #     QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; background: #162a3a; }}
        # """)
        # self.spin_strip.valueChanged.connect(self._on_strip_length_changed)
        # top_layout.addWidget(self.spin_strip)
        # 
        # sep2 = QFrame()
        # sep2.setFrameShape(QFrame.VLine)
        # sep2.setStyleSheet(f"color: {COL_GREEN_DRK};")
        # top_layout.addWidget(sep2)

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
            
            # Install event filter on each canvas to catch mouse clicks
            canvas.installEventFilter(self)

            row.addWidget(lbl)
            row.addWidget(canvas, 1)
            self.canvas_layout.addLayout(row)
            self._canvases.append(canvas)

        # TODO: Selection box overlay disabled for now
        # self.overlay = FullDisclosureOverlay(canvas_frame)
        # self.overlay.set_strip_length(self._strip_length)
        # self.overlay.on_selection_made = self._on_selection
        # self.overlay.double_clicked.connect(self._on_overlay_double_clicked)
        # # Enable mouse on overlay initially
        # self.overlay.set_mouse_enabled(True)
        
        # Add vertical line overlay for click tracking (spans all leads continuously)
        self._vertical_line_overlay = VerticalLineOverlay(canvas_frame)
        self._vertical_line_overlay.setGeometry(canvas_frame.rect())
        self._vertical_line_overlay.raise_()  # Make sure it's on top
        self._vertical_line_overlay.show()
        self._clicked_vertical_line_x = None  # Track clicked X position
        
        # Install event filter BEFORE adding canvas_frame to layout
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
        # Handle resize events for canvas_frame
        if obj == self._canvas_frame and event.type() == QEvent.Resize:
            # Resize the vertical line overlay to match the canvas frame
            if hasattr(self, '_vertical_line_overlay'):
                self._vertical_line_overlay.setGeometry(obj.rect())
        
        # Handle RIGHT CLICK - show context menu for beat labeling
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
            if obj == self._canvas_frame or obj in self._canvases:
                # Get click position
                if obj in self._canvases:
                    click_pos_local = event.pos()
                    click_pos_global = obj.mapTo(self._canvas_frame, click_pos_local)
                    click_x = click_pos_global.x()
                else:
                    click_x = event.pos().x()
                
                # Show context menu
                self._show_beat_context_menu(click_x, event.globalPos())
                return True  # Consume the event
        
        # Handle mouse press - start drag selection
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            # Check if the event is from a canvas or the canvas_frame
            if obj == self._canvas_frame or obj in self._canvases:
                # Get click position relative to canvas_frame
                if obj in self._canvases:
                    click_pos_local = event.pos()
                    click_pos_global = obj.mapTo(self._canvas_frame, click_pos_local)
                    click_x = click_pos_global.x()
                else:
                    click_x = event.pos().x()
                
                # Start drag selection
                self._drag_start_x = click_x
                self._drag_current_x = click_x
                self._is_dragging = False
                
                self._clicked_vertical_line_x = click_x
                
                # Update the overlay to draw the line
                if hasattr(self, '_vertical_line_overlay'):
                    self._vertical_line_overlay.set_line_position(click_x)
                
                # Convert click_x (global) to local Lead I coordinate
                lead_i_canvas = None
                for c in self._canvases:
                    if c.lead_name == 'I':
                        lead_i_canvas = c
                        break
                
                clicked_timestamp = None
                clicked_label = None
                if lead_i_canvas:
                    from PyQt5.QtCore import QPoint
                    click_x_local = lead_i_canvas.mapFrom(self._canvas_frame, QPoint(click_x, 0)).x()
                    click_x_local = max(0, min(lead_i_canvas.width(), click_x_local))
                    
                    lead_i_canvas._check_and_store_clicked_beat(click_x_local)
                    clicked_timestamp = lead_i_canvas._clicked_beat_timestamp
                    clicked_label = lead_i_canvas._clicked_beat_label
                
                # Store the start beat
                self._drag_start_timestamp = clicked_timestamp
                
                # Propagate to all canvases for single beat display
                for canvas in self._canvases:
                    if clicked_timestamp is not None:
                        if lead_i_canvas and hasattr(lead_i_canvas, '_clicked_beat_x_pos'):
                            canvas._clicked_beat_x_pos = lead_i_canvas._clicked_beat_x_pos
                        else:
                            canvas._clicked_beat_x_pos = click_x
                        canvas._clicked_beat_timestamp = clicked_timestamp
                        canvas._clicked_beat_label = clicked_label
                        # Initialize selected beats list
                        canvas._selected_beats = [clicked_timestamp] if clicked_timestamp else []
                    else:
                        canvas._clicked_beat_x_pos = None
                        canvas._clicked_beat_timestamp = None
                        canvas._clicked_beat_label = None
                        canvas._selected_beats = []
                    canvas.update()
                
                # Update overlay with single line position
                if hasattr(self, '_vertical_line_overlay'):
                    if clicked_timestamp is not None and lead_i_canvas and hasattr(lead_i_canvas, '_clicked_beat_x_pos') and lead_i_canvas._clicked_beat_x_pos is not None:
                        from PyQt5.QtCore import QPoint
                        beat_x_global = lead_i_canvas.mapTo(self._canvas_frame, QPoint(lead_i_canvas._clicked_beat_x_pos, 0)).x()
                        self._vertical_line_overlay.set_line_position(beat_x_global)
                    else:
                        self._vertical_line_overlay.set_line_position(click_x)
        
        # Handle mouse move - drag to select multiple beats
        elif event.type() == QEvent.MouseMove:
            if hasattr(self, '_drag_start_x') and self._drag_start_x is not None:
                # Get current drag position
                if obj in self._canvases:
                    drag_pos_local = event.pos()
                    drag_pos_global = obj.mapTo(self._canvas_frame, drag_pos_local)
                    drag_x = drag_pos_global.x()
                else:
                    drag_x = event.pos().x()
                
                # Check if user has moved enough to start drag (5 pixel threshold)
                if not self._is_dragging and abs(drag_x - self._drag_start_x) > 5:
                    self._is_dragging = True
                
                if self._is_dragging:
                    self._drag_current_x = drag_x
                    
                    # Find all beats between start and current position
                    start_x = min(self._drag_start_x, drag_x)
                    end_x = max(self._drag_start_x, drag_x)
                    
                    # Get all beats in range from Lead I by mapping to local coords
                    selected_beats = []
                    lead_i_canvas = None
                    for c in self._canvases:
                        if c.lead_name == 'I':
                            lead_i_canvas = c
                            break
                    
                    if lead_i_canvas:
                        from PyQt5.QtCore import QPoint
                        w_i = lead_i_canvas.width()
                        start_x_local = lead_i_canvas.mapFrom(self._canvas_frame, QPoint(start_x, 0)).x()
                        end_x_local = lead_i_canvas.mapFrom(self._canvas_frame, QPoint(end_x, 0)).x()
                        start_x_local = max(0, min(w_i, start_x_local))
                        end_x_local = max(0, min(w_i, end_x_local))
                        selected_beats = lead_i_canvas._find_beats_in_range(start_x_local, end_x_local)
                    
                    # Propagate selected beats to all canvases
                    for canvas in self._canvases:
                        canvas._selected_beats = selected_beats
                        canvas.update()
                    
                    # Update vertical line overlay with multiple line positions
                    if hasattr(self, '_vertical_line_overlay'):
                        line_positions = []
                        if selected_beats and lead_i_canvas:
                            w = lead_i_canvas.width()
                            start_sec = lead_i_canvas._start_sec
                            data_len = len(lead_i_canvas._data) if hasattr(lead_i_canvas, '_data') else 0
                            if w > 0 and data_len > 0:
                                end_sec = start_sec + data_len / lead_i_canvas._fs
                                for beat_ts in selected_beats:
                                    if start_sec <= beat_ts <= end_sec:
                                        pct = (beat_ts - start_sec) / (end_sec - start_sec) if (end_sec - start_sec) > 0 else 0.0
                                        beat_x = int(pct * w)
                                        from PyQt5.QtCore import QPoint
                                        beat_x_global = lead_i_canvas.mapTo(self._canvas_frame, QPoint(beat_x, 0)).x()
                                        line_positions.append(beat_x_global)
                        self._vertical_line_overlay.set_line_positions(line_positions)
        
        # Handle mouse release - end drag selection
        elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if hasattr(self, '_drag_start_x'):
                self._drag_start_x = None
                self._drag_current_x = None
                self._is_dragging = False
                
        return super().eventFilter(obj, event)

    # TODO: Strip length change handler disabled for now
    # def _on_strip_length_changed(self, val):
    #     self._strip_length = float(val)
    #     self.overlay.set_strip_length(self._strip_length)

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
            c.update()  # Force repaint with new gain
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
        # TODO: Overlay show/hide disabled for now
        # self.overlay.show()

    def _show_beat_context_menu(self, click_x: int, global_pos):
        """Show right-click context menu for beat labeling."""
        from PyQt5.QtWidgets import QMenu, QAction
        
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COL_DARK};
                color: {COL_WHITE};
                border: 1px solid {COL_GRID_MAJOR};
            }}
            QMenu::item:selected {{
                background-color: {COL_GRID_MAJOR};
            }}
        """)
        
        # Beat type options with colors
        beat_options = [
            ("Normal(N)", "N", "#00FF00"),  # Green
            ("Atrial Premature(S)", "S", "#00FFFF"),  # Cyan
            ("Ventricular Premature(V)", "V", "#FF3333"),  # Red
            ("Paced(P)", "P", "#FF00FF"),  # Magenta
            ("Atrial Fibrillation(AF)", "AF", "#FF00FF"),  # Magenta
            ("Artifact(X)", "X", "#0000FF"),  # Blue
            ("Other", "Other", "#FFFF00"),  # Yellow
        ]
        
        for label, code, color in beat_options:
            action = QAction(label, self)
            action.triggered.connect(lambda checked, c=code, x=click_x: self._label_beat(x, c))
            menu.addAction(action)
        
        menu.addSeparator()
        
        # Additional options
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self._delete_beat_at_position(click_x))
        menu.addAction(delete_action)
        
        menu.addSeparator()
        
        # Other options
        add_strip_action = QAction("Add/Print Strip(space)", self)
        menu.addAction(add_strip_action)
        
        interval_action = QAction("Interval reanalysis", self)
        menu.addAction(interval_action)
        
        add_afib_action = QAction("Add AFib Evt.", self)
        menu.addAction(add_afib_action)
        
        add_af_action = QAction("Add AF Evt.", self)
        menu.addAction(add_af_action)
        
        menu.addSeparator()
        
        amplitude_action = QAction("Amplitude Ruler", self)
        menu.addAction(amplitude_action)
        
        parallel_action = QAction("Parallel Ruler", self)
        menu.addAction(parallel_action)
        
        menu.addSeparator()
        
        set_start_action = QAction("Set as starting", self)
        menu.addAction(set_start_action)
        
        set_end_action = QAction("Set as ending", self)
        menu.addAction(set_end_action)
        
        menu.addSeparator()
        
        equal_interval_action = QAction("equal interval bulkinsert beats", self)
        menu.addAction(equal_interval_action)
        
        menu.addSeparator()
        
        set_max_hr_action = QAction("Set as max HR", self)
        menu.addAction(set_max_hr_action)
        
        set_min_hr_action = QAction("Set as min HR", self)
        menu.addAction(set_min_hr_action)
        
        set_sinus_max_action = QAction("Set as Sinus Max. HR", self)
        menu.addAction(set_sinus_max_action)
        
        set_sinus_min_action = QAction("Set as Sinus Min. HR", self)
        menu.addAction(set_sinus_min_action)
        
        # Show menu at cursor position
        menu.exec_(global_pos)
    
    def _label_beat(self, click_x: int, label: str):
        """Label the beat at click_x with the given label."""
        # Define color mapping for beat types
        label_colors = {
            "N": "#00FF00",      # Normal - Green
            "S": "#00FFFF",      # Atrial Premature - Cyan
            "V": "#FF3333",      # Ventricular Premature - Red
            "P": "#FF00FF",      # Paced - Magenta
            "AF": "#FF00FF",     # Atrial Fibrillation - Magenta
            "X": "#0000FF",      # Artifact - Blue
            "Other": "#FFFF00"   # Other - Yellow
        }
        
        # Find the beat at this position and update its label
        for canvas in self._canvases:
            if canvas.lead_name == 'I':
                from PyQt5.QtCore import QPoint
                local_x = canvas.mapFrom(self._canvas_frame, QPoint(click_x, 0)).x()
                local_x = max(0, min(canvas.width(), local_x))
                # Get beat timestamp at this position
                w = canvas.width()
                if w > 0:
                    pct = local_x / float(w)
                    start_sec = canvas._start_sec
                    data_len = len(canvas._data) if hasattr(canvas, '_data') else 0
                    if data_len > 0:
                        end_sec = start_sec + data_len / canvas._fs
                        click_ts = start_sec + pct * (end_sec - start_sec)
                        
                        # --- Snap click_ts to nearest detected R-peak ---
                        snapped_ts = click_ts
                        snap_tolerance_sec = 0.15  # 150ms tolerance
                        
                        # Try snapping to parent dialog's detected peaks first
                        if hasattr(self, '_detected_r_peaks') and self._detected_r_peaks:
                            best_dist = snap_tolerance_sec
                            for peak_ts in self._detected_r_peaks:
                                dist = abs(peak_ts - click_ts)
                                if dist < best_dist:
                                    best_dist = dist
                                    snapped_ts = peak_ts
                        
                        # Ensure _beat_annotations list exists
                        if not hasattr(canvas, '_beat_annotations') or canvas._beat_annotations is None:
                            canvas._beat_annotations = []
                        
                        # Try to find existing annotation within tolerance
                        found = False
                        for beat in canvas._beat_annotations:
                            if abs(beat['timestamp'] - snapped_ts) < snap_tolerance_sec:
                                beat['label'] = label
                                beat['color'] = label_colors.get(label, "#FFFF00")
                                print(f"[Full Disclosure] Updated beat at {snapped_ts:.3f}s as '{label}'")
                                found = True
                                break
                        
                        # If no existing annotation found, create one at the snapped R-peak position
                        if not found:
                            new_beat = {
                                'timestamp': snapped_ts,
                                'label': label,
                                'color': label_colors.get(label, "#FFFF00")
                            }
                            canvas._beat_annotations.append(new_beat)
                            # Keep sorted by timestamp for consistent rendering
                            canvas._beat_annotations.sort(key=lambda b: b['timestamp'])
                            print(f"[Full Disclosure] Created new beat annotation at {snapped_ts:.3f}s as '{label}'")
                        
                        # Refresh all canvases to show the updated color
                        for c in self._canvases:
                            c.update()
                break
    
    def _delete_beat_at_position(self, click_x: int):
        """Delete the beat at the clicked position."""
        for canvas in self._canvases:
            if canvas.lead_name == 'I':
                from PyQt5.QtCore import QPoint
                local_x = canvas.mapFrom(self._canvas_frame, QPoint(click_x, 0)).x()
                local_x = max(0, min(canvas.width(), local_x))
                w = canvas.width()
                if w > 0 and hasattr(canvas, '_beat_annotations'):
                    pct = local_x / float(w)
                    start_sec = canvas._start_sec
                    data_len = len(canvas._data) if hasattr(canvas, '_data') else 0
                    if data_len > 0:
                        end_sec = start_sec + data_len / canvas._fs
                        click_ts = start_sec + pct * (end_sec - start_sec)
                        
                        # Find and remove beat
                        canvas._beat_annotations[:] = [
                            b for b in canvas._beat_annotations 
                            if abs(b['timestamp'] - click_ts) >= 0.1
                        ]
                        
                        # Refresh all canvases
                        for c in self._canvases:
                            c.update()
                break

    def _on_scrollbar_moved(self, val):
        start_sec = float(val) / 100.0
        
        # Clear any selected beats and vertical lines when scrolling
        self._drag_start_x = None
        self._drag_current_x = None
        self._is_dragging = False
        self._drag_start_timestamp = None
        
        # Clear vertical lines from overlay
        if hasattr(self, '_vertical_line_overlay'):
            self._vertical_line_overlay.clear_line()
            
        # Clear beat selection from all canvases
        for canvas in self._canvases:
            canvas._clicked_beat_timestamp = None
            canvas._clicked_beat_label = None
            canvas._clicked_beat_x_pos = None
            canvas._selected_beats = []
            canvas.update()
            
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
        
        # Clear any selected beats and vertical lines when tab changes
        self._drag_start_x = None
        self._drag_current_x = None
        self._is_dragging = False
        self._drag_start_timestamp = None
        
        # Clear vertical lines from overlay
        if hasattr(self, '_vertical_line_overlay'):
            self._vertical_line_overlay.clear_line()
        
        # Clear beat selection from all canvases
        for canvas in self._canvases:
            canvas._clicked_beat_timestamp = None
            canvas._clicked_beat_label = None
            canvas._clicked_beat_x_pos = None
            canvas._selected_beats = []
            canvas.update()
        
        # TODO: Overlay mouse enable disabled for now
        # Always enable mouse on overlay for dragging
        # self.overlay.set_mouse_enabled(True)
        
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
        # TODO: Show/hide the strip selection overlay based on tool (disabled for now)
        # Show/hide the strip selection overlay based on tool
        # When a measurement tool is active, hide the selection box
        # if self._active_tool == TOOL_SELECT:
        #     self.overlay.show()
        # else:
        #     self.overlay.hide()
        #     self.clear_magnifier_focus()

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
        # TODO: Expanded view disabled for now
        # dialog = ExpandedViewDialog(self._engine, self._current_start + start_sec, duration, self)
        # dialog.exec_()
        pass


# ============================================================================
# EXPANDED VIEW DIALOG - COMMENTED OUT (Not needed for now)
# ============================================================================
# class ExpandedViewDialog(QDialog):
#     """Expanded 12-lead view for selected time range."""
#     
#     def __init__(self, replay_engine, start_sec: float, duration: float, parent=None):
#         super().__init__(parent)
#         self._engine = replay_engine
#         self._reader = replay_engine._reader
#         self._start_sec = start_sec
#         self._duration = duration
#         
#         self.setWindowTitle("Expanded View")
#         self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
#         self.setWindowState(Qt.WindowMaximized)
#         
#         screen = QApplication.primaryScreen()
#         if screen:
#             self.resize(screen.availableGeometry().size())
#             
#         self.setStyleSheet(f"QDialog {{ background: {COL_BLACK}; }}")
#         
#         self._build_ui()
#         self._update_canvases()
#         
#     def _build_ui(self):
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(16, 16, 16, 16)
#         layout.setSpacing(8)
#         
#         top_bar = QFrame()
#         top_bar.setStyleSheet(f"background: {COL_DARK}; border-bottom: 1px solid {COL_GREEN_DRK}; border-radius: 4px;")
#         top_bar.setFixedHeight(44)
#         top_layout = QHBoxLayout(top_bar)
#         top_layout.setContentsMargins(14, 4, 14, 4)
#         top_layout.setSpacing(12)
#         
#         start_real = datetime.fromtimestamp(self._engine._reader.start_time + self._start_sec)
#         end_real = datetime.fromtimestamp(self._engine._reader.start_time + self._start_sec + self._duration)
#         self.lbl_time = QLabel(f"Time Range: {start_real.strftime('%H:%M:%S')} - {end_real.strftime('%H:%M:%S')}")
#         self.lbl_time.setStyleSheet(f"color: {COL_GREEN}; font-weight: bold; font-size: 15px;")
#         top_layout.addWidget(self.lbl_time)
#         
#         top_layout.addStretch()
#         
#         btn_close = QPushButton("Close")
#         btn_close.setStyleSheet("""
#             QPushButton {
#                 background: #0d1b2a; color: #a0c4e8;
#                 border: 1px solid #2a5a6d; padding: 5px 14px;
#                 font-size: 13px; font-weight: bold; border-radius: 4px;
#             }
#             QPushButton:hover {
#                 background: #162a3a;
#             }
#         """)
#         btn_close.clicked.connect(self.accept)
#         top_layout.addWidget(btn_close)
#         
#         layout.addWidget(top_bar)
#         
#         canvas_frame = QFrame()
#         canvas_frame.setStyleSheet(f"background: {COL_BLACK}; border: 1px solid {COL_GREEN_DRK}; border-radius: 4px;")
#         self.canvas_layout = QVBoxLayout(canvas_frame)
#         self.canvas_layout.setContentsMargins(8, 12, 8, 12)
#         self.canvas_layout.setSpacing(6)
#         
#         self._canvases = []
#         leads = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
#         for lead in leads:
#             row = QHBoxLayout()
#             row.setContentsMargins(0, 0, 0, 0)
#             row.setSpacing(6)
#             
#             lbl = QLabel(lead)
#             lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
#             lbl.setStyleSheet(
#                 f"color: {COL_GREEN}; font-weight: bold; font-size: 16px;"
#                 f" background: #0a0f18; border-right: 1px solid {COL_GREEN_DRK};"
#                 f" padding-right: 8px; padding-top: 4px; padding-bottom:4px;"
#             )
#             lbl.setFixedWidth(52)
#             
#             canvas = ECGStripCanvas(canvas_frame, height=80, color=COL_GREEN, lead_name=lead)
#             canvas.set_paper_speed(25)
#             canvas.set_gain(2.0)  # Higher gain for expanded view
#             canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
#             
#             row.addWidget(lbl)
#             row.addWidget(canvas, 1)
#             self.canvas_layout.addLayout(row)
#             self._canvases.append(canvas)
#             
#         layout.addWidget(canvas_frame, 1)
#         
#     def _update_canvases(self):
#         end_sec = min(self._start_sec + self._duration, self._engine.duration_sec)
#         data = self._reader.read_range(self._start_sec, end_sec)
#         expected_len = int(self._duration * self._engine.fs)
#         
#         # Get beat annotations for this window
#         beat_annotations = []
#         try:
#             for m in self._engine._metrics:
#                 all_beats = m.get('all_beats', [])
#                 if not all_beats:
#                     continue
#                 for beat in all_beats:
#                     ts = float(beat.get('timestamp', 0.0))
#                     if self._start_sec <= ts <= end_sec:
#                         beat_annotations.append({
#                             'timestamp': ts,
#                             'label': str(beat.get('label', 'N'))
#                         })
#             beat_annotations.sort(key=lambda b: b['timestamp'])
#         except Exception as e:
#             print(f"[Expanded View] Error loading beat annotations: {e}")
#         
#         # Generate time array for ECG strips
#         x = np.linspace(0, self._duration, expected_len)
#         
#         # Optimization: Process data efficiently with numpy vectorization
#         for i, c in enumerate(self._canvases):
#             if i < data.shape[0] and data.shape[1] > 0:
#                 d_i = data[i]
#                 # Use numpy slicing instead of padding for better performance
#                 if len(d_i) != expected_len:
#                     if len(d_i) > expected_len:
#                         d_i = d_i[:expected_len]
#                     else:
#                         # Create padded array more efficiently
#                         padded = np.empty(expected_len, dtype=d_i.dtype)
#                         padded[:len(d_i)] = d_i
#                         padded[len(d_i):] = d_i[-1] if len(d_i) > 0 else 0
#                         d_i = padded
#                 # Convert to float32 for faster rendering and pass beat annotations
#                 c.set_data(x, np.asarray(d_i, dtype=np.float32), beat_annotations=beat_annotations, start_sec=self._start_sec)
#             else:
#                 c.set_data(x, np.zeros(expected_len, dtype=np.float32), beat_annotations=beat_annotations, start_sec=self._start_sec)
# ============================================================================

class HolterToolHandlers:
    """
    Centralized button/tool handler implementations for Holter UI.
    Extracted from holter_ui.py to reduce file size and improve maintainability.
    """
    
    @staticmethod
    def handle_patient_information(parent):
        """Show patient information dialog."""
        if hasattr(parent, '_show_patient_information'):
            parent._show_patient_information()
    
    @staticmethod
    def handle_full_disclosure(parent):
        """Open Full Disclosure dialog."""
        if hasattr(parent, "_replay_engine") and parent._replay_engine:
            from .holter_full_disclosure import HolterFullDisclosureDialog
            dialog = HolterFullDisclosureDialog(parent._replay_engine, parent)
            dialog.exec_()
        else:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(parent, "No Data", "No valid replay engine found for Full Disclosure.")
    
    @staticmethod
    def handle_goto_template(parent):
        """Show tool information popup."""
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtCore import Qt
        
        box = QMessageBox(parent)
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
    
    @staticmethod
    def handle_gain_settings(parent, btn=None):
        """Cycle through gain settings."""
        try:
            from .theme import GAINS
        except ImportError:
            from ecg.holter.theme import GAINS
        
        gains = [g / 10.0 for g in GAINS]
        curr_g = getattr(parent, '_curr_gain_idx', 1)
        next_g = (curr_g + 1) % len(gains)
        parent._curr_gain_idx = next_g
        val = gains[next_g]
        
        for s in getattr(parent, "_ch_strips", []):
            s.set_gain(val)
            s.update()  # Force repaint with new gain
        if hasattr(parent, "_mini_strip") and parent._mini_strip:
            parent._mini_strip.set_gain(val)
            parent._mini_strip.update()  # Force repaint
        if btn:
            btn.setText(f"Gain: {int(val*10)}mm/mV")
    
    @staticmethod
    def handle_paper_speed(parent, btn=None):
        """Cycle through paper speed settings."""
        try:
            from .theme import PAPER_SPEEDS
        except ImportError:
            from ecg.holter.theme import PAPER_SPEEDS
        
        speeds = PAPER_SPEEDS
        curr_s = getattr(parent, '_curr_speed_idx', 1)
        next_s = (curr_s + 1) % len(speeds)
        parent._curr_speed_idx = next_s
        val = speeds[next_s]
        
        for s in getattr(parent, "_ch_strips", []):
            s.set_paper_speed(int(val))
        if hasattr(parent, "_mini_strip"):
            parent._mini_strip.set_paper_speed(int(val))
        if btn:
            btn.setText(f"Paper speed:{val}mm/s")
        
        # Adjust strip_length_sec so the replay engine delivers the right amount of data.
        parent._strip_length_sec = 10.0 * (25.0 / max(1.0, float(val)))
        if getattr(parent, "_replay_engine", None):
            try:
                parent._replay_engine.set_window_length(parent._strip_length_sec)
            except Exception:
                pass
        
        # Re-seek to force data reload with the new strip length
        try:
            current_pos = parent._slider_value_to_sec(parent._slider.value())
            parent.seek_requested.emit(current_pos)
        except Exception:
            pass
    
    @staticmethod
    def handle_strip_length(parent, btn=None):
        """Cycle through strip length settings."""
        lengths = [3, 7, 10, 15, 30]
        curr_l = getattr(parent, '_curr_length_idx', 1)
        next_l = (curr_l + 1) % len(lengths)
        parent._curr_length_idx = next_l
        val = lengths[next_l]
        parent._strip_length_sec = float(val)
        
        if getattr(parent, "_replay_engine", None):
            try:
                parent._replay_engine.set_window_length(parent._strip_length_sec)
            except Exception:
                pass
        if btn:
            btn.setText(f"Strip Length:{val}s")
    
    @staticmethod
    def apply_tool_mode_to_strips(parent, mode):
        """Apply tool mode to all ECG strips."""
        try:
            from .tool_engine import canonical_tool
        except ImportError:
            from ecg.holter.tool_engine import canonical_tool
        
        canonical_mode = canonical_tool(mode)
        parent._tool_engine.set_tool(canonical_mode)
        
        for strip in getattr(parent, "_ch_strips", []):
            if hasattr(strip, 'set_mode'):
                strip.set_mode(canonical_mode)
        if hasattr(parent._mini_strip, 'set_mode'):
            parent._mini_strip.set_mode(canonical_mode)
        for strip in getattr(parent, "_template_thumbs", []):
            if hasattr(strip, 'set_mode'):
                strip.set_mode(canonical_mode)
    
    @staticmethod
    def handle_add_event(parent):
        """Open Add Event dialog."""
        try:
            from .add_event_dialog import AddEventDialog
        except ImportError:
            from ecg.holter.add_event_dialog import AddEventDialog
        
        from datetime import datetime
        
        # Get current time and position
        start_time = datetime.now()
        current_sec = 0.0
        hr = 0.0
        
        if hasattr(parent, '_replay_engine') and parent._replay_engine:
            try:
                current_sec = parent._replay_engine.current_position()
                # Get start time from reader if available
                if hasattr(parent._replay_engine, '_reader') and hasattr(parent._replay_engine._reader, 'start_time'):
                    start_time = datetime.fromtimestamp(parent._replay_engine._reader.start_time)
            except Exception:
                pass
        
        # Get current HR from status if available
        if hasattr(parent, '_current_bpm'):
            hr = parent._current_bpm
        
        # Open dialog
        dialog = AddEventDialog(parent, start_time=start_time, current_sec=current_sec, hr=hr)
        dialog.event_added.connect(lambda data: HolterToolHandlers._on_event_added(parent, data))
        dialog.exec_()
    
    @staticmethod
    def _on_event_added(parent, event_data: dict):
        """Handle event data from Add Event dialog."""
        print(f"[Add Event] Event added: {event_data}")
        
        # Add event to parent's event list
        if hasattr(parent, '_custom_events'):
            parent._custom_events.append(event_data)
        else:
            parent._custom_events = [event_data]
        
        # Handle different actions
        action = event_data.get('action', 'add_event')
        
        if action == 'instant_print':
            # TODO: Implement instant print
            print("[Add Event] Instant print triggered")
        elif action == 'export_pdf':
            # TODO: Implement PDF export
            print("[Add Event] PDF export triggered")
        elif action == 'add_event':
            # Just add to event list
            print(f"[Add Event] Event added at timestamp {event_data['timestamp']}")
