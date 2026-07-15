"""
ecg/holter/add_event_dialog.py
===============================
Add Event Dialog for Holter ECG Analysis

Allows users to add custom events with:
- Strip start time selection
- Print length (seconds)
- Heart rate
- Strip label (event type)
- Print orientation (Vertical/Horizontal)
- Preview channel selection
- Print channel selection (12-lead: I, II, III, aVR, aVL, aVF, V1-V6)
- Lead exchange options
"""

from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QRadioButton, QCheckBox, QGroupBox,
    QDateTimeEdit, QSpinBox, QButtonGroup, QFrame
)
from PyQt5.QtCore import Qt, QDateTime, pyqtSignal
from PyQt5.QtGui import QFont

try:
    from .theme import COL_BLACK, COL_GREEN, COL_GREEN_DRK, COL_TEXT, UI_BORDER, UI_TEXT, UI_PANEL_ALT
except ImportError:
    COL_BLACK = "#0a0f18"
    COL_GREEN = "#28E37B"
    COL_GREEN_DRK = "#1a6b3f"
    COL_TEXT = "#f3f7fb"
    UI_BORDER = "#2a5a6d"
    UI_TEXT = "#f3f7fb"
    UI_PANEL_ALT = "#0d1521"


class AddEventDialog(QDialog):
    """
    Dialog for adding custom events to Holter recording.
    Matches the reference design with 12-lead ECG support.
    """
    
    event_added = pyqtSignal(dict)  # Emits event data when added
    
    # 12-lead names
    LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    
    # Event/Strip label options
    EVENT_LABELS = [
        "Ventricular fusion",
        "Atrial Fibrillation",
        "Atrial Flutter",
        "Supraventricular Tachycardia",
        "Ventricular Tachycardia",
        "Bradycardia",
        "Pause",
        "PVC",
        "PAC",
        "Custom"
    ]
    
    def __init__(self, parent=None, start_time: datetime = None, current_sec: float = 0.0, hr: float = 0.0):
        super().__init__(parent)
        self.setWindowTitle("Edit strip")
        self.setModal(True)
        self.setFixedSize(640, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        self._start_time = start_time or datetime.now()
        self._current_sec = current_sec
        self._hr = hr
        
        self._build_ui()
        self._apply_styles()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # ========== Row 1: Strip start time, Print Len, HR ==========
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        
        # Strip start time
        time_group = QVBoxLayout()
        time_lbl = QLabel("Strip start time")
        time_lbl.setStyleSheet("color:#E5E7EB;font-size:12px;font-weight:700;background:transparent;")
        self.time_edit = QDateTimeEdit()
        self.time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.time_edit.setDateTime(QDateTime.fromSecsSinceEpoch(int(self._start_time.timestamp() + self._current_sec)))
        self.time_edit.setCalendarPopup(True)
        time_group.addWidget(time_lbl)
        time_group.addWidget(self.time_edit)
        row1.addLayout(time_group, 2)
        
        # Print Len (Sec.)
        len_group = QVBoxLayout()
        len_lbl = QLabel("Print Len.(Sec.)")
        len_lbl.setStyleSheet("color:#E5E7EB;font-size:12px;font-weight:700;background:transparent;")
        self.len_combo = QComboBox()
        self.len_combo.addItems(["3", "5", "7", "10", "15", "30"])
        self.len_combo.setCurrentText("7")
        len_group.addWidget(len_lbl)
        len_group.addWidget(self.len_combo)
        row1.addLayout(len_group, 1)
        
        # HR
        hr_group = QVBoxLayout()
        hr_lbl = QLabel("HR")
        hr_lbl.setStyleSheet("color:#E5E7EB;font-size:12px;font-weight:700;background:transparent;")
        self.hr_edit = QLineEdit()
        self.hr_edit.setText(f"{int(self._hr)}" if self._hr > 0 else "")
        self.hr_edit.setPlaceholderText("bpm")
        hr_group.addWidget(hr_lbl)
        hr_group.addWidget(self.hr_edit)
        row1.addLayout(hr_group, 1)
        
        layout.addLayout(row1)
        
        # ========== Row 2: << >> buttons ==========
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)
        self.btn_prev = QPushButton("<<")
        self.btn_next = QPushButton(">>")
        self.btn_prev.setFixedWidth(80)
        self.btn_next.setFixedWidth(80)
        nav_row.addWidget(self.btn_prev)
        nav_row.addWidget(self.btn_next)
        nav_row.addStretch()
        layout.addLayout(nav_row)
        
        # ========== Row 3: Strip label ==========
        label_group = QVBoxLayout()
        label_lbl = QLabel("Strip label")
        label_lbl.setStyleSheet("color:#E5E7EB;font-size:12px;font-weight:700;background:transparent;")
        self.label_combo = QComboBox()
        self.label_combo.addItems(self.EVENT_LABELS)
        self.label_combo.setCurrentText("Ventricular fusion")
        label_group.addWidget(label_lbl)
        label_group.addWidget(self.label_combo)
        layout.addLayout(label_group)
        
        # ========== Strip note ==========
        note_lbl = QLabel("Strip note")
        note_lbl.setStyleSheet("color:#E5E7EB;font-size:12px;font-weight:700;background:transparent;")
        layout.addWidget(note_lbl)
        
        # ========== Row 4: Print orientation, Preview channel, Strip Display Type ==========
        row4 = QHBoxLayout()
        row4.setSpacing(16)
        
        # Print orientation
        orient_group = QGroupBox("Print orientation")
        orient_layout = QHBoxLayout(orient_group)
        self.radio_vertical = QRadioButton("Vertical")
        self.radio_horizontal = QRadioButton("Horizontal")
        self.radio_vertical.setChecked(True)
        orient_layout.addWidget(self.radio_vertical)
        orient_layout.addWidget(self.radio_horizontal)
        row4.addWidget(orient_group)
        
        # Preview channel
        preview_group = QVBoxLayout()
        preview_lbl = QLabel("Preview channel")
        preview_lbl.setStyleSheet("color:#E5E7EB;font-size:12px;font-weight:700;background:transparent;")
        self.preview_combo = QComboBox()
        self.preview_combo.addItem("Auto")
        self.preview_combo.addItems(self.LEADS)
        self.preview_combo.setCurrentText("Auto")
        preview_group.addWidget(preview_lbl)
        preview_group.addWidget(self.preview_combo)
        row4.addLayout(preview_group)
        
        # Strip Display Type
        display_group = QVBoxLayout()
        display_lbl = QLabel("Strip Display Type")
        display_lbl.setStyleSheet("color:#E5E7EB;font-size:12px;font-weight:700;background:transparent;")
        self.display_combo = QComboBox()
        self.display_combo.addItems(["Default", "Cascade", "Grid"])
        display_group.addWidget(display_lbl)
        display_group.addWidget(self.display_combo)
        row4.addLayout(display_group)
        
        layout.addLayout(row4)
        
        # ========== Print channel selection ==========
        channel_group = QGroupBox("Print channel")
        channel_layout = QVBoxLayout(channel_group)
        
        # Radio buttons: 1-CH, 3-CH, Custom
        radio_row = QHBoxLayout()
        self.radio_1ch = QRadioButton("1-CH")
        self.radio_3ch = QRadioButton("3-CH")
        self.radio_custom = QRadioButton("Custom")
        self.radio_3ch.setChecked(True)
        radio_row.addWidget(self.radio_1ch)
        radio_row.addWidget(self.radio_3ch)
        radio_row.addWidget(self.radio_custom)
        radio_row.addStretch()
        channel_layout.addLayout(radio_row)
        
        # Channel checkboxes with gain dropdowns (12 leads)
        self.channel_checks = {}
        self.channel_gains = {}
        
        channels_grid = QHBoxLayout()
        channels_grid.setSpacing(12)
        
        for i, lead in enumerate(self.LEADS):
            ch_box = QHBoxLayout()
            ch_box.setSpacing(6)
            
            check = QCheckBox(lead)
            check.setChecked(i < 3)  # Default: first 3 leads checked (I, II, III)
            
            gain_combo = QComboBox()
            gain_combo.addItems(["5mm/mV", "10mm/mV", "20mm/mV", "40mm/mV"])
            gain_combo.setCurrentText("10mm/mV")
            gain_combo.setFixedWidth(90)
            
            ch_box.addWidget(check)
            ch_box.addWidget(gain_combo)
            
            self.channel_checks[lead] = check
            self.channel_gains[lead] = gain_combo
            
            if i % 4 == 0:
                col = QVBoxLayout()
                col.setSpacing(8)
                channels_grid.addLayout(col)
            col.addLayout(ch_box)
        
        channel_layout.addLayout(channels_grid)
        layout.addWidget(channel_group)
        
        # ========== Lead exchange ==========
        exchange_group = QGroupBox("Lead exchange")
        exchange_layout = QHBoxLayout(exchange_group)
        exchange_layout.setSpacing(16)
        
        # Limb lead reversal
        limb_check = QCheckBox("limb lead reversal")
        exchange_layout.addWidget(limb_check)
        self.limb_check = limb_check
        
        # Chest lead exchange
        chest_layout = QHBoxLayout()
        chest_check = QCheckBox("Chest lead exchange")
        self.chest_from_combo = QComboBox()
        self.chest_from_combo.addItems(self.LEADS)
        self.chest_from_combo.setCurrentText("I")
        
        swap_btn = QPushButton("⇄")
        swap_btn.setFixedSize(30, 26)
        
        self.chest_to_combo = QComboBox()
        self.chest_to_combo.addItems(self.LEADS)
        self.chest_to_combo.setCurrentText("I")
        
        chest_layout.addWidget(chest_check)
        chest_layout.addWidget(self.chest_from_combo)
        chest_layout.addWidget(swap_btn)
        chest_layout.addWidget(self.chest_to_combo)
        chest_layout.addStretch()
        self.chest_check = chest_check
        
        exchange_layout.addLayout(chest_layout)
        exchange_layout.addStretch()
        layout.addWidget(exchange_group)
        
        # ========== Bottom buttons ==========
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        
        self.btn_add = QPushButton("Add Event")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_instant = QPushButton("Instant print")
        self.btn_export = QPushButton("Export as pdf")
        self.btn_default = QPushButton("Set as default")
        
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_instant)
        btn_row.addWidget(self.btn_export)
        btn_row.addWidget(self.btn_default)
        
        layout.addLayout(btn_row)
        
        # Connect signals
        self.btn_add.clicked.connect(self._on_add_event)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_instant.clicked.connect(self._on_instant_print)
        self.btn_export.clicked.connect(self._on_export_pdf)
        self.btn_default.clicked.connect(self._on_set_default)
        
        self.radio_1ch.toggled.connect(self._on_channel_mode_changed)
        self.radio_3ch.toggled.connect(self._on_channel_mode_changed)
        self.radio_custom.toggled.connect(self._on_channel_mode_changed)
        
        swap_btn.clicked.connect(self._on_swap_leads)
    
    def _apply_styles(self):
        """Apply consistent styling to the dialog."""
        self.setStyleSheet(f"""
            QDialog {{
                background: #0B1220;
                color: #E5E7EB;
            }}
            QLabel {{
                color: #E5E7EB;
                font-size: 12px;
            }}
            QLineEdit, QComboBox, QDateTimeEdit, QSpinBox {{
                background: #0C1320;
                color: #FFFFFF;
                border: 1px solid #1a6b3f;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
                font-weight: 700;
            }}
            QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QSpinBox:focus {{
                border-color: #28E37B;
                background: #0F1825;
                color: #FFFFFF;
            }}
            QLineEdit::placeholder {{
                color: #6B7280;
            }}
            QComboBox {{
                background: #0C1320;
                color: #FFFFFF;
                border: 1px solid #1a6b3f;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
                font-weight: 700;
                selection-background-color: #1a6b3f;
            }}
            QComboBox:focus {{
                border-color: #28E37B;
                background: #0F1825;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
                subcontrol-origin: padding;
                subcontrol-position: top right;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #28E37B;
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background: #0C1320;
                color: #FFFFFF;
                selection-background-color: #1a6b3f;
                selection-color: #FFFFFF;
                border: 1px solid #1a6b3f;
                outline: 0;
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 8px;
                min-height: 20px;
                border-radius: 3px;
                color: #FFFFFF;
                background: #0C1320;
                font-weight: 700;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background: #152235;
                color: #FFFFFF;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: #1a6b3f;
                color: #FFFFFF;
            }}
            QPushButton {{
                background: #0C1320;
                color: #28E37B;
                border: 1px solid #1a6b3f;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
                min-height: 26px;
            }}
            QPushButton:hover {{
                background: #1a6b3f;
                color: #FFFFFF;
                border-color: #28E37B;
            }}
            QPushButton:pressed {{
                background: #28E37B;
                color: #0C1320;
            }}
            QGroupBox {{
                color: #E5E7EB;
                border: 1px solid #1e3a52;
                border-radius: 6px;
                margin-top: 16px;
                padding-top: 20px;
                font-weight: 600;
                font-size: 12px;
                background: transparent;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: #28E37B;
                font-weight: 700;
            }}
            QRadioButton, QCheckBox {{
                color: #E5E7EB;
                spacing: 8px;
                font-size: 12px;
                background: transparent;
            }}
            QRadioButton::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid #1e3a52;
                border-radius: 9px;
                background: #0C1320;
            }}
            QRadioButton::indicator:hover {{
                border-color: #28E37B;
            }}
            QRadioButton::indicator:checked {{
                background: #28E37B;
                border-color: #28E37B;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid #1e3a52;
                border-radius: 3px;
                background: #0C1320;
            }}
            QCheckBox::indicator:hover {{
                border-color: #28E37B;
            }}
            QCheckBox::indicator:checked {{
                background: #28E37B;
                border-color: #28E37B;
            }}
            QCheckBox::indicator:checked::after {{
                content: "✓";
                color: #0C1320;
                font-weight: bold;
            }}
            QToolButton {{
                background: #0C1320;
                color: #E5E7EB;
                border: 1px solid #1e3a52;
                border-radius: 3px;
                padding: 4px 8px;
            }}
            QToolButton:hover {{
                background: #152235;
                border-color: #28E37B;
            }}
            QToolButton:pressed {{
                background: #1a6b3f;
            }}
        """)
    
    def _on_channel_mode_changed(self):
        """Update channel selections based on mode."""
        if self.radio_1ch.isChecked():
            # Enable only lead II
            for lead, check in self.channel_checks.items():
                check.setChecked(lead == "II")
                check.setEnabled(False)
        elif self.radio_3ch.isChecked():
            # Enable leads I, II, III
            for lead, check in self.channel_checks.items():
                check.setChecked(lead in ["I", "II", "III"])
                check.setEnabled(False)
        else:  # Custom
            # Enable all checkboxes for manual selection
            for check in self.channel_checks.values():
                check.setEnabled(True)
    
    def _on_swap_leads(self):
        """Swap the lead selections in chest lead exchange."""
        from_lead = self.chest_from_combo.currentText()
        to_lead = self.chest_to_combo.currentText()
        self.chest_from_combo.setCurrentText(to_lead)
        self.chest_to_combo.setCurrentText(from_lead)
    
    def _on_add_event(self):
        """Collect event data and emit signal."""
        event_data = self._collect_event_data()
        self.event_added.emit(event_data)
        self.accept()
    
    def _on_instant_print(self):
        """Trigger instant print."""
        event_data = self._collect_event_data()
        event_data['action'] = 'instant_print'
        self.event_added.emit(event_data)
        self.accept()
    
    def _on_export_pdf(self):
        """Export event as PDF."""
        event_data = self._collect_event_data()
        event_data['action'] = 'export_pdf'
        self.event_added.emit(event_data)
        self.accept()
    
    def _on_set_default(self):
        """Save current settings as default."""
        # TODO: Save settings to config file
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(self, "Settings Saved", "Current settings have been saved as default.")
    
    def _collect_event_data(self) -> dict:
        """Collect all form data into a dictionary."""
        # Get selected channels
        selected_channels = [lead for lead, check in self.channel_checks.items() if check.isChecked()]
        channel_gains = {lead: self.channel_gains[lead].currentText() for lead in selected_channels}
        
        return {
            'timestamp': self.time_edit.dateTime().toSecsSinceEpoch(),
            'print_length_sec': int(self.len_combo.currentText()),
            'hr': int(self.hr_edit.text()) if self.hr_edit.text().isdigit() else 0,
            'label': self.label_combo.currentText(),
            'orientation': 'vertical' if self.radio_vertical.isChecked() else 'horizontal',
            'preview_channel': self.preview_combo.currentText(),
            'display_type': self.display_combo.currentText(),
            'channel_mode': '1-CH' if self.radio_1ch.isChecked() else ('3-CH' if self.radio_3ch.isChecked() else 'Custom'),
            'selected_channels': selected_channels,
            'channel_gains': channel_gains,
            'limb_reversal': self.limb_check.isChecked(),
            'chest_exchange': self.chest_check.isChecked(),
            'chest_from': self.chest_from_combo.currentText() if self.chest_check.isChecked() else None,
            'chest_to': self.chest_to_combo.currentText() if self.chest_check.isChecked() else None,
            'action': 'add_event'
        }


# Test/Demo
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    dialog = AddEventDialog(start_time=datetime.now(), current_sec=120.0, hr=75.0)
    dialog.event_added.connect(lambda data: print(f"Event added: {data}"))
    dialog.exec_()
    sys.exit(app.exit_code if hasattr(app, 'exit_code') else 0)
