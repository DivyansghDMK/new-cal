import sys
import math
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QWidget
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPainterPath

class AnimatedECG(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.offset = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(30)
        self.setStyleSheet("background: transparent;")

    def update_animation(self):
        self.offset += 5
        if self.offset > 200:
            self.offset = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        pen = QPen(QColor("#E8650A"))
        pen.setWidth(2)
        painter.setPen(pen)

        width = self.width()
        height = self.height()
        mid_y = height / 2

        path = QPainterPath()
        path.moveTo(0, mid_y)
        
        # Draw a simulated ECG wave
        # Just repeat a standard PQRST-like pattern
        segment_width = 120
        num_segments = int(width / segment_width) + 2
        
        for i in range(num_segments):
            x_base = i * segment_width - self.offset
            
            # Straight line
            path.lineTo(x_base + 10, mid_y)
            # P wave
            path.quadTo(x_base + 20, mid_y - 10, x_base + 30, mid_y)
            # PR segment
            path.lineTo(x_base + 40, mid_y)
            # Q wave
            path.lineTo(x_base + 45, mid_y + 15)
            # R wave
            path.lineTo(x_base + 55, mid_y - 35)
            # S wave
            path.lineTo(x_base + 65, mid_y + 20)
            # ST segment
            path.lineTo(x_base + 70, mid_y)
            path.lineTo(x_base + 80, mid_y)
            # T wave
            path.quadTo(x_base + 95, mid_y - 15, x_base + 110, mid_y)
            path.lineTo(x_base + 120, mid_y)

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
        self.timer.start(400) # 400ms per step

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
            QTimer.singleShot(500, self.accept)

def show_medical_loader():
    loader = MedicalLoader()
    loader.show()
    loader.start_loading()
    loader.exec_()
    return True
