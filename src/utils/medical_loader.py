import sys
import math
import time as _time
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QWidget
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPainterPath, QLinearGradient


class AnimatedECG(QWidget):
    """Smooth, time-based ECG scrolling animation.

    The wave offset is derived from ``time.monotonic()`` so the position is
    always mathematically correct for the real elapsed time — even when the
    main thread is blocked constructing the Dashboard and timer callbacks are
    delayed or dropped.  The animation will never appear to *stutter*; it may
    skip frames, but each rendered frame is always in the right position.
    """

    # Pixels per second the wave scrolls across the widget
    SCROLL_SPEED = 120          # px / s
    SEGMENT_WIDTH = 140         # px  — one complete PQRST cycle
    TIMER_INTERVAL_MS = 16      # ~60 fps target; fine even at lower actual fps

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(88)
        self.setStyleSheet("background: transparent;")
        self._start_time = _time.monotonic()

        # Repaint trigger — we don't accumulate offset here; paintEvent does it.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(self.TIMER_INTERVAL_MS)

    # ------------------------------------------------------------------
    def _compute_offset(self):
        """Return the current scroll offset in pixels based on wall-clock time."""
        elapsed = _time.monotonic() - self._start_time
        total_px = elapsed * self.SCROLL_SPEED
        return total_px % self.SEGMENT_WIDTH   # wrap within one cycle

    # ------------------------------------------------------------------
    def _build_ecg_path(self, offset, width, mid_y):
        """Return a QPainterPath for the scrolling ECG wave."""
        sw = self.SEGMENT_WIDTH
        # How many full segments do we need to cover the widget + 1 extra on each side
        num_segments = int(width / sw) + 3
        # Starting segment so that `offset` creates the illusion of continuous scroll
        start_x = -offset - sw   # one segment to the left so the wave enters smoothly

        path = QPainterPath()
        first = True

        for i in range(num_segments):
            x = start_x + i * sw

            # Each segment: baseline → P → PR → Q → R → S → ST → T → baseline
            pts = [
                (x,          mid_y),           # start baseline
                (x + 12,     mid_y),           # pre-P flat
                # P wave (smooth bump)
                (x + 18,     mid_y - 9),
                (x + 22,     mid_y - 12),
                (x + 26,     mid_y - 9),
                (x + 32,     mid_y),           # post-P flat
                (x + 42,     mid_y),           # PR segment
                # Q dip
                (x + 47,     mid_y + 8),
                # R peak  (tall spike)
                (x + 56,     mid_y - 42),
                # S trough
                (x + 64,     mid_y + 14),
                # ST segment
                (x + 72,     mid_y),
                (x + 82,     mid_y),
                # T wave (smooth hump)
                (x + 92,     mid_y - 7),
                (x + 102,    mid_y - 14),
                (x + 112,    mid_y - 7),
                (x + sw,     mid_y),           # back to baseline
            ]

            if first:
                path.moveTo(pts[0][0], pts[0][1])
                first = False
            else:
                path.lineTo(pts[0][0], pts[0][1])

            # Draw each segment — use quadTo for smooth P and T waves
            path.lineTo(pts[1][0], pts[1][1])
            path.quadTo(pts[2][0], pts[2][1], pts[3][0], pts[3][1])
            path.quadTo(pts[4][0], pts[4][1], pts[5][0], pts[5][1])
            path.lineTo(pts[6][0], pts[6][1])   # PR flat
            path.lineTo(pts[7][0], pts[7][1])   # Q
            path.lineTo(pts[8][0], pts[8][1])   # R peak
            path.lineTo(pts[9][0], pts[9][1])   # S
            path.lineTo(pts[10][0], pts[10][1]) # ST
            path.lineTo(pts[11][0], pts[11][1])
            path.quadTo(pts[12][0], pts[12][1], pts[13][0], pts[13][1])
            path.quadTo(pts[14][0], pts[14][1], pts[15][0], pts[15][1])

        return path

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        mid_y = h / 2
        offset = self._compute_offset()

        path = self._build_ecg_path(offset, w, mid_y)

        # ── Glow / shadow pass (wider, semi-transparent) ──
        glow_pen = QPen(QColor(232, 101, 10, 60))   # orange, very transparent
        glow_pen.setWidth(6)
        glow_pen.setCapStyle(Qt.RoundCap)
        glow_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(glow_pen)
        painter.drawPath(path)

        # ── Main line pass ──
        main_pen = QPen(QColor("#E8650A"))
        main_pen.setWidthF(2.2)
        main_pen.setCapStyle(Qt.RoundCap)
        main_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(main_pen)
        painter.drawPath(path)

class MedicalLoader(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(650, 480)

        self.steps = [
            "Device connection check",
            "Loading patient database",
            "Signal processing engine",
            "Arrhythmia detection modules",
            "License verification"
        ]
        self.current_step = 0
        self.labels = []

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget(self)
        main_widget.setFixedSize(650, 480)
        main_widget.setStyleSheet("""
            QWidget {
                background-color: #0F0F0F;
                border-radius: 12px;
                border: 1px solid #2a2a2a;
            }
        """)

        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(40, 40, 40, 30)
        layout.setSpacing(15)

        # Logo / Title
        title_layout = QHBoxLayout()
        logo = QLabel("CardioX")
        logo.setStyleSheet("color: white; font-size: 32px; font-weight: bold; background: transparent; border: none;")
        
        icon_lbl = QLabel(" ⚡ ")
        icon_lbl.setStyleSheet("color: white; background-color: #E8650A; border-radius: 8px; font-size: 24px; padding: 4px; border: none;")
        
        title_layout.addStretch()
        title_layout.addWidget(icon_lbl)
        title_layout.addWidget(logo)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        subtitle = QLabel("ECG MONITOR  ·  MEDICAL EDITION")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #888888; font-size: 12px; letter-spacing: 2px; background: transparent; border: none;")
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Animated ECG
        self.ecg_anim = AnimatedECG()
        layout.addWidget(self.ecg_anim)

        # Status
        self.status_lbl = QLabel("Initializing system...")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet("color: #E8650A; font-size: 14px; background: transparent; border: none;")
        layout.addWidget(self.status_lbl)

        layout.addSpacing(10)

        # Checklist
        check_layout = QVBoxLayout()
        check_layout.setContentsMargins(100, 0, 100, 0)
        check_layout.setSpacing(8)
        
        for step in self.steps:
            row = QHBoxLayout()
            icon = QLabel("○")
            icon.setStyleSheet("color: #555555; font-size: 16px; background: transparent; border: none;")
            text = QLabel(step)
            text.setStyleSheet("color: #888888; font-size: 13px; background: transparent; border: none;")
            row.addWidget(icon)
            row.addWidget(text)
            row.addStretch()
            check_layout.addLayout(row)
            self.labels.append((icon, text))

        layout.addLayout(check_layout)
        
        layout.addStretch()

        # Badges at bottom
        badges_layout = QHBoxLayout()
        badges_layout.setSpacing(20)
        badges = ["⛨ IEC 62304 compliant", "🔒 Encrypted session", "✓ CE marked"]
        badges_layout.addStretch()
        for b in badges:
            lbl = QLabel(b)
            lbl.setStyleSheet("color: #555555; font-size: 11px; background: transparent; border: none;")
            badges_layout.addWidget(lbl)
        badges_layout.addStretch()
        layout.addLayout(badges_layout)

    def start_loading(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.progress_step)
        self.timer.start(60) # 60ms per step

    def progress_step(self):
        if self.current_step < len(self.steps):
            # Mark current step as done
            icon, text = self.labels[self.current_step]
            icon.setText("✓")
            icon.setStyleSheet("color: #2ecc71; font-size: 16px; font-weight: bold; background: transparent; border: none;")
            text.setStyleSheet("color: #dddddd; font-size: 13px; background: transparent; border: none;")
            
            self.status_lbl.setText(f"Loading: {self.steps[self.current_step]}...")
            self.current_step += 1
        else:
            self.timer.stop()
            self.status_lbl.setText("Ready. Launching dashboard...")
            QTimer.singleShot(100, self.accept)

    def finish_and_close(self, target_window=None):
        """Mark all steps complete, show 'Ready' status, then close after a short delay.
        Call this right before showing the dashboard to give a clean hand-off."""
        try:
            if hasattr(self, 'timer') and self.timer is not None:
                self.timer.stop()
        except Exception:
            pass
        # Mark all remaining steps as done instantly
        for idx in range(self.current_step, len(self.steps)):
            try:
                icon, text = self.labels[idx]
                icon.setText("✓")
                icon.setStyleSheet("color: #2ecc71; font-size: 16px; font-weight: bold; background: transparent; border: none;")
                text.setStyleSheet("color: #dddddd; font-size: 13px; background: transparent; border: none;")
            except Exception:
                pass
        try:
            self.status_lbl.setText("Dashboard ready — opening now...")
        except Exception:
            pass
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
        # Small delay so user can read the "ready" message, then close
        QTimer.singleShot(300, self.close)

def show_medical_loader():
    """Blocking loader — shows and waits for all steps to complete."""
    loader = MedicalLoader()
    loader.show()
    loader.start_loading()
    loader.exec_()
    return True


def show_medical_loader_nonblocking():
    """Non-blocking loader — returns the loader instance immediately while it animates.
    
    The caller is responsible for calling ``loader.finish_and_close()`` once the
    dashboard (or whatever heavy work) is ready to be shown.  This keeps the
    loading screen visible during the entire construction window so there is no
    blank-screen gap between login and the dashboard.
    """
    from PyQt5.QtWidgets import QApplication
    loader = MedicalLoader()
    loader.show()
    loader.start_loading()
    # Let the UI paint before returning so the window is visible immediately
    QApplication.processEvents()
    return loader
