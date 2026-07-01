"""
Expanded Lead View - Detailed ECG lead analysis with PQRST labeling and metrics
This module provides an expanded view of individual ECG leads with comprehensive analysis.
"""

import sys
import time
import numpy as np
from scipy.signal import butter, filtfilt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QGridLayout,
    QSizePolicy, QScrollArea, QGroupBox, QFormLayout, QLineEdit, QComboBox,
    QMessageBox, QApplication, QDialog, QGraphicsDropShadowEffect, QSlider, QCheckBox
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, QTimer
from utils.platform_compat import is_low_spec_mode
from scipy.signal import find_peaks, butter, filtfilt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator
import matplotlib.patches as patches
import pyqtgraph as pg
from .arrhythmia_detector import ArrhythmiaDetector
from .pan_tompkins import pan_tompkins
try:
    from .ecg_filters import (
        extract_respiration,
        estimate_baseline_drift,
        apply_ac_filter,
        apply_emg_filter,
        apply_ecg_filters,
        apply_baseline_wander_median_mean,
    )
except ImportError:
    extract_respiration = None
    estimate_baseline_drift = None
    apply_ac_filter = None
    apply_emg_filter = None
    apply_ecg_filters = None
    apply_baseline_wander_median_mean = None
try:
    from .clinical_measurements import (
        build_median_beat, get_tp_baseline, measure_pr_from_median_beat,
        measure_qrs_duration_from_median_beat, measure_qt_from_median_beat
    )
except ImportError:
    build_median_beat = None
    get_tp_baseline = None
    measure_pr_from_median_beat = None
    measure_qrs_duration_from_median_beat = None
    measure_qt_from_median_beat = None

from ecg.signal.signal_processing import extract_low_frequency_baseline

class PQRSTAnalyzer:
    """Analyze ECG signal to detect P, Q, R, S, T waves and calculate metrics"""
    
    def __init__(self, sampling_rate=500):
        self.fs = sampling_rate
        self.r_peaks = []
        self.p_peaks = []
        self.q_peaks = []
        self.s_peaks = []
        self.t_peaks = []
        
    def analyze_signal(self, signal):
        """Analyze ECG signal and detect all wave components"""
        try:
            # Filter the signal
            filtered_signal = self._filter_signal(signal)
            
            # Detect R peaks first
            self.r_peaks = self._detect_r_peaks(filtered_signal)
            
            if len(self.r_peaks) > 0:
                # Detect other waves based on R peaks
                self.p_peaks = self._detect_p_waves(filtered_signal, self.r_peaks)
                self.q_peaks = self._detect_q_waves(filtered_signal, self.r_peaks)
                self.s_peaks = self._detect_s_waves(filtered_signal, self.r_peaks)
                self.t_peaks = self._detect_t_waves(filtered_signal, self.r_peaks)
            
            return {
                'r_peaks': self.r_peaks,
                'p_peaks': self.p_peaks,
                'q_peaks': self.q_peaks,
                's_peaks': self.s_peaks,
                't_peaks': self.t_peaks
            }
        except Exception as e:
            print(f"Error in PQRST analysis: {e}")
            return {'r_peaks': [], 'p_peaks': [], 'q_peaks': [], 's_peaks': [], 't_peaks': []}
    
    def _filter_signal(self, signal):
        """Apply bandpass filter to ECG signal with improved error handling"""
        try:
            if len(signal) < 10:
                return signal
            
            # Ensure sampling rate is valid
            if self.fs <= 0 or self.fs > 10000:
                print(f" Invalid sampling rate: {self.fs} Hz, using default 80 Hz")
                self.fs = 80.0
            
            nyq = 0.5 * self.fs
            # Ensure filter frequencies are valid
            low = max(0.01, 0.5 / nyq)  # At least 0.5 Hz
            high = min(0.49, 40 / nyq)  # At most 40 Hz, but below Nyquist
            
            if low >= high:
                # Invalid filter parameters, return unfiltered signal
                print(f" Invalid filter parameters: low={low}, high={high}, fs={self.fs}")
                return signal
            
            b, a = butter(4, [low, high], btype='band')
            
            # Check if signal is long enough for filtering
            if len(signal) < max(len(b), len(a)) * 3:
                # Signal too short for filtering, return as is
                return signal
            
            filtered = filtfilt(b, a, signal)
            return filtered
        except Exception as e:
            print(f" Error filtering signal: {e}, returning unfiltered signal")
            return signal
    
    def _detect_r_peaks(self, signal):
        """Detect R peaks using Pan-Tompkins algorithm with improved sensitivity for serial data"""
        try:
            if len(signal) < 10:
                return []
            
            # Filter the signal first to reduce noise
            filtered_signal = self._filter_signal(signal)
            
            # Differentiate
            diff = np.ediff1d(filtered_signal)
            # Square
            squared = diff ** 2
            
            # Moving window integration - adaptive window size based on sampling rate
            window_size = max(3, int(0.15 * self.fs))
            if window_size > len(squared):
                window_size = len(squared) // 4
            if window_size < 1:
                window_size = 1
            
            mwa = np.convolve(squared, np.ones(window_size)/window_size, mode='same')
            
            # Adaptive threshold - more lenient for serial data
            mean_mwa = np.mean(mwa)
            std_mwa = np.std(mwa)
            
            # Use lower threshold for better sensitivity (0.3 instead of 0.5)
            threshold = mean_mwa + 0.3 * std_mwa
            
            # Minimum distance between peaks - adaptive based on expected heart rate
            # FIX-ELV1: Was 0.2*fs (200ms) = exactly RR at 300 BPM → missed every
            # other peak → false 150 BPM.  Use 0.12*fs (120ms) for up to 500 BPM.
            min_distance_samples = max(3, int(0.12 * self.fs))  # At least 120ms between peaks
            
            # Try to find peaks with the threshold
            peaks, properties = find_peaks(mwa, height=threshold, distance=min_distance_samples)
            
            # If no peaks found, try with lower threshold
            if len(peaks) == 0 and len(mwa) > 0:
                # Lower threshold to 0.1 * std for very sensitive detection
                lower_threshold = mean_mwa + 0.1 * std_mwa
                peaks, _ = find_peaks(mwa, height=lower_threshold, distance=min_distance_samples)
            
            # Additional check: if we have very few peaks but signal has variation, try even more lenient
            if len(peaks) < 2 and len(mwa) > 50:
                # Check if signal has significant variation (not flatline)
                signal_variation = np.std(filtered_signal)
                if signal_variation > 0.01:  # Signal has variation
                    # Use even lower threshold
                    very_low_threshold = mean_mwa + 0.05 * std_mwa
                    peaks, _ = find_peaks(mwa, height=very_low_threshold, distance=max(2, min_distance_samples // 2))
            
            return peaks
        except Exception as e:
            print(f"Error in R peak detection: {e}")
            return []
    
    def _detect_p_waves(self, signal, r_peaks):
        """Detect P waves before R peaks"""
        p_peaks = []
        for r in r_peaks:
            # Look for P wave 120-200ms before R peak for better accuracy
            start = max(0, r - int(0.20 * self.fs))
            end = max(0, r - int(0.12 * self.fs))
            if end > start:
                segment = signal[start:end]
                if len(segment) > 0:
                    p_idx = start + np.argmax(segment)
                    p_peaks.append(p_idx)
        return p_peaks
    
    def _detect_q_waves(self, signal, r_peaks):
        """Detect Q waves (negative deflection before R)"""
        q_peaks = []
        for r in r_peaks:
            # Look for Q wave up to 80ms before R peak
            start = max(0, r - int(0.08 * self.fs))
            end = r
            if end > start:
                segment = signal[start:end]
                if len(segment) > 0:
                    # Q wave is the minimum point between the P wave end and R peak
                    q_idx = start + np.argmin(segment)
                    q_peaks.append(q_idx)
        return q_peaks
    
    def _detect_s_waves(self, signal, r_peaks):
        """Detect S waves (negative deflection after R)"""
        s_peaks = []
        for r in r_peaks:
            # Look for S wave up to 80ms after R peak
            start = r
            end = min(len(signal), r + int(0.08 * self.fs))
            if end > start:
                segment = signal[start:end]
                if len(segment) > 0:
                    s_idx = start + np.argmin(segment)
                    s_peaks.append(s_idx)
        return s_peaks
    
    def _detect_t_waves(self, signal, r_peaks):
        """Detect T waves after S waves"""
        t_peaks = []
        for r in r_peaks:
            # Look for T wave 100-300ms after R peak
            start = min(len(signal), r + int(0.1 * self.fs))
            end = min(len(signal), r + int(0.3 * self.fs))
            if end > start:
                segment = signal[start:end]
                if len(segment) > 0:
                    t_idx = start + np.argmax(segment)
                    t_peaks.append(t_idx)
        return t_peaks

    def find_pqrst(self, signal):
        """Compatibility wrapper used by the expanded lead analysis code."""
        try:
            r_peaks = self._detect_r_peaks(signal)
            q_peaks = self._detect_q_waves(signal, r_peaks)
            s_peaks = self._detect_s_waves(signal, r_peaks)
            t_peaks = self._detect_t_waves(signal, r_peaks)
            # Do not guess P waves here; the old heuristic was the source of
            # false PR / Mobitz-style conclusions in the expanded window.
            p_peaks = []
            return p_peaks, q_peaks, r_peaks, s_peaks, t_peaks
        except Exception as e:
            print(f"Error in find_pqrst: {e}")
            return [], [], [], [], []

    def calculate_pr_interval(self, p_peaks, r_peaks):
        """Deprecated compatibility wrapper.

        The expanded view now relies on clinical_measurements.measure_pr_from_median_beat
        elsewhere for PR reporting. We return an empty list here so the old
        peak-to-peak fallback does not manufacture PR intervals from guessed P waves.
        """
        _ = (p_peaks, r_peaks)
        return []

class MetricsCard(QFrame):
    """Individual metric card with color coding and animations"""
    
    def __init__(self, title, value, unit, color="#0984e3", parent=None):
        super().__init__(parent)
        self.title = title
        self.value = value
        self.unit = unit
        self.color = color
        # Base sizes used for responsive scaling - reduced for smaller screens
        self._base_title_pt = 11
        self._base_value_pt = 20
        self._base_status_pt = 10
        
        # Flexible card height — scales down on small screens without clipping
        self.setMinimumHeight(110)
        self.setMaximumHeight(220)
        self.base_style = f"""
            QFrame {{
                background: white;
                border-radius: 8px;
                border: 2px solid #e0e0e0;
                border-top: 4px solid {self.color};
                margin: 4px;
            }}
        """
        self.hover_style = f"""
            QFrame {{
                background: #f8f9fa;
                border-radius: 8px;
                border: 2px solid {self.color};
                border-top: 4px solid {self.color};
                margin: 4px;
            }}
        """
        self.setStyleSheet(self.base_style)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.setGraphicsEffect(shadow)
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Title
        title_label = QLabel(self.title)
        title_label.setFont(QFont("Segoe UI", self._base_title_pt, QFont.Bold))
        title_label.setStyleSheet(f"color: {self.color}; border: none; margin: 0; padding: 0; font-weight: bold; background: transparent;")
        title_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(title_label)
        
        # Value
        self.value_label = QLabel(f"{self.value} {self.unit}")
        self.value_label.setFont(QFont("Segoe UI", self._base_value_pt, QFont.Bold))
        self.value_label.setStyleSheet("color: #2c3e50; border: none; margin: 4px 0; font-weight: bold; background: transparent;")
        self.value_label.setAlignment(Qt.AlignLeft)
        # Ensure enough label height for larger fonts to avoid clipping
        self.value_label.setMinimumHeight(40)
        self.value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.value_label.setWordWrap(True)
        layout.addWidget(self.value_label)
        
        layout.addStretch()
        
        # Status indicator
        self.status_label = QLabel(self.get_status())
        self.status_label.setFont(QFont("Segoe UI", self._base_status_pt, QFont.Bold))
        self.status_label.setStyleSheet(f"color: white; background-color: {self.get_status_color()}; border-radius: 6px; padding: 6px 10px; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignLeft)
        self.status_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        layout.addWidget(self.status_label)
        
    def enterEvent(self, event):
        self.setStyleSheet(self.hover_style)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self.base_style)
        super().leaveEvent(event)

    def get_status(self):
        """Get status based on metric value"""
        if self.title == "Heart Rate":
            if 60 <= self.value <= 100: return "NORMAL"
            elif self.value < 60: return "BRADYCARDIA"
            else: return "TACHYCARDIA"
        elif self.title == "PR Interval":
            if 120 <= self.value <= 200: return "NORMAL"
            elif self.value < 120: return "SHORT"
            else: return "PROLONGED"
        elif self.title == "QRS Duration":
            if 80 <= self.value < 110: return "NORMAL"
            elif 110 <= self.value < 120: return "BORDERLINE"
            elif self.value < 80: return "NARROW"
            else: return "WIDE"
        elif self.title == "QTc Interval":
            if 350 <= self.value <= 450: return "NORMAL"
            elif self.value < 350: return "SHORT"
            else: return "PROLONGED"
        else:
            return "MEASURED"
    
    def get_status_color(self):
        """Get color based on status"""
        status = self.get_status()
        if status == "NORMAL": return "#2ecc71"  # Green
        if status in ["BRADYCARDIA", "TACHYCARDIA", "PROLONGED", "WIDE"]: return "#e74c3c"  # Red
        if status == "BORDERLINE": return "#f39c12"
        if status in ["SHORT", "NARROW"]: return "#f39c12" # Orange
        return "#3498db" # Blue
    
    def update_value(self, new_value):
        """Update the metric value"""
        self.value = new_value
        self.value_label.setText(f"{self.value} {self.unit}")
        self.status_label.setText(self.get_status())
        self.status_label.setStyleSheet(f"color: white; background-color: {self.get_status_color()}; border-radius: 4px; padding: 2px 6px;")

    def set_scale(self, scale: float) -> None:
        """Scale fonts responsively based on a scale factor.

        The scale is typically derived from current window size vs. baseline.
        """
        scale = max(0.7, min(1.6, scale))
        self.value_label.setFont(QFont("Segoe UI", int(self._base_value_pt * scale), QFont.Bold))
        self.status_label.setFont(QFont("Segoe UI", int(self._base_status_pt * scale), QFont.Bold))
        # Title is the first child label in layout
        if isinstance(self.layout().itemAt(0).widget(), QLabel):
            self.layout().itemAt(0).widget().setFont(QFont("Segoe UI", int(self._base_title_pt * scale), QFont.Bold))

class ExpandedLeadView(QDialog):
    """Expanded view for individual ECG leads with detailed analysis"""
    
    def __init__(self, lead_name, ecg_data, sampling_rate=500, parent=None):
        super().__init__(parent)
        self.lead_name = lead_name
        self.ecg_data = np.array(ecg_data) if ecg_data is not None and len(ecg_data) > 0 else np.array([])
        self.sampling_rate = sampling_rate
        # Keep a reference to parent ECG page for shared metrics
        self._parent = parent
        self.analyzer = PQRSTAnalyzer(sampling_rate)
        self.arrhythmia_detector = ArrhythmiaDetector(sampling_rate)
        # Display gain (no pre-scaling; gain applied once at display stage)
        self.display_gain = 1.0

        self.amplification = 0.20  # Amplification factor (default 0.20x for waves)
        self.min_amplification = 0.05  # Minimum 5% of original
        self.max_amplification = 10.0  # Maximum 10x amplification

        # Store original y-axis limits (will be set after first plot)
        self.fixed_ylim = None

        # Store the baseline (mean) of the signal for proper zooming
        self.signal_baseline = 0.0

        # 🏥 HOSPITAL MONITOR: Simple baseline removal (display only)
        # Single low-frequency baseline removal (≤0.1 Hz equivalent)
        # No repeated recentering, no EMA, no buffer tricks
        
        # Respiration plotting support (secondary Y-axis with dynamic scaling)
        self.respiration_ax = None  # Secondary axis for respiration (if needed)
        self.respiration_ylim = None  # Dynamic Y-limits for respiration (percentile-based)
        self.respiration_data = None  # Respiration waveform data (if available)
        self.use_clean_view = False  # Default to False (unchecked)
        self.show_respiration = True
        self.show_median_overlay = True
        self.show_markers = False
        self.show_quality = True

        # Store detected arrhythmia events as (time_seconds, label)
        self.arrhythmia_events = []
        
        # Heat map + history view state
        self.heatmap_overlay = None
        self.heatmap_time_axis = None
        self.heatmap_window_step = 1.0

        # History view widgets (initialized later)
        self.history_slider = None
        self.history_slider_label = None
        self.history_slider_frame = None
        self.view_window_duration = 6.0  # seconds visible at once (matches 12-lead grid)
        self.min_view_window_duration = 2.0  # min time window (seconds)
        self.max_view_window_duration = 60.0  # max time window (seconds)
        self.view_window_offset = 0.0
        self.manual_view = False
        self.history_slider_active = False

        # Demo mode settings - sync with parent's demo manager
        self.demo_mode_active = False
        self.demo_manager = None
        if parent and hasattr(parent, 'demo_manager') and hasattr(parent, 'demo_toggle'):
            self.demo_mode_active = parent.demo_toggle.isChecked()
            self.demo_manager = parent.demo_manager
            print(f" Expanded view: Demo mode is {'ON' if self.demo_mode_active else 'OFF'}")

        # Track the rendered history window so display stabilization can reset
        # when the user jumps to a different portion of the recording.
        self._last_window_bounds = None
        
        # Live data update
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_live_data)
        self.is_live = False
        
        self.setWindowTitle(f"Detailed Analysis - {lead_name}")
        # Make dialog responsive from ~13\" laptops up to 27\" monitors
        # IMPORTANT (multi‑monitor/macOS): Prefer the SAME SCREEN as the parent window,
        # instead of always using QApplication.primaryScreen() which may be the TV.
        try:
            from PyQt5.QtWidgets import QApplication
            target_screen = None
            # 1) Try to use the parent's screen (same display as main ECG window)
            if parent is not None:
                try:
                    # Qt5: QWidget.screen() returns the QScreen where the widget is shown
                    if hasattr(parent, "screen") and parent.screen() is not None:
                        target_screen = parent.screen()
                    # Fallback: use windowHandle().screen() if available
                    elif parent.window() is not None and getattr(parent.window(), "windowHandle", None):
                        handle = parent.window().windowHandle()
                        if handle is not None and handle.screen() is not None:
                            target_screen = handle.screen()
                except Exception:
                    target_screen = None

            # 2) If we couldn't get parent's screen, fall back to primary screen
            if target_screen is None:
                target_screen = QApplication.primaryScreen()

            if target_screen is not None:
                geom = target_screen.availableGeometry()
                # Use 80% of target screen size for initial window
                w = int(geom.width() * 0.8)
                h = int(geom.height() * 0.8)
                self.resize(max(960, w), max(600, h))
            else:
                # Fallback if screen info not available
                self.resize(1280, 720)
        except Exception:
            self.resize(1280, 720)
        # Reasonable minimum to keep layout usable on small screens
        self.setMinimumSize(800, 500)

        # Center the dialog over the parent window (on the same screen) when possible
        try:
            if parent is not None:
                parent_window = parent.window()
                if parent_window is not None:
                    parent_geo = parent_window.frameGeometry()
                    dialog_geo = self.frameGeometry()
                    dialog_geo.moveCenter(parent_geo.center())
                    self.move(dialog_geo.topLeft())
        except Exception:
            # If centering fails, let Qt choose default position
            pass
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f2f5;
            }
            QScrollArea {
                border: none;
            }
        """)
        
        self.setup_ui()
        self.analyze_ecg()
        
        # Initialize history slider range after analyzing data
        self.update_history_slider()
        
        # Force initial plot update once the UI is completely set up
        self.update_plot()
        
        # Start live updates if parent is available (hardware data)
        if parent is not None:
            self.start_live_mode()

            # Initialize button states based on parent acquisition status
            if hasattr(self, 'expanded_start_btn'):
                self.update_button_states()
    
    def setup_ui(self):
        """Setup the user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Header
        self.create_header(main_layout)
        
        # Main content area with proper proportions
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)
        
        # Left side - ECG plot (70% of width)
        self.create_ecg_plot(content_layout)
        
        # Right side - Metrics (30% of width)
        self.create_metrics_panel(content_layout)
        
        main_layout.addLayout(content_layout, 1)
        
        # Bottom - Arrhythmia analysis
        self.create_arrhythmia_panel(main_layout)
    
    def create_header(self, parent_layout):
        """Create the header section"""
        header_frame = QFrame()
        header_frame.setMinimumHeight(50)
        header_frame.setMaximumHeight(70)
        header_frame.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 8px;
                padding: 10px;
                border: 1px solid #e0e0e0;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 0, 5, 0)
        
        title_label = QLabel(f"Lead {self.lead_name} - Detailed Waveform Analysis")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50; border: none; background: transparent;")
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_label.setWordWrap(True)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(35)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #34495e; color: white; border-radius: 5px;
                padding: 8px 18px; font-weight: bold; font-size: 10pt;
            }
            QPushButton:hover { background: #5d6d7e; }
        """)
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)
        
        parent_layout.addWidget(header_frame)

    # Mouse wheel event for amplification

    def wheelEvent(self, event):
        """Handle mouse wheel scrolling for amplification"""
        try:
            # Get scroll direction
            delta = event.angleDelta().y()
            
            # Calculate amplification change
            if delta > 0:
                # Scroll up = amplify (zoom in)
                self.amplification *= 1.1
            else:
                # Scroll down = deamplify (zoom out)
                self.amplification /= 1.1
            
            # Clamp amplification to limits
            self.amplification = max(self.min_amplification, 
                                    min(self.max_amplification, self.amplification))
            
            # Update the plot
            self.update_plot()
            
            # Update amplification display if it exists
            if hasattr(self, 'amp_label'):
                self.amp_label.setText(f"{self.amplification:.2f}x")
            
            event.accept()
        except Exception as e:
            print(f"Error in wheel event: {e}")
    
    def create_ecg_plot(self, parent_layout):
        """Create the ECG plot area"""
        plot_frame = QFrame()
        plot_frame.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border-radius: 8px;
                border: 1px solid #e0e5eb;
            }
        """)
        plot_layout = QVBoxLayout(plot_frame)
        plot_layout.setContentsMargins(8, 8, 8, 8)
        
        # ── Smooth pyqtgraph plot (same render engine as the 12-lead grid) ───
        # Matplotlib redrew the whole figure every frame (ax.clear + draw_idle),
        # which made the expanded waveform feel laggy. pyqtgraph instead only
        # pushes new point data into persistent curve items via setData(), so the
        # trace scrolls right-to-left fluidly exactly like the 12-lead box.
        try:
            pg.setConfigOptions(antialias=True)
        except Exception:
            pass

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#ffffff')
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.hideButtons()
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setClipToView(True)
        try:
            self.plot_widget.setDownsampling(auto=True, mode='peak')
        except Exception:
            pass
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_widget.setMinimumSize(500, 320)

        # Axis styling — keep it close to the previous matplotlib look
        self.plot_widget.setLabel('left', 'Amplitude (ADC)', color='#34495e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.12)
        for _ax_name in ('left', 'bottom'):
            try:
                _ax = self.plot_widget.getAxis(_ax_name)
                _ax.setPen(pg.mkPen(color='#34495e', width=1))
                _ax.setTextPen(pg.mkPen(color='#34495e'))
            except Exception:
                pass

        # Persistent curve items (created ONCE, updated each frame via setData)
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color=(0, 0, 0), width=1.2))
        self.median_curve = self.plot_widget.plot(pen=pg.mkPen(color='#7f8c8d', width=2.0))
        self.resp_curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#27ae60', width=1.5, style=Qt.DashLine))
        self.marker_curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#8e44ad', width=0.8, style=Qt.DashLine))
        self.event_curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#e74c3c', width=1.0, style=Qt.DashLine))
        # Isoelectric baseline (horizontal reference at ADC center)
        self.baseline_line = pg.InfiniteLine(
            angle=0, pen=pg.mkPen(color='#95a5a6', width=1.0, style=Qt.DashLine))
        self.plot_widget.addItem(self.baseline_line)

        # Keep a 'canvas' alias so any legacy references stay valid.
        self.canvas = self.plot_widget

        self.setup_ecg_plot()

        plot_layout.addWidget(self.plot_widget)

        # --- CONTROLS: two compact rows so nothing clips on any screen ---
        def _mk_lbl(text, style):
            lb = QLabel(text); lb.setStyleSheet(style); return lb
        control_frame = QFrame()
        control_frame.setStyleSheet("background: #f8f9fa; border-radius: 6px; border: 1px solid #e0e5eb;")
        ctrl_vbox = QVBoxLayout(control_frame)
        ctrl_vbox.setContentsMargins(8, 4, 8, 4)
        ctrl_vbox.setSpacing(3)

        # ── Shared compact styles ────────────────────────────────────────────
        _blue = ("QPushButton{background:#3498db;color:white;border-radius:5px;"
                 "font-weight:bold;font-size:14pt;border:1px solid #2980b9;"
                 "min-width:28px;max-width:32px;min-height:24px;max-height:26px;}"
                 "QPushButton:hover{background:#2980b9;}"
                 "QPushButton:pressed{background:#21618c;}")
        _val = ("color:#2c3e50;font-weight:bold;font-size:9pt;"
                "background:#fff;border:1px solid #dee2e6;"
                "border-radius:4px;padding:2px 5px;min-width:40px;")
        _sec = "color:#555;font-size:8pt;font-weight:600;background:transparent;border:none;"
        _grey = ("QPushButton{background:#95a5a6;color:white;border-radius:5px;"
                 "padding:2px 8px;font-weight:bold;font-size:9pt;"
                 "border:1px solid #7f8c8d;min-height:24px;max-height:26px;}"
                 "QPushButton:hover{background:#7f8c8d;}")
        _green = ("QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                  "stop:0 #4CAF50,stop:1 #45a049);color:white;"
                  "border:1px solid #4CAF50;border-radius:5px;"
                  "padding:2px 10px;font-size:9pt;font-weight:bold;"
                  "min-height:24px;max-height:26px;min-width:58px;}"
                  "QPushButton:hover{background:#45a049;}"
                  "QPushButton:pressed{background:#3d8b40;}"
                  "QPushButton:disabled{background:#aaa;border-color:#aaa;}")
        _purple = ("QPushButton{background:#8e44ad;color:white;border-radius:5px;"
                   "padding:2px 8px;font-weight:bold;font-size:9pt;"
                   "border:1px solid #7d3c98;min-height:24px;max-height:26px;}"
                   "QPushButton:hover{background:#7d3c98;}")
        _chk = "QCheckBox{font-size:9pt;color:#2c3e50;background:transparent;border:none;spacing:4px;}"

        # ── ROW 1 : Zoom  |  Amp  |  Reset  |  hint ─────────────────────────
        row1 = QHBoxLayout(); row1.setSpacing(4)

        _zt = QLabel("Zoom:"); _zt.setStyleSheet(_sec); row1.addWidget(_zt)
        _zo = QPushButton("−"); _zo.setStyleSheet(_blue)
        _zo.clicked.connect(self.zoom_out_time); row1.addWidget(_zo)
        self.zoom_label = QLabel(f"{self.view_window_duration:.1f}s")
        self.zoom_label.setAlignment(Qt.AlignCenter); self.zoom_label.setStyleSheet(_val)
        row1.addWidget(self.zoom_label)
        _zi = QPushButton("+"); _zi.setStyleSheet(_blue)
        _zi.clicked.connect(self.zoom_in_time); row1.addWidget(_zi)

        row1.addSpacing(8)
        _at = QLabel("Amp:"); _at.setStyleSheet(_sec); row1.addWidget(_at)
        _am = QPushButton("−"); _am.setStyleSheet(_blue)
        _am.clicked.connect(self.decrease_amplification); row1.addWidget(_am)
        self.amp_label = QLabel(f"{self.amplification:.2f}x")
        self.amp_label.setAlignment(Qt.AlignCenter); self.amp_label.setStyleSheet(_val)
        row1.addWidget(self.amp_label)
        _ap = QPushButton("+"); _ap.setStyleSheet(_blue)
        _ap.clicked.connect(self.increase_amplification); row1.addWidget(_ap)

        reset_btn = QPushButton("Reset"); reset_btn.setStyleSheet(_grey)
        reset_btn.clicked.connect(self.reset_amplification); row1.addWidget(reset_btn)

        _hint = QLabel("🖱 Scroll = zoom")
        _hint.setStyleSheet("color:#95a5a6;font-size:8pt;font-style:italic;"
                            "background:transparent;border:none;")
        row1.addWidget(_hint)
        row1.addStretch()

        # ── ROW 2 : Lorenz  |  toggles  |  Start / Stop ─────────────────────
        row2 = QHBoxLayout(); row2.setSpacing(8)

        lorenz_btn = QPushButton("Lorenz Plot"); lorenz_btn.setStyleSheet(_purple)
        lorenz_btn.clicked.connect(self.show_lorenz_plot); row2.addWidget(lorenz_btn)

        row2.addSpacing(6)

        # Hidden clean-view toggle (logic intact, UI hidden)
        self.clean_view_toggle = QCheckBox("Clean display")
        self.clean_view_toggle.setChecked(False)
        self.clean_view_toggle.stateChanged.connect(self.toggle_clean_view)
        self.clean_view_toggle.hide()

        self.resp_toggle = QCheckBox("Respiration")
        self.resp_toggle.setChecked(True); self.resp_toggle.setStyleSheet(_chk)
        self.resp_toggle.stateChanged.connect(self.toggle_respiration)
        row2.addWidget(self.resp_toggle)

        self.median_toggle = QCheckBox("Median beat")
        self.median_toggle.setChecked(True); self.median_toggle.setStyleSheet(_chk)
        self.median_toggle.stateChanged.connect(self.toggle_median_overlay)
        row2.addWidget(self.median_toggle)

        self.marker_toggle = QCheckBox("Markers")
        self.marker_toggle.setChecked(False); self.marker_toggle.setStyleSheet(_chk)
        self.marker_toggle.stateChanged.connect(self.toggle_markers)
        row2.addWidget(self.marker_toggle)

        row2.addStretch()

        self.expanded_start_btn = QPushButton("▶ Start")
        self.expanded_start_btn.setStyleSheet(_green)
        self.expanded_start_btn.clicked.connect(self.start_parent_acquisition)
        row2.addWidget(self.expanded_start_btn)

        self.expanded_stop_btn = QPushButton("■ Stop")
        self.expanded_stop_btn.setStyleSheet(_green)
        self.expanded_stop_btn.clicked.connect(self.stop_parent_acquisition)
        row2.addWidget(self.expanded_stop_btn)

        ctrl_vbox.addLayout(row1)
        ctrl_vbox.addLayout(row2)
        
        # History slider container (initially hidden until acquisition stops)
        history_frame = QFrame()
        history_frame.setStyleSheet("""
            QFrame {
                background: transparent;
                border: none;
            }
        """)
        history_layout = QHBoxLayout(history_frame)
        history_layout.setContentsMargins(0, 5, 0, 5)
        history_layout.setSpacing(10)

        history_label = QLabel("History View:")
        history_label.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 11pt;")
        history_layout.addWidget(history_label)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 0)
        slider.setSingleStep(10)
        slider.setPageStep(100)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setEnabled(True)  # Ensure slider is always enabled
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 2px solid #3498db;
                background: #f5f5f5;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #3498db;
                border: 2px solid #1f78b4;
                width: 18px;
                height: 18px;
                margin: -8px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #2980b9;
                border: 2px solid #21618c;
            }
            QSlider::handle:horizontal:pressed {
                background: #21618c;
            }
        """)
        slider.valueChanged.connect(self.on_history_slider_changed)
        history_layout.addWidget(slider, 1)

        history_value = QLabel("LIVE")
        history_value.setStyleSheet("color: #7f8c8d; font-size: 10pt; font-weight: bold;")
        history_layout.addWidget(history_value)
        
        # Add "Back to Live" button
        live_btn = QPushButton("↻ Live")
        live_btn.setMinimumSize(70, 30)
        live_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white; 
                border-radius: 5px;
                padding: 4px 8px;
                font-weight: bold; 
                font-size: 9pt;
            }
            QPushButton:hover { 
                background: #2980b9;
            }
        """)
        live_btn.clicked.connect(self.return_to_live_view)
        history_layout.addWidget(live_btn)
        
        # Show history slider by default (can be used anytime)
        history_frame.setVisible(True)
        plot_layout.addWidget(history_frame)

        self.history_slider = slider
        self.history_slider_label = history_value
        self.history_slider_frame = history_frame
        
        plot_layout.addWidget(control_frame)
        
        parent_layout.addWidget(plot_frame, 7) # Plot takes ~70% of horizontal space

    # Amplification functions

    def increase_amplification(self):
        """Increase amplification by 20%"""
        self.amplification *= 1.2
        self.amplification = min(self.max_amplification, self.amplification)
        if hasattr(self, 'amp_label'):
            self.amp_label.setText(f"{self.amplification:.2f}x")
        self.update_plot()
        print(f" Amplification increased to {self.amplification:.2f}x")

    def decrease_amplification(self):
        """Decrease amplification by 20%"""
        self.amplification /= 1.2
        self.amplification = max(self.min_amplification, self.amplification)
        if hasattr(self, 'amp_label'):
            self.amp_label.setText(f"{self.amplification:.2f}x")
        self.update_plot()
        print(f" Amplification decreased to {self.amplification:.2f}x")

    def reset_amplification(self):
        """Reset amplification to default (0.20x)"""
        self.amplification = 0.20
        if hasattr(self, 'amp_label'):
            self.amp_label.setText(f"{self.amplification:.2f}x")
        self.update_plot()
        print(" Amplification reset to 0.20x")

    # Time zoom controls (PDF-style + / -)
    def zoom_in_time(self):
        """Zoom in (reduce visible time window)."""
        try:
            self.view_window_duration = max(self.min_view_window_duration, self.view_window_duration / 1.25)
            if hasattr(self, 'zoom_label'):
                self.zoom_label.setText(f"{self.view_window_duration:.1f}s")
            self.update_plot()
            self.update_history_slider()
        except Exception:
            pass

    def zoom_out_time(self):
        """Zoom out (increase visible time window)."""
        try:
            max_dur = self.max_view_window_duration
            try:
                total_duration = len(self.ecg_data) / max(1.0, float(self.sampling_rate))
                max_dur = min(max_dur, max(2.0, total_duration))
            except Exception:
                pass
            self.view_window_duration = min(max_dur, self.view_window_duration * 1.25)
            if hasattr(self, 'zoom_label'):
                self.zoom_label.setText(f"{self.view_window_duration:.1f}s")
            self.update_plot()
            self.update_history_slider()
        except Exception:
            pass
    
    def setup_ecg_plot(self):
        """Configure the pyqtgraph plot widget: fixed Y range, title, X window."""
        # Add demo mode or wave speed info to title
        if self.demo_mode_active and self.demo_manager:
            mode_text = f" [{self.demo_manager.current_wave_speed}mm/s]"
        else:
            try:
                parent = self.parent()
                if parent and hasattr(parent, 'settings_manager'):
                    wave_speed = float(parent.settings_manager.get_wave_speed())
                    mode_text = f" [{wave_speed:.1f}mm/s]"
                else:
                    mode_text = ""
            except Exception:
                mode_text = ""

        ylim_low, ylim_high = (-4096.0, 0.0) if str(self.lead_name).upper() == 'AVR' else (0.0, 4096.0)
        self.display_ylim = (ylim_low, ylim_high)

        try:
            self.plot_widget.setTitle(
                f'Lead {self.lead_name} - PQRST Analysis{mode_text}',
                color='#2c3e50', size='14pt')
            # Fixed Y range (no auto-range jumping); X starts at the window width.
            self.plot_widget.setYRange(ylim_low, ylim_high, padding=0)
            self.plot_widget.setXRange(0, self.view_window_duration, padding=0)
            vb = self.plot_widget.getViewBox()
            if vb is not None:
                vb.setLimits(yMin=ylim_low, yMax=ylim_high)
        except Exception:
            pass

    def create_metrics_panel(self, parent_layout):
        """Create the metrics panel"""
        # A container frame for the entire right-side panel
        metrics_frame = QFrame()
        metrics_frame.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
            }
        """)
        # Let this panel be responsive; width controlled by stretch factors
        metrics_frame.setMinimumWidth(300)
        metrics_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        # The scroll area allows content to overflow vertically
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea { 
                background: transparent; 
                border: none; 
            }
            QScrollBar:vertical {
                border: none;
                background: #f0f2f5;
                width: 8px;
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #bdc3c7;
                min-height: 25px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # A widget that will sit inside the scroll area and hold the layout
        metrics_container_widget = QWidget()
        metrics_container_widget.setStyleSheet("background: transparent;")

        # A vertical layout for a single column of cards
        self.metrics_vbox = QVBoxLayout(metrics_container_widget)
        self.metrics_vbox.setContentsMargins(10, 10, 5, 10)
        self.metrics_vbox.setSpacing(12)

        self.metrics_cards = {}
        self.create_metrics_cards()

        scroll_area.setWidget(metrics_container_widget)

        # The main layout for the right panel
        main_metrics_layout = QVBoxLayout(metrics_frame)
        main_metrics_layout.setContentsMargins(0, 0, 0, 0)
        main_metrics_layout.addWidget(scroll_area)

        parent_layout.addWidget(metrics_frame, 3) # Metrics panel takes 30% of horizontal space
    
    def create_metrics_cards(self):
        """Create individual metric cards"""
        # Metrics displayed in expanded view (Heart Rate is not shown here)
        metrics = [
            ("RR Interval", 0, "ms", "#2980b9"),
            ("PR Interval", 0, "ms", "#8e44ad"),
            ("QRS Duration", 0, "ms", "#27ae60"),
            ("P Duration", 0, "ms", "#16a085"),
        ]
        
        for i, (title, value, unit, color) in enumerate(metrics):
            card = MetricsCard(title, value, unit, color)
            self.metrics_cards[title.lower().replace(" ", "_")] = card
            self.metrics_vbox.addWidget(card)
        
        # Add a stretch at the end
        self.metrics_vbox.addStretch(1)
        
        # Initialize with some default values for testing (only for visible metrics)
        self.update_metric('rr_interval', 0)
        self.update_metric('pr_interval', 0)
        self.update_metric('qrs_duration', 0)
        self.update_metric('p_duration', 0)
    
    def start_live_mode(self):
        """Start live data updates"""
        self.is_live = True
        # 30 FPS on normal machines; drop to 20 FPS on low-spec to halve paint cost.
        _interval = 50 if is_low_spec_mode() else 33
        self.timer.start(_interval)  # Update every ~33ms (~30 FPS) or ~50ms (20 FPS) on low-spec

    def resizeEvent(self, event):
        """Respond to window resizing by scaling fonts and components."""
        try:
            # Baseline matches initial size above
            base_w, base_h = 1400.0, 900.0
            cur_w, cur_h = max(1, self.width()), max(1, self.height())
            scale = min(cur_w / base_w, cur_h / base_h)

            # Scale metric cards
            for card in getattr(self, 'metrics_cards', {}).values():
                if hasattr(card, 'set_scale'):
                    card.set_scale(scale)
        except Exception:
            pass
        super().resizeEvent(event)
    
    def stop_live_mode(self):
        """Stop live data updates"""
        self.is_live = False
        self.timer.stop()

    def _resolve_runtime_sampling_rate(self, parent=None):
        """Return stable runtime sampling rate for plotting/analysis.

        Hardware mode is locked to 500 Hz. Demo mode may use demo/detected rate.
        This prevents waveform deformation when UI focus changes reduce measured
        UI callback cadence.
        """
        try:
            p = parent if parent is not None else (self.parent() if hasattr(self, 'parent') else None)
            is_demo = bool(getattr(self, 'demo_mode_active', False))
            if p is not None and hasattr(p, 'demo_toggle') and p.demo_toggle is not None:
                try:
                    is_demo = bool(p.demo_toggle.isChecked())
                except Exception:
                    pass

            if not is_demo:
                return 500.0

            if p is not None and hasattr(p, 'demo_fs') and p.demo_fs:
                return float(p.demo_fs)
            if p is not None and hasattr(p, 'sampler') and getattr(p.sampler, 'sampling_rate', 0):
                return float(p.sampler.sampling_rate)
        except Exception:
            pass
        return 500.0
    
    def update_live_data(self):
        """Update ECG data from parent (hardware)"""
        if not self.is_live or not hasattr(self, 'parent') or self.parent() is None:
            return
        
        try:
            # Get current data from parent ECG test page
            parent = self.parent()
            # Keep expanded-view sampling stable across focus/tab switches.
            try:
                self.sampling_rate = float(self._resolve_runtime_sampling_rate(parent))
                self.analyzer.fs = self.sampling_rate
                self.arrhythmia_detector.fs = self.sampling_rate
            except Exception:
                pass
            if hasattr(parent, 'data') and len(parent.data) > 0:
                # Find the lead index for this lead
                lead_index = self.get_lead_index()
                if lead_index is not None:
                    # 🫀 CLINICAL: Get RAW data from parent's snapshot if frozen, or parent's raw buffer if live
                    parent_frozen = getattr(parent, '_grid_frozen', False)
                    parent_snapshot = getattr(parent, '_replay_snapshot', None)
                    if parent_frozen and parent_snapshot is not None and lead_index < len(parent_snapshot):
                        new_data = parent_snapshot[lead_index]
                    elif lead_index < len(parent.data):
                        new_data = parent.data[lead_index]
                    else:
                        new_data = None

                    if new_data is not None and len(new_data) > 0:
                        # Store raw clinical data for analysis
                        self.ecg_data = np.array(new_data)
                        # Only auto-advance if user hasn't manually positioned the slider
                        if not self.manual_view and not self.history_slider_active:
                            total_duration = len(self.ecg_data) / max(1.0, self.sampling_rate)
                            target_offset = max(0.0, total_duration - self.view_window_duration)
                            # Smooth the live follow position so bursty serial updates
                            # do not make the visible window jump frame-to-frame.
                            if not hasattr(self, "_live_follow_offset"):
                                self._live_follow_offset = target_offset
                            # Light smoothing only: enough to absorb bursty serial
                            # chunk arrival without letting the view lag behind real
                            # time. Heavy smoothing (old 0.85/0.15) made the wave
                            # crawl; this tracks the newest samples closely so the
                            # waveform flows smoothly like the 12-lead grid.
                            self._live_follow_offset = (
                                0.6 * float(self._live_follow_offset)
                                + 0.4 * float(target_offset)
                            )
                            # If we have fallen noticeably behind the newest data
                            # (e.g. after a focus switch dropped frames), snap forward
                            # so the trace never appears to stall.
                            if target_offset - self._live_follow_offset > self.view_window_duration * 0.5:
                                self._live_follow_offset = target_offset
                            self.view_window_offset = self._live_follow_offset
                        
                        # Update plot first (visual update)
                        self.update_plot()
                        
                        # Then analyze ECG (including arrhythmia detection) - call periodically, not every frame
                        # Only analyze every 500ms to avoid performance issues
                        if not hasattr(self, '_last_analysis_time'):
                            self._last_analysis_time = 0.0
                        
                        current_time = time.time()
                        if current_time - self._last_analysis_time >= 0.5:  # Analyze every 500ms
                            self.analyze_ecg()
                            self._last_analysis_time = current_time
                        
                        self.update_history_slider()

                        # Update button states to reflect parent's status
                        if hasattr(self, 'expanded_start_btn'):
                            self.update_button_states()

        except Exception as e:
            print(f"Error updating live data: {e}")
    
    def calculate_p_duration(self, p_peaks, filtered_signal):
        """Calculate P wave duration from detected P peaks
        
        Args:
            p_peaks: Array of P-peak indices
            filtered_signal: Filtered ECG signal
        
        Returns:
            int: Median P duration in milliseconds
        """
        if len(p_peaks) == 0:
            return 0
        
        p_durations = []
        for p_idx in p_peaks:
            try:
                # Examine ±80 ms window around P-peak
                half_win = int(0.08 * self.sampling_rate)
                start = max(0, p_idx - half_win)
                end = min(len(filtered_signal) - 1, p_idx + half_win)
                
                if end <= start:
                    continue
                
                segment = filtered_signal[start:end]
                baseline = np.median(segment)
                
                # CRITICAL FIX: Define peak_rel correctly as relative index within segment
                peak_rel = p_idx - start  # Relative index within segment
                
                if peak_rel < 0 or peak_rel >= len(segment):
                    continue
                
                peak_val = segment[peak_rel]
                amp = np.abs(peak_val - baseline)
                
                if amp < 1e-6:  # Too small amplitude
                    continue
                
                # Threshold at 20% of peak amplitude
                thresh = 0.2 * amp
                
                # Find onset (search left from peak)
                left = peak_rel
                while left > 0 and np.abs(segment[left] - baseline) > thresh:
                    left -= 1
                
                # Find offset (search right from peak)
                right = peak_rel
                while right < len(segment) - 1 and np.abs(segment[right] - baseline) > thresh:
                    right += 1
                
                # Calculate duration in milliseconds
                dur_samples = max(1, right - left)
                p_dur_ms = dur_samples * 1000.0 / self.sampling_rate
                
                # Validate physiological range (40-120 ms)
                if 40 <= p_dur_ms <= 120:
                    p_durations.append(p_dur_ms)
            
            except Exception as e:
                print(f" Error calculating P duration for peak at {p_idx}: {e}")
                continue
        
        if len(p_durations) > 0:
            return int(round(np.median(p_durations)))
        else:
            return 0
    
    def analyze_ecg(self):
        """Analyze the current ECG data segment for PQRST features and arrhythmias."""
        if len(self.ecg_data) == 0:
            return

        try:
            # FIX-ELV2: Pull metrics from parent's authoritative calculation
            # so that expanded view and 12-lead view show identical numbers.
            parent = self.parent() if hasattr(self, 'parent') and callable(self.parent) else None
            parent_metrics = None
            if parent and hasattr(parent, 'get_current_metrics'):
                try:
                    parent_metrics = parent.get_current_metrics()
                except Exception:
                    parent_metrics = None

            if parent_metrics:
                # Use parent's calculated metrics — single source of truth
                rr_val = parent_metrics.get('rr_interval')
                pr_val = parent_metrics.get('pr_interval')
                qrs_val = parent_metrics.get('qrs_duration')
                p_val = parent_metrics.get('p_duration') or parent_metrics.get('st_interval')

                if rr_val is not None:
                    try:
                        self.update_metric('rr_interval', int(float(str(rr_val).replace('--', '0'))))
                    except (ValueError, TypeError):
                        self.update_metric('rr_interval', 0)
                if pr_val is not None:
                    try:
                        self.update_metric('pr_interval', int(float(str(pr_val).replace('--', '0'))))
                    except (ValueError, TypeError):
                        self.update_metric('pr_interval', 0)
                if qrs_val is not None:
                    try:
                        self.update_metric('qrs_duration', int(float(str(qrs_val).replace('--', '0'))))
                    except (ValueError, TypeError):
                        self.update_metric('qrs_duration', 0)
                if p_val is not None:
                    try:
                        self.update_metric('p_duration', int(float(str(p_val).replace('--', '0'))))
                    except (ValueError, TypeError):
                        self.update_metric('p_duration', 0)
            else:
                # Fallback: compute locally (same as before but with fixed min_distance)
                filtered_signal = self._apply_display_bandpass(self.ecg_data, self.sampling_rate)
                p_peaks, q_peaks, r_peaks, s_peaks, t_peaks = self.analyzer.find_pqrst(filtered_signal)

                self.p_peaks = p_peaks
                self.q_peaks = q_peaks
                self.r_peaks = r_peaks
                self.s_peaks = s_peaks
                self.t_peaks = t_peaks

                rr_intervals = np.diff(r_peaks) / self.sampling_rate * 1000
                if len(rr_intervals) > 0:
                    self.update_metric('rr_interval', int(np.median(rr_intervals)))
                else:
                    self.update_metric('rr_interval', 0)

                pr_intervals = self.analyzer.calculate_pr_interval(p_peaks, r_peaks)
                if len(pr_intervals) > 0:
                    self.update_metric('pr_interval', int(np.median(pr_intervals)))
                else:
                    self.update_metric('pr_interval', 0)

                qrs_durations = self.analyzer.calculate_qrs_duration(q_peaks, s_peaks)
                if len(qrs_durations) > 0:
                    self.update_metric('qrs_duration', int(np.median(qrs_durations)))
                else:
                    self.update_metric('qrs_duration', 0)

                p_duration = self.calculate_p_duration(p_peaks, filtered_signal)
                self.update_metric('p_duration', p_duration)

            # Still run PQRST analysis for markers/arrhythmia display
            # (even when using parent metrics for numbers)
            filtered_signal = self._apply_display_bandpass(self.ecg_data, self.sampling_rate)
            p_peaks, q_peaks, r_peaks, s_peaks, t_peaks = self.analyzer.find_pqrst(filtered_signal)
            self.p_peaks = p_peaks
            self.q_peaks = q_peaks
            self.r_peaks = r_peaks
            self.s_peaks = s_peaks
            self.t_peaks = t_peaks

            rr_intervals = np.diff(r_peaks) / self.sampling_rate * 1000 if len(r_peaks) > 1 else np.array([])
            
            # Fix call to detect_arrhythmias: point it to the UI's unified metrics
            # These were pulled from the parent and are the source of truth
            try:
                _hr_val = float(self.metrics_labels.get("heart_rate", {}).get("value", "0").replace("BPM", "").strip())
            except Exception:
                _hr_val = 0.0
            try:
                _qrs_val = float(self.metrics_labels.get("qrs_duration", {}).get("value", "0").replace("ms", "").strip())
            except Exception:
                _qrs_val = 0.0
            try:
                _pr_val = float(self.metrics_labels.get("pr_interval", {}).get("value", "0").replace("ms", "").strip())
            except Exception:
                _pr_val = 0.0

            analysis_dict = {
                'r_peaks': r_peaks,
                'p_peaks': p_peaks,
                'q_peaks': q_peaks,
                's_peaks': s_peaks,
                't_peaks': t_peaks,
                'external_hr': _hr_val,
                'external_qrs': _qrs_val,
                'external_pr': _pr_val
            }
            arrhythmias = self.arrhythmia_detector.detect_arrhythmias(
                filtered_signal,
                analysis_dict,
                lead_signals=self._collect_parent_lead_signals(parent),
            )
            self.update_arrhythmia_display(arrhythmias)

            # Store to parent for dashboard report generation
            if parent:
                if not hasattr(parent, '_last_analysis') or parent._last_analysis is None:
                    parent._last_analysis = {}
                parent._last_analysis['arrhythmias'] = arrhythmias

        except Exception as e:
            print(f" Error during ECG analysis: {e}")
    
    def get_lead_index(self):
        """Get the lead index for this lead name"""
        lead_mapping = {
            'I': 0, 'II': 1, 'III': 2, 'aVR': 3, 'aVL': 4, 'aVF': 5,
            'V1': 6, 'V2': 7, 'V3': 8, 'V4': 9, 'V5': 10, 'V6': 11
        }
        return lead_mapping.get(self.lead_name)

    def _collect_parent_lead_signals(self, parent):
        """Collect all available raw lead buffers so BBB morphology can be reported."""
        lead_mapping = {
            'I': 0, 'II': 1, 'III': 2, 'aVR': 3, 'aVL': 4, 'aVF': 5,
            'V1': 6, 'V2': 7, 'V3': 8, 'V4': 9, 'V5': 10, 'V6': 11
        }
        if parent is None:
            return {}
        try:
            parent_frozen = getattr(parent, '_grid_frozen', False)
            parent_snapshot = getattr(parent, '_replay_snapshot', None)
            if parent_frozen and parent_snapshot is not None:
                data = parent_snapshot
            elif hasattr(parent, 'data'):
                data = parent.data
            else:
                return {}
            return {
                lead: np.asarray(data[idx], dtype=float)
                for lead, idx in lead_mapping.items()
                if idx < len(data) and len(data[idx]) > 0
            }
        except Exception:
            return {}
    
    def _apply_display_bandpass(self, signal, fs=500.0, low=0.05, high=40.0, order=2):
        """Display-only bandpass to remove DC drift (<0.05 Hz) and very high freq noise."""
        if len(signal) < order * 3:
            return signal
        try:
            nyq = 0.5 * fs
            low_n = max(low / nyq, 1e-5)
            high_n = min(high / nyq, 0.999)
            b, a = butter(order, [low_n, high_n], btype="bandpass")
            return filtfilt(b, a, signal)
        except Exception:
            return signal

    def _remove_respiration_display(self, signal, fs=500.0, window_sec=2.0):
        """Display-only respiration suppression via moving-average subtraction (~0.5 Hz HP)."""
        if len(signal) == 0:
            return signal
        try:
            win = int(max(3, window_sec * fs))
            win = min(win, len(signal))
            if win < 3:
                return signal
            kernel = np.ones(win) / win
            baseline = np.convolve(signal, kernel, mode="same")
            return signal - baseline
        except Exception:
            return signal

    def _compute_median_beat(self, signal, r_peaks, fs, pre_sec=0.2, post_sec=0.4):
        """Display-only median beat (for overlay)."""
        if signal is None or len(signal) == 0 or r_peaks is None or len(r_peaks) < 2:
            return None, None
        pre = int(pre_sec * fs)
        post = int(post_sec * fs)
        beats = []
        for r in r_peaks:
            start = r - pre
            end = r + post
            if start < 0 or end > len(signal):
                continue
            beat = signal[start:end]
            if len(beat) == pre + post:
                beats.append(beat)
        if len(beats) == 0:
            return None, None
        beats_arr = np.vstack(beats)
        median = np.median(beats_arr, axis=0)
        t = (np.arange(len(median)) - pre) / fs
        return t, median

    def toggle_clean_view(self, state):
        self.use_clean_view = state == Qt.Checked
        self.update_plot()

    def toggle_respiration(self, state):
        self.show_respiration = state == Qt.Checked
        self.update_plot()

    def toggle_median_overlay(self, state):
        self.show_median_overlay = state == Qt.Checked
        self.update_plot()

    def toggle_markers(self, state):
        self.show_markers = state == Qt.Checked
        self.update_plot()

    def _apply_display_highpass(self, signal, fs, cutoff_hz=0.3):
        """
        Display-only high-pass (~0.3 Hz) applied after baseline anchoring.
        Does NOT affect raw data or measurements.
        """
        if len(signal) == 0:
            return signal
        try:
            # Approximate 0.3 Hz HPF via moving-average subtraction (~3.5s window ≈0.28 Hz)
            window_samples = int(max(10, fs * 3.5))
            window_samples = min(window_samples, len(signal))
            if window_samples < 10:
                return signal
            kernel = np.ones(window_samples) / window_samples
            baseline = np.convolve(signal, kernel, mode="same")
            return signal - baseline
        except Exception:
            return signal

    def _smooth_display_signal(self, signal, sigma=0.8):
        """Smooth plotted data without introducing right-edge jumps.

        The expanded lead window usually follows the newest samples. If we
        smooth with implicit zero-padding, the newest samples can dip or spike
        at the end of the plot. Mirror-padding avoids that visible tail jump.
        """
        if signal is None:
            return signal

        arr = np.asarray(signal, dtype=float)
        if arr.size <= 5:
            return arr

        pad = max(3, int(np.ceil(max(0.5, float(sigma)) * 3)))
        if arr.size <= pad:
            return arr

        try:
            from scipy.ndimage import gaussian_filter1d

            padded = np.pad(arr, pad_width=pad, mode='reflect')
            smoothed = gaussian_filter1d(padded, sigma=float(sigma), mode='nearest')
            return smoothed[pad:-pad]
        except Exception:
            kernel_size = max(3, min(7, (pad * 2) + 1))
            kernel = np.ones(kernel_size, dtype=float) / float(kernel_size)
            padded = np.pad(arr, pad_width=pad, mode='edge')
            smoothed = np.convolve(padded, kernel, mode='same')
            return smoothed[pad:-pad]
    
    def calculate_respiration_ylim(self, respiration_signal):
        """Calculate dynamic Y-limits for respiration using percentiles.
        Ensures respiration amplitude is fully visible without cropping.
        
        Args:
            respiration_signal: Respiration waveform array
            
        Returns:
            Tuple of (y_min, y_max) for respiration Y-axis
        """
        if len(respiration_signal) == 0:
            return (-100, 100)  # Default range
        
        # Remove NaN and invalid values
        valid_resp = respiration_signal[~np.isnan(respiration_signal)]
        if len(valid_resp) == 0:
            return (-100, 100)
        
        # Use percentiles to avoid outliers (robust scaling)
        p1 = np.percentile(valid_resp, 1)   # 1st percentile
        p99 = np.percentile(valid_resp, 99)  # 99th percentile
        
        # Add padding (10% margin) to ensure full visibility
        range_padding = (p99 - p1) * 0.1
        y_min = p1 - range_padding
        y_max = p99 + range_padding
        
        # Ensure minimum range for visibility
        min_range = 50.0
        if (y_max - y_min) < min_range:
            center = (y_max + y_min) / 2.0
            y_min = center - min_range / 2.0
            y_max = center + min_range / 2.0
        
        return (y_min, y_max)
    
    def extract_respiration_from_ecg(self, ecg_signal):
        """Extract respiration waveform from ECG signal (optional, for display).
        Uses ecg_filters functions if available.
        
        Args:
            ecg_signal: Raw ECG signal array
            
        Returns:
            Respiration waveform array, or None if extraction fails
        """
        if extract_respiration is None or estimate_baseline_drift is None:
            return None
        
        try:
            if len(ecg_signal) < 100:  # Need minimum data
                return None
            
            # Extract baseline drift first
            drift = estimate_baseline_drift(ecg_signal, self.sampling_rate)
            
            # Extract respiration from drift signal
            respiration = extract_respiration(drift, self.sampling_rate)
            
            return respiration
        except Exception as e:
            print(f" Error extracting respiration: {e}")
            return None
    
    def update_plot(self):
        """Update the ECG plot with new data"""
        if len(self.ecg_data) == 0:
            return
        
        try:
            total_samples = len(self.ecg_data)
            window_samples = max(1, int(self.view_window_duration * self.sampling_rate))
            if window_samples > total_samples:
                window_samples = total_samples

            total_duration = total_samples / max(1.0, self.sampling_rate)
            max_offset = max(0.0, total_duration - self.view_window_duration)
            # If user manually positioned slider, keep that position
            if not self.manual_view and not self.history_slider_active:
                self.view_window_offset = max_offset
            else:
                self.view_window_offset = min(self.view_window_offset, max_offset)

            start_idx = int(self.view_window_offset * self.sampling_rate)
            end_idx = min(total_samples, start_idx + window_samples)

            try:
                non_zero_indices = np.where(self.ecg_data != 0)[0]
                if len(non_zero_indices) > 0:
                    first_real_idx = int(non_zero_indices[0])
                    if first_real_idx > start_idx:
                        start_idx = first_real_idx
                        end_idx = min(total_samples, start_idx + window_samples)
            except Exception:
                pass

            if end_idx - start_idx <= 1:
                return

            # To avoid filter edge artifacts at the very start/end of the visible box
            # (especially when 50 Hz AC filter is enabled), we apply all display‑only
            # filters on a slightly larger padded segment, then crop back to the
            # requested [start_idx, end_idx) window.
            pad_seconds = 0.5  # 500 ms padding on each side
            pad_samples = int(pad_seconds * self.sampling_rate)
            padded_start = max(0, start_idx - pad_samples)
            padded_end = min(total_samples, end_idx + pad_samples)

            signal_raw = self.ecg_data[padded_start:padded_end]

            # ── FIX: Mirror-pad right edge when at buffer end ─────────────────
            # When end_idx = total_samples (live view), right pad = 0
            # → filtfilt has no causal data → Gibbs ringing → jump at right edge
            # Solution: mirror-extend the last pad_samples worth of signal
            right_missing = pad_samples - (padded_end - end_idx)
            if right_missing > 0 and len(signal_raw) > right_missing:
                mirror_right = signal_raw[-right_missing:][::-1]  # mirror last N samples
                signal_raw = np.concatenate([signal_raw, mirror_right])
            # ─────────────────────────────────────────────────────────────────

            padded_signal = signal_raw
            if len(padded_signal) <= 1:
                return

            # This is the portion we will actually display after filtering
            visible_len = end_idx - start_idx
            visible_offset = start_idx - padded_start
            current_window_bounds = (start_idx, end_idx)

            window_signal = padded_signal  # use padded for filtering
            
            # Ensure we have valid data
            if len(window_signal) == 0:
                return
            
            # ---------------- DISPLAY-ONLY PIPELINE ----------------
            # Clinical signal (raw) is untouched; display_signal is for plotting only.
            display_signal = window_signal.copy()
            try:
                # Keep expanded view filter behavior aligned with 12-box defaults.
                # Default AC notch is 50 Hz; if user turns it off, both views follow that.
                ac_opt = '50'
                emg_opt = 'off'
                dft_opt = 'off'
                if hasattr(self._parent, 'settings_manager') and self._parent.settings_manager is not None:
                    ac_opt = str(self._parent.settings_manager.get_setting('filter_ac', '50')).strip()
                    emg_opt = str(self._parent.settings_manager.get_setting('filter_emg', 'off')).strip()
                    dft_opt = str(self._parent.settings_manager.get_setting('filter_dft', 'off')).strip()

                if apply_ecg_filters is not None:
                    # Display fix: 0.5 Hz "DFT" high-pass can introduce beat-synchronous baseline droop
                    # between QRS complexes on short windows. For expanded view display, keep the
                    # isoelectric line visually straight by using median+mean baseline removal when
                    # the user selects 0.5 Hz.
                    use_median_mean_baseline = (str(dft_opt).strip() == '0.5')
                    display_signal = apply_ecg_filters(
                        signal=display_signal,
                        sampling_rate=float(self.sampling_rate),
                        ac_filter=ac_opt if ac_opt in ('50', '60') else None,
                        emg_filter=emg_opt if emg_opt not in ('off', '') else None,
                        dft_filter=None if use_median_mean_baseline else (dft_opt if dft_opt not in ('off', '') else None),
                    )
                    if use_median_mean_baseline and apply_baseline_wander_median_mean is not None:
                        display_signal = apply_baseline_wander_median_mean(display_signal, float(self.sampling_rate))
                else:
                    if apply_emg_filter is not None and emg_opt not in ('off', ''):
                        display_signal = apply_emg_filter(display_signal, float(self.sampling_rate), emg_opt)
                    if apply_ac_filter is not None and ac_opt in ('50', '60'):
                        display_signal = apply_ac_filter(display_signal, float(self.sampling_rate), ac_opt)

                # Optional clean-view mode can further suppress respiration drift.
                if self.use_clean_view:
                    display_signal = self._remove_respiration_display(display_signal, fs=self.sampling_rate, window_sec=2.0)
            except Exception as filter_error:
                print(f" Expanded view display filter error: {filter_error}")

            # After all filters, crop back to the exact visible window to remove
            # edge transients introduced by filtering the padded segment.
            try:
                if visible_len > 0 and len(display_signal) >= visible_offset + visible_len:
                    display_signal = display_signal[visible_offset:visible_offset + visible_len]
            except Exception:
                # In case of any indexing issues, fall back to the original (unpadded) slice
                display_signal = self.ecg_data[start_idx:end_idx]

            sigma = 0.8
            if hasattr(self._parent, 'SMOOTH_SIGMA'):
                sigma = float(self._parent.SMOOTH_SIGMA)
            display_signal = self._smooth_display_signal(display_signal, sigma=sigma)

            # ---------------- DISPLAY SCALING (apply gain ONCE, last) ----------------
            wave_gain_mm = 10.0
            try:
                if hasattr(self._parent, "settings_manager"):
                    wave_gain_mm = float(self._parent.settings_manager.get_wave_gain())
            except Exception:
                wave_gain_mm = 10.0
            gain = wave_gain_mm / 10.0  # 10mm/mV = 1.0x baseline

            center_slice = display_signal
            if len(display_signal) > 20:
                edge_trim = max(1, min(len(display_signal) // 10, int(self.sampling_rate * 0.2)))
                if (len(display_signal) - (edge_trim * 2)) >= 5:
                    center_slice = display_signal[edge_trim:-edge_trim]

            # ── FIX: Percentile-based baseline — works at ALL BPM incl 219 ────
            # median fails at high BPM: 36 beats in window → median IS the QRS
            # P10 tracks the true isoelectric line regardless of heart rate
            # (10th percentile ≈ TP segment baseline at any BPM)
            if len(center_slice) > 0:
                raw_center = float(np.percentile(center_slice, 10))
            else:
                raw_center = 0.0

            if (
                not hasattr(self, '_display_center_ema')
                or self._last_window_bounds is None
                or abs(current_window_bounds[0] - self._last_window_bounds[0]) > max(1, int(self.sampling_rate * 30.0))
            ):
                self._display_center_ema = raw_center
            else:
                # Keep the live expanded view visually stable.
                # The dashboard view already renders against a fixed center;
                # here we only allow very slow baseline drift correction so the
                # waveform does not wobble as new samples arrive.
                if self.manual_view or self.history_slider_active:
                    center_alpha = 0.01
                    self._display_center_ema = (
                        (center_alpha * raw_center)
                        + ((1.0 - center_alpha) * self._display_center_ema)
                    )
            self._last_window_bounds = current_window_bounds
            # ─────────────────────────────────────────────────────────────────

            centered = display_signal - self._display_center_ema
            scaled = centered * (gain * self.amplification)
            visual_gain = 1.5
            adc_center = -2048 if str(self.lead_name).upper() == 'AVR' else 2048
            display_adc = adc_center + scaled * visual_gain
            
            # Create time array matching the signal length
            fs = max(1.0, float(self.sampling_rate))
            time = np.arange(len(display_adc), dtype=float) / fs + (start_idx / fs)

            ylim_low, ylim_high = (-4096.0, 0.0) if str(self.lead_name).upper() == 'AVR' else (0.0, 4096.0)

            # ── SMOOTH RENDER (pyqtgraph) ────────────────────────────────────
            # No matplotlib clear/redraw. We push new data into persistent curve
            # items (setData), the same technique the 12-lead grid uses, so the
            # trace scrolls right-to-left fluidly with no per-frame figure rebuild.

            # Ensure time and display_adc arrays have matching lengths
            if len(time) != len(display_adc):
                min_len = min(len(time), len(display_adc))
                time = time[:min_len]
                display_adc = display_adc[:min_len]
            
            # Beat-quality estimate → line opacity (kept from previous behavior)
            waveform_alpha = 255
            quality_text = None
            if len(display_adc) > 0:
                valid_mask = ~np.isnan(display_adc)
                if np.any(valid_mask):
                    try:
                        ptp = np.ptp(display_adc[valid_mask])
                        if self.show_quality and ptp < 0.15:
                            waveform_alpha = 110
                            quality_text = "Quality: Noisy/Low"
                        elif self.show_quality:
                            quality_text = "Quality: Clean"
                    except Exception:
                        pass
                    # Light smoothing for a clean line without right-edge artifacts
                    display_adc = self._smooth_display_signal(display_adc, sigma=0.5)

                    # Update the main waveform curve. connect='finite' makes
                    # pyqtgraph break the line across any NaN gaps automatically.
                    self.curve.setPen(pg.mkPen(color=(0, 0, 0, int(waveform_alpha)), width=1.2))
                    self.curve.setData(np.asarray(time, dtype=float),
                                       np.asarray(display_adc, dtype=float),
                                       connect='finite')
                else:
                    self.curve.setData([], [])
                    print(f" All data is NaN in expanded view for lead {self.lead_name}")
            else:
                self.curve.setData([], [])
                print(f" No data to plot in expanded view for lead {self.lead_name}: len={len(display_adc)}")

            # X window follows the newest samples → smooth right-to-left scroll
            if len(time) > 0:
                self.plot_widget.setXRange(float(time[0]), float(time[-1]), padding=0)

            # Isoelectric baseline (display units) — static horizontal reference
            self.baseline_line.setValue(adc_center)
            self.baseline_line.setVisible(len(display_adc) > 0)

            # Arrhythmia event markers: vertical dashed lines built as a single
            # NaN-separated curve (cheap, no per-frame item churn).
            try:
                ex, ey = [], []
                if getattr(self, "arrhythmia_events", None) and len(time) > 0:
                    t_start, t_end = float(time[0]), float(time[-1])
                    for evt_time, _evt_label in self.arrhythmia_events:
                        if t_start <= evt_time <= t_end:
                            ex += [evt_time, evt_time, np.nan]
                            ey += [ylim_low, ylim_high, np.nan]
                self.event_curve.setData(np.asarray(ex, dtype=float),
                                         np.asarray(ey, dtype=float), connect='finite')
            except Exception as evt_err:
                print(f" Event marker overlay error: {evt_err}")
                self.event_curve.setData([], [])

            # Median beat overlay (display-only)
            try:
                if self.show_median_overlay and len(display_adc) > 0:
                    r_peaks_local = self.analyzer._detect_r_peaks(window_signal)
                    t_median, median_beat = self._compute_median_beat(display_adc, r_peaks_local, self.sampling_rate)
                    if (t_median is not None and median_beat is not None
                            and len(t_median) == len(median_beat) and len(r_peaks_local) > 0):
                        r0 = r_peaks_local[0]
                        t0 = time[0] + r0 / self.sampling_rate
                        self.median_curve.setData(np.asarray(t0 + t_median, dtype=float),
                                                  np.asarray(median_beat, dtype=float))
                    else:
                        self.median_curve.setData([], [])
                else:
                    self.median_curve.setData([], [])
            except Exception as median_err:
                print(f" Median beat overlay error: {median_err}")
                self.median_curve.setData([], [])

            # Measurement markers (optional P/Q/S/T) as NaN-separated verticals
            try:
                mx, my = [], []
                if self.show_markers and len(time) > 0:
                    analysis_local = self.analyzer.analyze_signal(window_signal)
                    for _key in ("p_peaks", "q_peaks", "s_peaks", "t_peaks"):
                        for idx in analysis_local.get(_key, []):
                            if 0 <= idx < len(time):
                                mx += [float(time[idx]), float(time[idx]), np.nan]
                                my += [ylim_low, ylim_high, np.nan]
                self.marker_curve.setData(np.asarray(mx, dtype=float),
                                          np.asarray(my, dtype=float), connect='finite')
            except Exception as marker_err:
                print(f" Marker overlay error: {marker_err}")
                self.marker_curve.setData([], [])

            # Respiration overlay. pyqtgraph has no twin-axis here, so respiration
            # is normalized (percentile-based) and mapped into a band in the upper
            # part of the ECG view, keeping the ECG amplitude scale fixed.
            try:
                show_resp = (self.show_respiration
                             and hasattr(self, 'respiration_data')
                             and self.respiration_data is not None)
                if show_resp and len(time) > 0:
                    if len(self.respiration_data) > end_idx:
                        respiration_window = self.respiration_data[start_idx:end_idx]
                    elif len(self.respiration_data) > start_idx:
                        respiration_window = self.respiration_data[start_idx:]
                    else:
                        respiration_window = self.respiration_data
                    respiration_window = np.asarray(respiration_window, dtype=float)

                    if respiration_window.size != len(time) and respiration_window.size >= 2:
                        xp = np.linspace(0.0, 1.0, respiration_window.size)
                        xq = np.linspace(0.0, 1.0, len(time))
                        respiration_window = np.interp(xq, xp, respiration_window)

                    valid_resp = respiration_window[~np.isnan(respiration_window)]
                    if valid_resp.size > 0 and respiration_window.size == len(time):
                        p1 = float(np.percentile(valid_resp, 1))
                        p99 = float(np.percentile(valid_resp, 99))
                        span = max(1e-6, p99 - p1)
                        full = (ylim_high - ylim_low)
                        band = 0.18 * full
                        center = adc_center + 0.55 * (ylim_high - adc_center)
                        resp_disp = center + (((respiration_window - p1) / span) - 0.5) * band
                        self.resp_curve.setData(np.asarray(time, dtype=float),
                                                np.asarray(resp_disp, dtype=float), connect='finite')
                    else:
                        self.resp_curve.setData([], [])
                else:
                    self.resp_curve.setData([], [])
            except Exception as resp_error:
                print(f" Error plotting respiration: {resp_error}")
                self.resp_curve.setData([], [])

            # Title (amplification + quality)
            amp_text = f" (Zoom: {self.amplification:.2f}x)" if self.amplification != 1.0 else ""
            q_text = f"  •  {quality_text}" if quality_text else ""
            self.plot_widget.setTitle(
                f'Lead {self.lead_name} - Live PQRST Analysis{amp_text}{q_text}',
                color='#2c3e50', size='14pt')
        except Exception as e:
            print(f"Error updating plot: {e}")
    
    def show_lorenz_plot(self):
        """Open the Lorenz (Poincaré) plot for the current lead."""
        try:
            from ecg.lorenz_plot import LorenzPlotDialog
            dlg = LorenzPlotDialog(
                ecg_signal=self.ecg_data,
                fs=float(self.sampling_rate),
                lead_name=self.lead_name,
                parent=self,
            )
            dlg.exec_()
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Lorenz Plot", f"Could not open Lorenz plot: {e}")

    def closeEvent(self, event):
        """Handle window close event"""
        self.stop_live_mode()
        event.accept()

    # Start/Stop Acquisition from Expanded Lead View

    def start_parent_acquisition(self):
        """Start serial data acquisition from parent ECG test page"""
        try:
            parent = self.parent()
            
            # Check if demo mode is active - prevent starting if it is
            if parent and hasattr(parent, 'demo_toggle') and parent.demo_toggle.isChecked():
                QMessageBox.warning(self, "Demo Mode Active", 
                    "Cannot start serial acquisition while Demo mode is ON.\n\n"
                    "Please turn off Demo mode first to use real serial data.")
                print("Cannot start acquisition - Demo mode is active")
                return
            
            if parent and hasattr(parent, 'start_acquisition'):
                print("Starting acquisition from expanded lead view...")
                parent.start_acquisition()
                
                # Update button states
                self.expanded_start_btn.setEnabled(False)
                self.expanded_stop_btn.setEnabled(True)
                
                # Ensure live mode is active for this view
                if not self.is_live:
                    self.start_live_mode()
                self.history_slider_active = False
                self.manual_view = False
                if self.history_slider_frame:
                    self.history_slider_frame.setVisible(False)
                    
                print(" Acquisition started successfully from expanded view")
            else:
                QMessageBox.warning(self, "Error", 
                    "Cannot start acquisition. Parent ECG page not found.")
                print("Parent ECG test page not available")
        except Exception as e:
            print(f"Error starting acquisition from expanded view: {e}")
            QMessageBox.warning(self, "Error", 
                f"Failed to start acquisition: {str(e)}")
    
    def stop_parent_acquisition(self):
        """Stop serial data acquisition from parent ECG test page"""
        try:
            parent = self.parent()
            if parent and hasattr(parent, 'stop_acquisition'):
                print(" Stopping acquisition from expanded lead view...")
                parent.stop_acquisition()
                self.stop_live_mode()
                self.history_slider_active = True
                self.manual_view = False
                if self.history_slider_frame:
                    self.history_slider_frame.setVisible(True)
                self.update_history_slider()
                
                # Update button states
                self.expanded_start_btn.setEnabled(True)
                self.expanded_stop_btn.setEnabled(False)
                
                print(" Acquisition stopped successfully from expanded view")
            else:
                QMessageBox.warning(self, "Error", 
                    "Cannot stop acquisition. Parent ECG page not found.")
                print(" Parent ECG test page not available")
        except Exception as e:
            print(f" Error stopping acquisition from expanded view: {e}")
            QMessageBox.warning(self, "Error", 
                f"Failed to stop acquisition: {str(e)}")
    
    def update_button_states(self):
        """Update start/stop button states based on parent acquisition status.

        Called every live tick (~30 FPS), so it must be cheap and quiet: we only
        touch the widgets / log when the state actually changes.
        """
        try:
            parent = self.parent()

            # Check if demo mode is active
            is_demo_mode = False
            if parent and hasattr(parent, 'demo_toggle'):
                is_demo_mode = parent.demo_toggle.isChecked()

            is_running = False
            if (not is_demo_mode) and parent and hasattr(parent, 'timer'):
                is_running = parent.timer.isActive()

            # Skip all work (and logging) if nothing changed since last tick.
            state = (is_demo_mode, is_running)
            if getattr(self, '_last_button_state', None) == state:
                return
            self._last_button_state = state

            if hasattr(self, 'expanded_start_btn') and hasattr(self, 'expanded_stop_btn'):
                if is_demo_mode:
                    # Demo mode is ON - hide the buttons
                    self.expanded_start_btn.setVisible(False)
                    self.expanded_stop_btn.setVisible(False)
                    print("Demo mode ON - Start/Stop buttons hidden in expanded view")
                else:
                    # Demo mode is OFF - show the buttons and update their states
                    self.expanded_start_btn.setVisible(True)
                    self.expanded_stop_btn.setVisible(True)
                    self.expanded_start_btn.setEnabled(not is_running)
                    self.expanded_stop_btn.setEnabled(is_running)
                    print("Demo mode OFF - Start/Stop buttons visible in expanded view")
        except Exception as e:
            print(f"Error updating button states: {e}")
    
    def create_arrhythmia_panel(self, parent_layout):
        """Create the arrhythmia analysis panel"""
        arrhythmia_frame = QFrame()
        arrhythmia_frame.setMinimumHeight(44)
        arrhythmia_frame.setMaximumHeight(80)
        arrhythmia_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        arrhythmia_frame.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
            }
        """)
        arrhythmia_layout = QHBoxLayout(arrhythmia_frame)
        arrhythmia_layout.setContentsMargins(15, 10, 15, 10)
        arrhythmia_layout.setSpacing(15)
        
        title = QLabel("Arrhythmia Interpretation:")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color: #2c3e50; border: none; background: transparent;")
        arrhythmia_layout.addWidget(title)
        
        self.arrhythmia_list = QLabel("Analyzing...")
        self.arrhythmia_list.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.arrhythmia_list.setStyleSheet("color: #34495e; border: none; background: transparent;")
        self.arrhythmia_list.setWordWrap(True)
        self.arrhythmia_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        arrhythmia_layout.addWidget(self.arrhythmia_list, 1)
        
        parent_layout.addWidget(arrhythmia_frame)
    
    def analyze_ecg(self):
        """Analyze the ECG signal and update metrics"""
        if self.ecg_data.size == 0:
            if hasattr(self, 'arrhythmia_list'):
                self.arrhythmia_list.setText("No data to analyze.")
            return
        
        try:
            # Ensure we have enough data for analysis (at least 2 seconds)
            min_samples = int(2.0 * self.sampling_rate)
            if len(self.ecg_data) < min_samples:
                if hasattr(self, 'arrhythmia_list'):
                    self.arrhythmia_list.setText("Collecting data...")
                return
            
            # Analyze signal for PQRST waves
            analysis = self.analyzer.analyze_signal(self.ecg_data)
            self.calculate_metrics(analysis)
            
            # Check if serial data has actually started flowing (not just initial state)
            has_received_serial_data = False
            min_serial_data_packets = 50
            
            # Check parent for serial reader state
            if self._parent and hasattr(self._parent, 'serial_reader'):
                serial_reader = self._parent.serial_reader
                if serial_reader and hasattr(serial_reader, 'running') and serial_reader.running:
                    # Check if we've received substantial serial data
                    if hasattr(serial_reader, 'data_count'):
                        data_count = serial_reader.data_count
                        # Only check for asystole if we've received at least 50 packets
                        if data_count >= min_serial_data_packets:
                            has_received_serial_data = True
                            print(f" Serial data flowing: {data_count} packets received - asystole detection enabled")
                        else:
                            print(f" Waiting for serial data: {data_count}/{min_serial_data_packets} packets - asystole detection disabled")
            
            # Detect arrhythmias using raw ECG data
            print(f" Analyzing arrhythmias for {self.lead_name}: {len(self.ecg_data)} samples, {len(analysis.get('r_peaks', []))} R-peaks detected")
            
            # Inject external metrics from the parent window so the detector uses the accurate UI calculations
            try:
                p = self._parent if hasattr(self, '_parent') else (self.parent() if hasattr(self, 'parent') else None)
                if p and hasattr(p, 'get_current_metrics'):
                    m = p.get_current_metrics()
                    if m:
                        analysis['external_hr'] = float(str(m.get('heart_rate', 0)).replace('--', '0'))
                        analysis['external_pr'] = float(str(m.get('pr_interval', 0)).replace('--', '0'))
                        analysis['external_qrs'] = float(str(m.get('qrs_duration', 0)).replace('--', '0'))
            except Exception as e:
                pass

            arrhythmias = self.arrhythmia_detector.detect_arrhythmias(
                self.ecg_data, 
                analysis,
                has_received_serial_data=has_received_serial_data,
                min_serial_data_packets=min_serial_data_packets,
                lead_signals=self._collect_parent_lead_signals(self._parent or self.parent()),
            )
            print(f" Arrhythmia detection result for {self.lead_name}: {arrhythmias}")
            self.update_arrhythmia_display(arrhythmias)
            
            # Generate heat map data (optional - don't break if method doesn't exist)
            try:
                if len(analysis.get('r_peaks', [])) > 0:
                    # Check if method exists before calling
                    if hasattr(self.arrhythmia_detector, 'detect_arrhythmias_with_probabilities'):
                        heat_map_data = self.arrhythmia_detector.detect_arrhythmias_with_probabilities(
                            self.ecg_data, analysis['r_peaks'], window_size=2.0
                        )
                        self.prepare_heatmap_overlay(heat_map_data)
                    else:
                        # Method doesn't exist, clear heatmap
                        self.heatmap_overlay = None
                        self.heatmap_time_axis = None
                else:
                    # No R-peaks detected, clear heatmap
                    self.heatmap_overlay = None
                    self.heatmap_time_axis = None
            except Exception as heatmap_error:
                # Heatmap is optional - don't break arrhythmia display
                import traceback
                print(f" Heatmap generation error (non-critical): {heatmap_error}")
                traceback.print_exc()
                self.heatmap_overlay = None
                self.heatmap_time_axis = None
            
            self.update_plot_with_markers(analysis)
            
            # Update history slider range after analysis
            self.update_history_slider()
        except Exception as e:
            import traceback
            error_msg = f"Error in ECG analysis for {self.lead_name}: {str(e)}"
            print(error_msg)
            traceback.print_exc()
            if hasattr(self, 'arrhythmia_list'):
                self.arrhythmia_list.setText(f"Analysis error: {str(e)[:50]}")
            print(traceback.format_exc())
            # Still try to show rate-based detection even if other detections fail
            try:
                if len(self.ecg_data) > 0:
                    # Try to get r_peaks from analyzer if analysis failed
                    try:
                        temp_analysis = self.analyzer.analyze_signal(self.ecg_data)
                        r_peaks = temp_analysis.get('r_peaks', [])
                    except:
                        r_peaks = []
                    
                    if len(r_peaks) >= 3:
                        rr_intervals = np.diff(r_peaks) / self.sampling_rate * 1000
                        if len(rr_intervals) >= 2:
                            mean_rr = np.mean(rr_intervals)
                            if mean_rr > 0:
                                heart_rate = 60000 / mean_rr
                                if heart_rate >= 100:
                                    self.arrhythmia_list.setText("Sinus Tachycardia")
                                elif heart_rate < 60:
                                    self.arrhythmia_list.setText("Sinus Bradycardia")
                                else:
                                    self.arrhythmia_list.setText(f"Analysis error: {str(e)[:50]}")
                            else:
                                self.arrhythmia_list.setText(f"Analysis error: {str(e)[:50]}")
                        else:
                            self.arrhythmia_list.setText(f"Analysis error: {str(e)[:50]}")
                    else:
                        self.arrhythmia_list.setText(f"Analysis error: {str(e)[:50]}")
                else:
                    self.arrhythmia_list.setText(f"Analysis error: {str(e)[:50]}")
            except Exception as e2:
                print(f"Error in fallback detection: {e2}")
                self.arrhythmia_list.setText(f"Analysis error: {str(e)[:50]}")
    
    def calculate_metrics(self, analysis):
        """Calculate ECG metrics from analysis results
        
        ⚠️ CLINICAL ANALYSIS: Uses self.ecg_data which comes from parent.data[lead_index]
        This is raw clinical data, NOT display-processed data.
        
        - Lead II: Uses parent's standardized metrics to match dashboard display exactly
        - Other leads (I, III, aVR, aVL, aVF, V1-V6): Calculate independently from their own data
        This ensures Lead II matches dashboard while other leads show lead-specific analysis.
        """
        try:
            # Check if demo mode is active from parent
            parent = self._parent if hasattr(self, '_parent') else None
            is_demo_mode = False
            if parent is not None and hasattr(parent, 'demo_toggle'):
                is_demo_mode = parent.demo_toggle.isChecked()
            
            # If demo mode is active, use fixed demo values
            if is_demo_mode:
                self.update_metric('heart_rate', 60)
                self.update_metric('rr_interval', 1000)
                self.update_metric('pr_interval', 160)
                self.update_metric('qrs_duration', 85)
                self.update_metric('p_duration', 80)
                return
            
            # For Lead II: Use parent's standardized metrics to match dashboard display
            # Dashboard metrics are calculated from Lead II, so expanded Lead II should match exactly
            if self.lead_name == "II" and parent is not None:
                try:
                    # Get parent's current metrics (standardized calculations from Lead II)
                    if hasattr(parent, 'get_current_metrics'):
                        parent_metrics = parent.get_current_metrics()
                        
                        # Extract and update metrics from parent (ensures exact match with dashboard)
                        def safe_int(val, default=0):
                            try:
                                if isinstance(val, str):
                                    # Remove units and extract number
                                    val = val.replace(' BPM', '').replace(' bpm', '').replace(' ms', '').replace(' ms', '').strip()
                                    if '/' in val:
                                        val = val.split('/')[0]  # Take first value if QT/QTc format
                                    return int(float(val)) if val and val != '0' else default
                                return int(float(val)) if val else default
                            except:
                                return default
                        
                        # Update Heart Rate
                        if 'heart_rate' in parent_metrics:
                            hr_val = safe_int(parent_metrics['heart_rate'])
                            if hr_val > 0:
                                self.update_metric('heart_rate', hr_val)
                                self.update_metric('rr_interval', int(60000 / hr_val) if hr_val > 0 else 0)
                        
                        # Update PR Interval
                        if 'pr_interval' in parent_metrics:
                            pr_val = safe_int(parent_metrics['pr_interval'])
                            if pr_val > 0:
                                self.update_metric('pr_interval', pr_val)
                        
                        # Update QRS Duration
                        if 'qrs_duration' in parent_metrics:
                            qrs_val = safe_int(parent_metrics['qrs_duration'])
                            if qrs_val > 0:
                                self.update_metric('qrs_duration', qrs_val)
                        
                        # Update P Duration (stored in 'st_interval' label - P replaced ST in display)
                        # Check multiple sources: 'p_duration', 'st_interval', or parent's last_p_duration attribute
                        p_val = None
                        if 'p_duration' in parent_metrics:
                            p_val = safe_int(parent_metrics['p_duration'])
                        elif 'st_interval' in parent_metrics:
                            # P duration is stored in st_interval label (P replaced ST)
                            st_val = parent_metrics['st_interval']
                            p_val = safe_int(st_val)
                        
                        # Fallback: Try to get from parent's last_p_duration attribute directly
                        if (p_val is None or p_val == 0) and hasattr(parent, 'last_p_duration'):
                            try:
                                p_val = int(parent.last_p_duration) if parent.last_p_duration else 0
                            except:
                                pass
                        
                        # Update P duration if we found a value (update even if 0 to show current state)
                        if p_val is not None:
                            self.update_metric('p_duration', p_val)
                        
                        # Update QTc Interval
                        if 'qtc_interval' in parent_metrics:
                            qtc_val = parent_metrics['qtc_interval']
                            if isinstance(qtc_val, str) and '/' in qtc_val:
                                # Extract QTc value (second part)
                                qtc_val = qtc_val.split('/')[-1]
                            qtc_int = safe_int(qtc_val)
                            if qtc_int > 0:
                                self.update_metric('qtc_interval', qtc_int)
                        
                        # If we successfully got metrics from parent, return early
                        # This ensures exact match with dashboard values for Lead II
                        return
                except Exception as e:
                    print(f" Error getting parent metrics for Lead II: {e}")
                    # Fall through to calculate independently if parent metrics unavailable
            
            # For all other leads (I, III, aVR, aVL, aVF, V1-V6): Calculate independently from their own data
            # Each lead calculates its own metrics from its own waveform
            r_peaks, p_peaks, q_peaks, s_peaks, t_peaks = (
                analysis['r_peaks'], analysis['p_peaks'], analysis['q_peaks'],
                analysis['s_peaks'], analysis['t_peaks']
            )
            
            # Heart Rate & RR Interval - use same calculation as 12-lead page if available
            # 🫀 CLINICAL: Calculate metrics from RAW clinical data (self.ecg_data)
            # self.ecg_data comes from parent.data[lead_index] which is raw, not display-processed
            heart_rate = 0
            if parent is not None and hasattr(parent, 'calculate_heart_rate'):
                try:
                    # Pass raw clinical data to parent's calculation function
                    heart_rate = int(parent.calculate_heart_rate(self.ecg_data))
                    self.update_metric('heart_rate', max(0, heart_rate))
                    self.update_metric('rr_interval', int(60000 / heart_rate) if heart_rate > 0 else 0)
                except Exception:
                    heart_rate = 0
            else:
                # Calculate from R-peaks detected in raw clinical data
                if len(r_peaks) > 1:
                    rr_intervals = np.diff(r_peaks) / self.sampling_rate * 1000
                    mean_rr = np.mean(rr_intervals)
                    heart_rate = 60000 / mean_rr if mean_rr > 0 else 0
                    self.update_metric('heart_rate', int(heart_rate))
                    self.update_metric('rr_interval', int(mean_rr))
            
            # PR Interval and QRS Duration - Use median beat method for ALL leads when possible
            # For each lead, calculate metrics from its own data using median beat analysis
            median_beat = None
            time_axis = None
            tp_baseline = None
            
            # Try to build median beat for this lead's data (works for all leads)
            if build_median_beat is not None and len(r_peaks) >= 8:
                try:
                    # Calculate HR to determine min_beats (Fixed Bug P-2: Lower requirement for high BPM)
                    rr_intervals = np.diff(r_peaks) / self.sampling_rate
                    mean_rr = np.mean(rr_intervals) if len(rr_intervals) > 0 else 0.8
                    hr_est = 60 / mean_rr if mean_rr > 0 else 75
                    min_beats_req = 4 if hr_est > 150 else 8

                    # Build median beats from this lead's raw clinical data
                    time_axis, median_beat = build_median_beat(self.ecg_data, r_peaks, self.sampling_rate, min_beats=min_beats_req)
                    if median_beat is not None:
                        # Get TP baseline for this lead
                        r_mid = r_peaks[len(r_peaks) // 2]
                        prev_r_idx = r_peaks[len(r_peaks) // 2 - 1] if len(r_peaks) > 1 else None
                        tp_baseline = get_tp_baseline(self.ecg_data, r_mid, self.sampling_rate, prev_r_peak_idx=prev_r_idx)
                except Exception as e:
                    print(f" Error building median beat for {self.lead_name}: {e}")
                    median_beat = None
            
            # PR Interval calculation
            if median_beat is not None and measure_pr_from_median_beat is not None:
                try:
                    # Calculate PR using standardized function (same as 12-lead test page)
                    rr_ms = None
                    try:
                        if len(r_peaks) >= 2:
                            rr_ms = float(np.median(np.diff(r_peaks) / self.sampling_rate * 1000.0))
                    except Exception:
                        rr_ms = None

                    pr_interval = measure_pr_from_median_beat(
                        median_beat, time_axis, self.sampling_rate, tp_baseline,
                        rr_ms=rr_ms
                    )
                    if pr_interval and pr_interval > 0:
                        self.update_metric('pr_interval', pr_interval)
                    else:
                        # Fallback to simple method if standardized fails
                        if len(p_peaks) > 0 and len(q_peaks) > 0:
                            pr_intervals = [(q - p) / self.sampling_rate * 1000 for p, q in zip(p_peaks, q_peaks) if q > p]
                            if pr_intervals:
                                self.update_metric('pr_interval', int(np.mean(pr_intervals)))
                except Exception as e:
                    print(f" Error calculating PR from median beat in expanded view: {e}")
                    # Fallback to simple method
                    if len(p_peaks) > 0 and len(q_peaks) > 0:
                        pr_intervals = [(q - p) / self.sampling_rate * 1000 for p, q in zip(p_peaks, q_peaks) if q > p]
                        if pr_intervals:
                            self.update_metric('pr_interval', int(np.mean(pr_intervals)))
            else:
                # For other leads or if median beat not available, use simple method
                if len(p_peaks) > 0 and len(q_peaks) > 0:
                    pr_intervals = [(q - p) / self.sampling_rate * 1000 for p, q in zip(p_peaks, q_peaks) if q > p]
                    if pr_intervals:
                        self.update_metric('pr_interval', int(np.mean(pr_intervals)))
            
            # QRS Duration calculation
            if median_beat is not None and measure_qrs_duration_from_median_beat is not None:
                try:
                    # Calculate QRS using standardized function (same as 12-lead test page)
                    qrs_duration = measure_qrs_duration_from_median_beat(median_beat, time_axis, self.sampling_rate, tp_baseline)
                    if qrs_duration and qrs_duration > 0:
                        self.update_metric('qrs_duration', qrs_duration)
                    else:
                        # Fallback to simple method if standardized fails
                        if len(q_peaks) > 0 and len(s_peaks) > 0:
                            qrs_durations = [(s - q) / self.sampling_rate * 1000 for q, s in zip(q_peaks, s_peaks) if s > q]
                            if qrs_durations:
                                self.update_metric('qrs_duration', int(np.mean(qrs_durations)))
                except Exception as e:
                    print(f" Error calculating QRS from median beat in expanded view: {e}")
                    # Fallback to simple method
                    if len(q_peaks) > 0 and len(s_peaks) > 0:
                        qrs_durations = [(s - q) / self.sampling_rate * 1000 for q, s in zip(q_peaks, s_peaks) if s > q]
                        if qrs_durations:
                            self.update_metric('qrs_duration', int(np.mean(qrs_durations)))
            else:
                # For other leads or if median beat not available, use simple method
                if len(q_peaks) > 0 and len(s_peaks) > 0:
                    qrs_durations = [(s - q) / self.sampling_rate * 1000 for q, s in zip(q_peaks, s_peaks) if s > q]
                    if qrs_durations:
                        self.update_metric('qrs_duration', int(np.mean(qrs_durations)))
            
            # QTc Interval (Bazett's formula) using measured QT (if available)
            if 'rr_interval' in self.metrics_cards and self.metrics_cards['rr_interval'].value > 0:
                rr_sec = self.metrics_cards['rr_interval'].value / 1000.0
                # Estimate QT as mean (T − Q) over detected beats
                qt_intervals = []
                for q_idx, t_idx in zip(q_peaks, t_peaks):
                    if t_idx > q_idx:
                        qt_ms = (t_idx - q_idx) / self.sampling_rate * 1000.0
                        # Accept only physiologic QT (e.g., 240–520 ms)
                        if 240.0 <= qt_ms <= 520.0:
                            qt_intervals.append(qt_ms)
                if qt_intervals and rr_sec > 0:
                    qt_interval_ms = float(np.median(qt_intervals))
                    qtc = qt_interval_ms / np.sqrt(rr_sec)
                    self.update_metric('qtc_interval', int(round(qtc)))

            # P Duration (estimate from P-wave width around detected P peaks)
            try:
                if len(p_peaks) > 0:
                    filtered = self.analyzer._filter_signal(self.ecg_data)
                    p_durations = []
                filtered = self.analyzer._filter_signal(self.ecg_data)
                p_duration_val = self.calculate_p_duration(p_peaks, filtered)
                if p_duration_val > 0:
                    self.update_metric('p_duration', p_duration_val)
            except Exception as _:
                # Fallback if anything fails; do not block other metrics
                pass
            
        except Exception as e:
            print(f"Error calculating metrics: {e}")
    
    def update_metric(self, metric_name, value):
        """Update a specific metric card"""
        if metric_name in self.metrics_cards:
            self.metrics_cards[metric_name].update_value(value)
    
    def _normalize_arrhythmia_labels_for_display(self, arrhythmias):
        """
        Match the main ECG screen's simple rate-only interpretation rule.

        This is intentionally a display-layer normalization only. The detector
        still runs unchanged, but the expanded view summary follows the same
        user-facing rule as the main ECG page:
        - HR > 100 -> Tachycardia
        - HR < 60  -> Bradycardia
        - otherwise -> Normal Sinus Rhythm
        """
        try:
            parent = self._parent if hasattr(self, '_parent') else None
            hr_value = None

            if parent is not None and hasattr(parent, 'get_current_metrics'):
                metrics = parent.get_current_metrics() or {}
                raw_hr = metrics.get('heart_rate', 0)
                hr_text = str(raw_hr).replace('BPM', '').strip()
                if hr_text and hr_text not in ('--', 'None'):
                    hr_value = float(hr_text)

            if (hr_value is None or hr_value <= 0) and parent is not None:
                hr_value = float(getattr(parent, 'last_heart_rate', 0) or 0)

            if hr_value is None or hr_value <= 0:
                return arrhythmias

            if hr_value > 100:
                return ["Tachycardia"]
            if hr_value < 60:
                return ["Bradycardia"]
            return ["Normal Sinus Rhythm"]
        except Exception:
            return arrhythmias
    
    def update_arrhythmia_display(self, arrhythmias):
        """Update the arrhythmia display"""
        arrhythmias = self._normalize_arrhythmia_labels_for_display(arrhythmias)
        arrhythmia_text = ", ".join(arrhythmias) if arrhythmias else "No specific arrhythmia detected."
        self.arrhythmia_list.setText(arrhythmia_text)
        self._save_arrhythmia_findings_for_report(arrhythmias)
        
        # Keep parent ECG page's rhythm interpretation in sync for dashboard conclusions
        if hasattr(self, '_parent') and self._parent is not None:
            try:
                setattr(self._parent, '_latest_rhythm_interpretation', arrhythmia_text)
            except Exception:
                pass

            # Refresh the dashboard interpretation immediately so the dashboard card
            # follows the same live arrhythmia text as the expanded view.
            try:
                dashboard = getattr(self._parent, 'dashboard_instance', None)
                if dashboard is not None and hasattr(dashboard, 'update_live_conclusion'):
                    dashboard.update_live_conclusion()
            except Exception:
                pass
        
        # Color code based on severity
        abnormal_keywords = (
            "Block", "Fibrillation", "Flutter", "Tachycardia", "Bradycardia",
            "PVC", "PAC", "Wide QRS", "Prolonged", "Short"
        )
        is_normal = (
            "Normal Sinus Rhythm" in arrhythmia_text
            and not any(keyword in arrhythmia_text for keyword in abnormal_keywords)
        )
        self.arrhythmia_list.setStyleSheet(f"""
            color: {'#2ecc71' if is_normal else '#e74c3c'};
            font-weight: bold;
            border: none;
        """)

    def _save_arrhythmia_findings_for_report(self, arrhythmias):
        """Persist expanded-view findings so the PDF report uses the same diagnosis."""
        try:
            import json
            import os
            from utils.app_paths import data_file
            from datetime import datetime

            findings = []
            for item in arrhythmias or []:
                for part in str(item).split(","):
                    label = part.strip()
                    if label and label not in findings:
                        findings.append(label)

            # ── Lethal rhythm short-circuit ──────────────────────────────────
            # When Asystole / VF / VT is the primary diagnosis, save ONLY that
            # label.  No secondary findings (Wide QRS, etc.) should be
            # stored alongside — they are meaningless on a flat/absent signal.
            _LETHAL = {"Asystole", "Ventricular Fibrillation", "Ventricular Tachycardia"}
            if findings and findings[0] in _LETHAL:
                findings = [findings[0]]

            abnormal_keywords = (
                "Block", "Fibrillation", "Flutter", "Tachycardia", "Bradycardia",
                "PVC", "PAC", "Wide QRS", "Prolonged", "Short", "Asystole"
            )
            has_abnormal = any(
                any(keyword.lower() in label.lower() for keyword in abnormal_keywords)
                for label in findings
            )
            if has_abnormal:
                findings = [label for label in findings if label != "Normal Sinus Rhythm"]

            if not findings:
                return

            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            conclusions_file = str(data_file("last_conclusions.json"))
            with open(conclusions_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "expanded_lead_view",
                        "findings": findings,
                        "recommendations": [],
                    },
                    f,
                    indent=2,
                )
        except Exception as exc:
            print(f" Error saving expanded arrhythmia findings: {exc}")
    
    def update_plot_with_markers(self, analysis):
        """Clear any optional PQRST marker overlay (pyqtgraph path)."""
        if self.ecg_data.size == 0:
            return

        try:
            if hasattr(self, 'marker_curve'):
                self.marker_curve.setData([], [])
        except Exception as e:
            print(f"Error updating plot markers: {e}")

    def prepare_heatmap_overlay(self, heat_map_data):
        """Convert arrhythmia probabilities into a background overlay and record event times."""
        # Clear previous events each time we recompute the heatmap
        self.arrhythmia_events = []

        colors = {
            "Normal Sinus Rhythm": "#2ecc71",
            "Atrial Fibrillation": "#e74c3c",
            "Ventricular Tachycardia": "#8e44ad",
            "Premature Ventricular Contractions": "#f39c12",
            "Sinus Bradycardia": "#3498db",
            "Sinus Tachycardia": "#e67e22",
            "Irregular Rhythm": "#95a5a6"
        }
        arrhythmia_types = list(colors.keys())

        if not heat_map_data:
            self.heatmap_overlay = None
            self.heatmap_time_axis = None
            return

        # Pick any available series to establish window count/time axis
        base_series = None
        for arr_type in arrhythmia_types:
            series = heat_map_data.get(arr_type)
            if series:
                base_series = series
                break

        if not base_series:
            self.heatmap_overlay = None
            self.heatmap_time_axis = None
            return

        num_windows = len(base_series)
        overlay = np.ones((120, num_windows, 4))
        time_axis = []

        for idx in range(num_windows):
            time_value = base_series[idx][0] if idx < len(base_series) else idx * 2.0
            time_axis.append(time_value)
            
            best_type = "Irregular Rhythm"
            best_prob = 0.0
            for arr_type in arrhythmia_types:
                arr_list = heat_map_data.get(arr_type, [])
                if idx < len(arr_list):
                    _, prob = arr_list[idx]
                    if prob > best_prob:
                        best_prob = prob
                        best_type = arr_type

            color_hex = colors.get(best_type, "#95a5a6")
            rgb = tuple(int(color_hex[i:i+2], 16) / 255.0 for i in (1, 3, 5))
            opacity = 0.2 + 0.8 * max(0.0, min(1.0, best_prob))
            overlay[:, idx, 0] = rgb[0]
            overlay[:, idx, 1] = rgb[1]
            overlay[:, idx, 2] = rgb[2]
            overlay[:, idx, 3] = opacity

            # Record an arrhythmia event when a non-normal rhythm dominates this window
            if best_type != "Normal Sinus Rhythm" and best_prob >= 0.7:
                self.arrhythmia_events.append((float(time_value), best_type))
        self.heatmap_overlay = overlay
        self.heatmap_time_axis = np.array(time_axis)
        if len(self.heatmap_time_axis) > 1:
            diffs = np.diff(self.heatmap_time_axis)
            self.heatmap_window_step = max(0.1, float(np.median(diffs)))
        else:
            self.heatmap_window_step = 2.0

    def update_history_slider(self):
        """Adjust slider bounds to match available history"""
        if not hasattr(self, 'history_slider'):
            return
        total_duration = len(self.ecg_data) / max(1.0, self.sampling_rate)
        max_offset = max(0.0, total_duration - self.view_window_duration)
        slider_max = int(max_offset * 1000)
        current_val = int(min(self.view_window_offset, max_offset) * 1000)
        
        self.history_slider.blockSignals(True)
        self.history_slider.setMaximum(slider_max)
        self.history_slider.setValue(current_val)
        self.history_slider.setEnabled(True)  # Ensure slider is enabled
        self.history_slider.blockSignals(False)

        if self.history_slider_label:
            if not self.history_slider_active:
                self.history_slider_label.setText("LIVE")
            else:
                start_time = min(self.view_window_offset, max_offset)
                end_time = min(start_time + self.view_window_duration, total_duration)
                self.history_slider_label.setText(f"{start_time:0.1f}s – {end_time:0.1f}s")

    
    def on_history_slider_changed(self, value):
        """Scroll through historical data - works anytime"""
        # print(f" History slider changed to: {value}")
        self.manual_view = True
        self.history_slider_active = True  # Enable manual control
        self.view_window_offset = value / 1000.0
        # print(f" View window offset set to: {self.view_window_offset:.2f}s")
        self.update_plot()
        if self.history_slider_label:
            total_duration = len(self.ecg_data) / max(1.0, self.sampling_rate)
            start_time = max(0.0, min(self.view_window_offset, total_duration))
            end_time = min(start_time + self.view_window_duration, total_duration)
            self.history_slider_label.setText(f"{start_time:0.1f}s – {end_time:0.1f}s")
            # print(f" Showing window: {start_time:.1f}s - {end_time:.1f}s")
    
    def return_to_live_view(self):
        """Return to live view (most recent data)"""
        # print(" Returning to LIVE view")
        self.manual_view = False
        self.history_slider_active = False
        if self.history_slider_label:
            self.history_slider_label.setText("LIVE")
        # Update plot to show latest data
        if len(self.ecg_data) > 0:
            total_duration = len(self.ecg_data) / max(1.0, self.sampling_rate)
            self.view_window_offset = max(0.0, total_duration - self.view_window_duration)
            self.update_plot()
            self.update_history_slider()
def show_expanded_lead_view(lead_name, ecg_data, sampling_rate=500, parent=None):
    """Show the expanded lead view dialog"""
    dialog = ExpandedLeadView(lead_name, ecg_data, sampling_rate, parent)
    # Open maximized by default for best visibility on any monitor
    dialog.showMaximized()
    dialog.show()  # Non-modal: main window stays visible

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Create more realistic sample ECG data
    fs = 500
    duration = 5 # seconds
    t = np.linspace(0, duration, duration * fs, endpoint=False)
    
    # P wave
    p_wave = 0.1 * np.exp(-((t % 1 - 0.25)**2) / 0.005)
    # QRS complex
    qrs_complex = 1.0 * np.exp(-((t % 1 - 0.4)**2) / 0.002) - 0.3 * np.exp(-((t % 1 - 0.37)**2) / 0.001) - 0.2 * np.exp(-((t % 1 - 0.43)**2) / 0.001)
    # T wave
    t_wave = 0.3 * np.exp(-((t % 1 - 0.6)**2) / 0.01)
    # Noise
    noise = 0.03 * np.random.randn(len(t))
    
    sample_ecg = p_wave + qrs_complex + t_wave + noise
    
    dialog = ExpandedLeadView("Lead II", sample_ecg, fs)
    dialog.showMaximized()
    
    sys.exit(app.exec_())
