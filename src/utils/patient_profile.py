import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.app_paths import data_file

SRC_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SRC_ROOT.parent
USERS_FILE = data_file("users.json")
ALL_PATIENTS_FILE = data_file("all_patients.json")
FALLBACK_USERS_FILE = SRC_ROOT / "users.json"


def _safe_read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _load_users_db() -> Dict[str, Any]:
    """Load users from the runtime users.json and (optionally) src/users.json.

    Some entrypoints run with different CWDs, so `data_file("users.json")` may
    point to different locations. For reporting, merge both sources so doctor/org
    details saved during sign up are always discoverable.
    """
    merged: Dict[str, Any] = {}

    fallback = _safe_read_json(FALLBACK_USERS_FILE)
    if isinstance(fallback, dict):
        merged.update(fallback)

    primary = _safe_read_json(USERS_FILE)
    if isinstance(primary, dict):
        merged.update(primary)

    return merged


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _split_name(full_name: str) -> Dict[str, str]:
    parts = [part for part in str(full_name or "").strip().split() if part]
    if not parts:
        return {"first_name": "", "last_name": "", "patient_name": ""}
    return {
        "first_name": parts[0],
        "last_name": " ".join(parts[1:]),
        "patient_name": " ".join(parts),
    }


def _find_user_record(username: str = "", user_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    provided = dict(user_details) if isinstance(user_details, dict) and user_details else {}
    users = _load_users_db()
    if not isinstance(users, dict) or not users:
        return provided

    key = str(username or "").strip()
    if key and isinstance(users.get(key), dict):
        record = dict(users[key])
        for k, v in provided.items():
            if k not in record or not _is_present(record.get(k)):
                record[k] = v
        return record

    key_lower = key.lower()
    for uname, record in users.items():
        if not isinstance(record, dict):
            continue
        if key and uname == key:
            merged = dict(record)
            for k, v in provided.items():
                if k not in merged or not _is_present(merged.get(k)):
                    merged[k] = v
            return merged
        full_name = str(record.get("full_name", "")).strip()
        phone = str(record.get("phone", "")).strip()
        if key and (full_name == key or phone == key):
            merged = dict(record)
            for k, v in provided.items():
                if k not in merged or not _is_present(merged.get(k)):
                    merged[k] = v
            return merged
        if key_lower and (full_name.lower() == key_lower or phone.lower() == key_lower):
            merged = dict(record)
            for k, v in provided.items():
                if k not in merged or not _is_present(merged.get(k)):
                    merged[k] = v
            return merged

    return provided


def _is_valid_name(name: str) -> bool:
    """Return True only if the name contains at least one alphabetic character.
    This prevents raw numeric usernames (e.g. '12', '007') from being
    displayed as patient names in ECG reports."""
    return bool(name) and any(c.isalpha() for c in name)


def _format_indian_phone(phone_value: Any) -> str:
    """Return phone number as +91-XXXXXXXXXX for report display."""
    if phone_value is None:
        return ""

    text = str(phone_value).strip()
    if not text:
        return ""

    digits_only = "".join(ch for ch in text if ch.isdigit())
    if digits_only.startswith("91") and len(digits_only) > 10:
        digits_only = digits_only[2:]
    if len(digits_only) > 10:
        digits_only = digits_only[-10:]
    if not digits_only:
        return text
    return f"+91-{digits_only}"


def org_from_user_profile(username: str = "", user_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return organization/contact fields from the signup user profile.

    This is intentionally limited to org/address/phone metadata so we don't
    couple patient identity (patient_name) to the login user record.
    """
    record = _find_user_record(username=username, user_details=user_details)
    if not record:
        return {}

    org_name = str(record.get("org_name", "") or record.get("Org.", "") or record.get("Org. Name", "") or "").strip()
    org_address = str(record.get("org_address", "") or record.get("Org. Address", "") or "").strip()
    doctor_name = str(record.get("doctor", "") or record.get("doctor_name", "") or "").strip()
    phone = str(record.get("doctor_mobile", "") or record.get("phone", "") or "").strip()
    formatted_phone = _format_indian_phone(phone) if phone else ""

    out: Dict[str, Any] = {"date_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if org_name:
        out["Org."] = org_name
        out["Org. Name"] = org_name
        out["org"] = org_name
        out["org_name"] = org_name
    if org_address:
        out["Org. Address"] = org_address
        out["org_address"] = org_address
    if formatted_phone:
        out["doctor_mobile"] = formatted_phone
    if doctor_name:
        # Canonical key for reports is `doctor_name`.
        # Keep `doctor` populated for backward compatibility with older generators.
        out["doctor_name"] = doctor_name
        out["doctor"] = doctor_name
    return out


def patient_from_user_profile(username: str = "", user_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    record = _find_user_record(username=username, user_details=user_details)
    if not record:
        return {}

    raw_patient_name = str(record.get("patient_name", "")).strip()
    if not _is_valid_name(raw_patient_name):
        return {}

    name_parts = _split_name(raw_patient_name)
    patient = {
        "first_name": name_parts["first_name"],
        "last_name": name_parts["last_name"],
        "patient_name": name_parts["patient_name"],
        "date_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return patient


def get_latest_saved_patient() -> Dict[str, Any]:
    payload = _safe_read_json(ALL_PATIENTS_FILE)
    if isinstance(payload, dict):
        patients = payload.get("patients")
        if isinstance(patients, list) and patients:
            last_patient = patients[-1]
            if isinstance(last_patient, dict):
                return dict(last_patient)
    return {}


def merge_patient_profile(base_patient: Optional[Dict[str, Any]], fallback_patient: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(base_patient or {})
    fallback = dict(fallback_patient or {})

    for key, value in fallback.items():
        if not _is_present(merged.get(key)):
            merged[key] = value

    if not _is_present(merged.get("patient_name")):
        combined_name = " ".join(
            part for part in [str(merged.get("first_name", "")).strip(), str(merged.get("last_name", "")).strip()] if part
        ).strip()
        if combined_name:
            merged["patient_name"] = combined_name

    if not _is_present(merged.get("first_name")) or not _is_present(merged.get("last_name")):
        name_parts = _split_name(str(merged.get("patient_name", "")).strip())
        if not _is_present(merged.get("first_name")):
            merged["first_name"] = name_parts["first_name"]
        if not _is_present(merged.get("last_name")):
            merged["last_name"] = name_parts["last_name"]

    merged["date_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Normalize doctor naming: `doctor_name` is canonical, but some flows still write `doctor`.
    try:
        doc = str(merged.get("doctor", "") or "").strip()
        doc_name = str(merged.get("doctor_name", "") or "").strip()
        if doc and not doc_name:
            merged["doctor_name"] = doc
        elif doc_name and not doc:
            merged["doctor"] = doc_name
    except Exception:
        pass
    return merged


def resolve_patient_profile(
    explicit_patient: Optional[Dict[str, Any]] = None,
    username: str = "",
    user_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_fallback = org_from_user_profile(username=username, user_details=user_details)
    user_doctor = ""
    try:
        user_doctor = str(user_fallback.get("doctor_name", "") or user_fallback.get("doctor", "")).strip()
    except Exception:
        user_doctor = ""
    user_org = ""
    user_addr = ""
    try:
        user_org = str(user_fallback.get("org_name", "") or user_fallback.get("Org.", "") or "").strip()
        user_addr = str(user_fallback.get("org_address", "") or user_fallback.get("Org. Address", "") or "").strip()
    except Exception:
        user_org, user_addr = "", ""

    current = dict(explicit_patient or {})
    if current:
        merged = merge_patient_profile(current, user_fallback)
        if user_doctor:
            merged["doctor_name"] = user_doctor
            merged["doctor"] = user_doctor
        # Always prefer the logged-in doctor's organisation details for report headers.
        if user_org:
            merged["Org."] = user_org
            merged["Org. Name"] = user_org
            merged["org"] = user_org
            merged["org_name"] = user_org
        if user_addr:
            merged["Org. Address"] = user_addr
            merged["org_address"] = user_addr
        return merged

    latest_patient = get_latest_saved_patient()
    if latest_patient:
        merged = merge_patient_profile(latest_patient, user_fallback)
        if user_doctor:
            merged["doctor_name"] = user_doctor
            merged["doctor"] = user_doctor
        if user_org:
            merged["Org."] = user_org
            merged["Org. Name"] = user_org
            merged["org"] = user_org
            merged["org_name"] = user_org
        if user_addr:
            merged["Org. Address"] = user_addr
            merged["org_address"] = user_addr
        return merged

    if user_fallback:
        merged = merge_patient_profile(user_fallback, {})
        if user_doctor:
            merged["doctor_name"] = user_doctor
            merged["doctor"] = user_doctor
        if user_org:
            merged["Org."] = user_org
            merged["Org. Name"] = user_org
            merged["org"] = user_org
            merged["org_name"] = user_org
        if user_addr:
            merged["Org. Address"] = user_addr
            merged["org_address"] = user_addr
        return merged
    return {"date_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
