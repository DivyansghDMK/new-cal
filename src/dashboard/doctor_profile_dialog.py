from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from utils.app_paths import data_file


def _load_users_db() -> Dict[str, Dict[str, Any]]:
    users_path = str(data_file("users.json"))
    if not os.path.exists(users_path):
        return {}
    try:
        with open(users_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}

    # Legacy format: {username: "password"}
    if isinstance(raw, dict):
        sample_values = list(raw.values())
        if sample_values and isinstance(sample_values[0], str):
            return {str(u): {"password": p} for u, p in raw.items()}
        return {str(u): v for u, v in raw.items() if isinstance(v, dict)}
    return {}


def _save_users_db(users: Dict[str, Dict[str, Any]]) -> None:
    users_path = str(data_file("users.json"))
    with open(users_path, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def _find_user_key_and_record(
    users: Dict[str, Dict[str, Any]],
    username_or_phone: str,
) -> Tuple[Optional[str], Dict[str, Any]]:
    ident = str(username_or_phone or "").strip()
    if not ident:
        return None, {}

    if ident in users and isinstance(users.get(ident), dict):
        return ident, dict(users[ident])

    ident_lower = ident.lower()
    for uname, rec in users.items():
        if not isinstance(rec, dict):
            continue
        phone = str(rec.get("phone", "")).strip()
        full_name = str(rec.get("full_name", "")).strip()
        if ident == phone or ident == full_name:
            return uname, dict(rec)
        if ident_lower and (ident_lower == phone.lower() or ident_lower == full_name.lower()):
            return uname, dict(rec)
    return None, {}


@dataclass
class DoctorProfileUpdate:
    full_name: str
    doctor_name: str
    org_name: str
    org_address: str
    current_password: str
    new_password: str
    confirm_password: str


class DoctorProfileDialog(QDialog):
    """
    Per-doctor profile settings dialog.

    Persists to users.json (same store used for login + report org/doctor fallback).
    """

    def __init__(self, username: str, user_details: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Profile Management")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(520)

        self._identifier = str(username or "").strip()
        self._user_details = dict(user_details or {}) if isinstance(user_details, dict) else {}

        self._users = _load_users_db()
        self._user_key, self._record = _find_user_key_and_record(self._users, self._identifier)
        if self._record:
            # Merge missing fields from in-memory details
            for k, v in self._user_details.items():
                if k not in self._record or not str(self._record.get(k, "")).strip():
                    self._record[k] = v

        self._build_ui()
        self._prefill()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #f4f7f6; }
            QLabel { color: #101828; font-family: 'Segoe UI', Arial; }
            QLineEdit, QTextEdit {
                font: 11pt 'Segoe UI', Arial; color: #101828; background: #fcfcfd; padding: 8px 12px;
                border: 1px solid #d0d5dd; border-radius: 8px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 2px solid #ff6600; background: #ffffff;
            }
            QPushButton {
                font: bold 11pt 'Segoe UI', Arial;
                padding: 10px 24px;
                border-radius: 10px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Main Header
        title = QLabel("Profile Management")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font: 900 18pt 'Segoe UI', Arial; color: white; "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff6600, stop:1 #ff8c33); "
            "padding: 14px; border-radius: 12px;"
        )
        layout.addWidget(title)

        label_style = (
            "QLabel { font: bold 11pt 'Segoe UI', Arial; color: #344054; background: transparent; "
            "padding: 8px; border: none; min-width: 160px; }"
        )

        # ---------------- Profile card ----------------
        profile_card = QFrame()
        profile_card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e0e5eb; border-radius: 16px; }"
        )
        profile_layout = QVBoxLayout(profile_card)
        profile_layout.setContentsMargins(24, 24, 24, 24)
        profile_layout.setSpacing(16)

        section_title = QLabel("Personal Information")
        section_title.setStyleSheet("font: 900 12pt 'Segoe UI', Arial; color: #ff6600; border: none; background: transparent;")
        profile_layout.addWidget(section_title)

        form = QVBoxLayout()
        form.setSpacing(12)

        def add_form_row(label_text, widget):
            row = QHBoxLayout()
            row.setSpacing(16)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(label_style)
            row.addWidget(lbl)
            row.addWidget(widget)
            form.addLayout(row)

        self.full_name_edit = QLineEdit()
        self.full_name_edit.setPlaceholderText("Enter your full name")
        add_form_row("Full Name", self.full_name_edit)

        self.doctor_name_edit = QLineEdit()
        self.doctor_name_edit.setPlaceholderText("Enter your Doctor name")
        add_form_row("Doctor Name", self.doctor_name_edit)

        self.org_name_edit = QLineEdit()
        self.org_name_edit.setPlaceholderText("Clinic or Hospital name")
        add_form_row("Clinic / Hospital Name", self.org_name_edit)

        self.org_address_edit = QTextEdit()
        self.org_address_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.org_address_edit.setPlaceholderText("Full clinic address")
        self.org_address_edit.setFixedHeight(100)
        add_form_row("Clinic Address", self.org_address_edit)

        profile_layout.addLayout(form)
        layout.addWidget(profile_card)

        # ---------------- Security card ----------------
        security_card = QFrame()
        security_card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e0e5eb; border-radius: 16px; }"
        )
        security_layout = QVBoxLayout(security_card)
        security_layout.setContentsMargins(24, 24, 24, 24)
        security_layout.setSpacing(16)

        sec_title = QLabel("Security & Password")
        sec_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        sec_title.setStyleSheet("color: #ff6600; border: none; background: transparent;")
        security_layout.addWidget(sec_title)

        sec_form = QVBoxLayout()
        sec_form.setSpacing(12)

        def add_password_row(label_text, widget, eye_btn):
            row = QHBoxLayout()
            row.setSpacing(15)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(label_style)
            
            field_row = QHBoxLayout()
            field_row.setSpacing(8)
            field_row.addWidget(widget)
            field_row.addWidget(eye_btn)
            
            row.addWidget(lbl)
            row.addLayout(field_row)
            sec_form.addLayout(row)

        self.current_password_edit = QLineEdit()
        self.current_password_edit.setEchoMode(QLineEdit.Password)
        self.cur_eye_btn = self._create_eye_btn(self.current_password_edit)
        add_password_row("Current Password", self.current_password_edit, self.cur_eye_btn)

        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.Password)
        self.new_eye_btn = self._create_eye_btn(self.new_password_edit)
        add_password_row("New Password", self.new_password_edit, self.new_eye_btn)

        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.Password)
        self.confirm_password_edit.returnPressed.connect(self._on_save)
        self.conf_eye_btn = self._create_eye_btn(self.confirm_password_edit)
        add_password_row("Confirm Password", self.confirm_password_edit, self.conf_eye_btn)

        security_layout.addLayout(sec_form)
        layout.addWidget(security_card)

        # ---------------- Buttons ----------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet(
            "QPushButton { background: #ffffff; color: #344054; border-radius: 10px; padding: 10px 24px;"
            " font: bold 11pt 'Segoe UI', Arial; border: 1px solid #d0d5dd; min-width: 120px; }"
            "QPushButton:hover { background: #f9fafb; }"
            "QPushButton:pressed { background: #e9edf3; }"
        )
        btn_row.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(
            "QPushButton { background: #ff6600; color: white; border-radius: 10px; padding: 10px 24px;"
            " font: bold 11pt 'Segoe UI', Arial; border: none; min-width: 140px; }"
            "QPushButton:hover { background: #e65c00; }"
            "QPushButton:pressed { background: #cc5200; }"
        )
        btn_row.addWidget(self.save_btn)

        layout.addLayout(btn_row)

        try:
            from PyQt5.QtWidgets import QGraphicsDropShadowEffect
            from PyQt5.QtGui import QColor
            shadow1 = QGraphicsDropShadowEffect(self)
            shadow1.setBlurRadius(20)
            shadow1.setOffset(0, 4)
            shadow1.setColor(QColor(16, 24, 40, 30))
            profile_card.setGraphicsEffect(shadow1)

            shadow2 = QGraphicsDropShadowEffect(self)
            shadow2.setBlurRadius(20)
            shadow2.setOffset(0, 4)
            shadow2.setColor(QColor(16, 24, 40, 30))
            security_card.setGraphicsEffect(shadow2)
        except Exception:
            pass

    def _create_eye_btn(self, target_edit: QLineEdit) -> QPushButton:
        btn = QPushButton("👁")
        btn.setFixedSize(36, 36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: #ff6600; color: white; border-radius: 8px; font-size: 14px; padding: 0px; border: none; }"
            "QPushButton:hover { background: #ff7a26; }"
        )
        btn.clicked.connect(lambda: self._toggle_visibility(target_edit, btn))
        return btn

    def _toggle_visibility(self, target_edit: QLineEdit, btn: QPushButton) -> None:
        if target_edit.echoMode() == QLineEdit.Password:
            target_edit.setEchoMode(QLineEdit.Normal)
            btn.setText("🔒")
        else:
            target_edit.setEchoMode(QLineEdit.Password)
            btn.setText("👁")

    def _prefill(self) -> None:
        rec = self._record or self._user_details or {}

        self.full_name_edit.setText(str(rec.get("full_name", "") or "").strip())
        self.doctor_name_edit.setText(str(rec.get("doctor", rec.get("doctor_name", "")) or "").strip())
        self.org_name_edit.setText(str(rec.get("org_name", "") or rec.get("Org. Name", "") or "").strip())
        self.org_address_edit.setPlainText(str(rec.get("org_address", "") or rec.get("Org. Address", "") or "").strip())

    def get_updated_user_details(self) -> Dict[str, Any]:
        return dict(self._record or {})

    def _collect(self) -> DoctorProfileUpdate:
        return DoctorProfileUpdate(
            full_name=self.full_name_edit.text().strip(),
            doctor_name=self.doctor_name_edit.text().strip(),
            org_name=self.org_name_edit.text().strip(),
            org_address=self.org_address_edit.toPlainText().strip(),
            current_password=self.current_password_edit.text(),
            new_password=self.new_password_edit.text(),
            confirm_password=self.confirm_password_edit.text(),
        )

    def _validate(self, upd: DoctorProfileUpdate) -> Optional[str]:
        if not upd.full_name:
            return "Full name is required."
        if not upd.doctor_name:
            return "Doctor name is required."
        if not upd.org_name:
            return "Organisation name is required."
        if not upd.org_address:
            return "Organisation address is required."

        wants_password_change = bool(upd.new_password or upd.confirm_password or upd.current_password)
        if wants_password_change:
            if not (upd.current_password and upd.new_password and upd.confirm_password):
                return "To change password, fill Current password, New password, and Confirm password."
            if upd.new_password != upd.confirm_password:
                return "New password and Confirm password do not match."
            if len(upd.new_password) < 4:
                return "New password must be at least 4 characters."
        return None

    def _on_save(self) -> None:
        upd = self._collect()
        msg = self._validate(upd)
        if msg:
            QMessageBox.warning(self, "Validation", msg)
            return

        if not self._user_key:
            QMessageBox.warning(
                self,
                "Profile not found",
                "Could not find the logged-in user in users.json. Please sign out and sign in again.",
            )
            return

        # Password validation/update (if requested)
        wants_password_change = bool(upd.new_password or upd.confirm_password or upd.current_password)
        if wants_password_change:
            try:
                from auth.sign_in import SignIn

                auth = SignIn()
                found = auth._find_user_record(self._user_key)  # returns (username, record)
                if not found:
                    QMessageBox.warning(self, "Password", "User record not found for password change.")
                    return
                found_username, found_record = found
                stored = str(found_record.get("password", ""))
                if not auth._verify_password(upd.current_password, stored):
                    QMessageBox.warning(self, "Password", "Current password is incorrect.")
                    return
                # Hash + persist
                found_record["password"] = auth._hash_password(upd.new_password)
                auth.users[found_username] = found_record
                auth.save_users()
                # Keep our in-memory snapshot consistent so the profile save below doesn't overwrite it.
                try:
                    self._record = dict(self._record or {})
                    self._record["password"] = found_record.get("password", "")
                    if self._user_key and isinstance(self._users.get(self._user_key), dict):
                        self._users[self._user_key]["password"] = found_record.get("password", "")
                except Exception:
                    pass
            except Exception as e:
                QMessageBox.warning(self, "Password", f"Failed to change password: {e}")
                return

        # Update profile fields
        self._record = dict(self._record or {})
        self._record["full_name"] = upd.full_name
        self._record["doctor"] = upd.doctor_name
        self._record["doctor_name"] = upd.doctor_name
        self._record["org_name"] = upd.org_name
        self._record["org_address"] = upd.org_address
        # Keep legacy keys used by some PDF headers
        self._record["Org. Name"] = upd.org_name
        self._record["Org. Address"] = upd.org_address
        self._record["Org."] = upd.org_name

        # Persist to users.json
        self._users[self._user_key] = dict(self._users.get(self._user_key, {}), **self._record)
        try:
            _save_users_db(self._users)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", f"Could not save profile: {e}")
            return

        # Show success message and close automatically
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Profile Updated")
        msg_box.setText("Your profile has been updated successfully!")
        msg_box.setStandardButtons(QMessageBox.NoButton)
        msg_box.setStyleSheet("QLabel { color: #1f2d3d; font-weight: bold; }")
        
        from PyQt5.QtCore import QTimer
        
        def close_all():
            msg_box.accept()
            self.accept()
            
        QTimer.singleShot(1500, close_all)
        msg_box.show()
