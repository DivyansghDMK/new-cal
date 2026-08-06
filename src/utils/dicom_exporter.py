"""
dicom_exporter.py
~~~~~~~~~~~~~~~~~
Convert a CardioX history entry to a DICOM file.

Supports:
  1. DICOM Encapsulated PDF Storage (1.2.840.10008.5.1.4.1.1.104.1)
     When a PDF report exists, embeds the entire visual PDF report inside the DICOM
     file along with full patient demographics so PACS & DICOM viewers open the PDF directly!

  2. Basic Text SR DICOM (1.2.840.10008.5.1.4.1.1.88.11)
     Fallback structured report when raw PDF file is not available.

Usage:
    from utils.dicom_exporter import entry_to_dicom, is_available
    if is_available():
        path = entry_to_dicom(history_entry)
"""

from __future__ import annotations

import datetime
import os
import re
import struct
from typing import Optional

# ── optional import — graceful if pydicom not present ────────────────────────
try:
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.sequence import Sequence
    from pydicom.uid import generate_uid, ExplicitVRLittleEndian
    _PYDICOM_OK = True
except ImportError:
    _PYDICOM_OK = False

# ── DICOM SOP Class UIDs ──────────────────────────────────────────────────────
ENCAPSULATED_PDF_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.104.1"  # DICOM Encapsulated PDF
ECG_SOP_CLASS_UID              = "1.2.840.10008.5.1.4.1.1.9.1.1"   # 12-lead ECG Waveform
SR_SOP_CLASS_UID               = "1.2.840.10008.5.1.4.1.1.88.11"   # Basic Text SR
IMPL_CLASS_UID                 = "1.2.826.0.1.3680043.9.7156.1"
IMPL_VER_NAME                  = "CARDIOX_1_0"


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe(value, default: str = "") -> str:
    """Return a printable ASCII string truncated to 64 chars."""
    text = str(value or default).strip()
    return re.sub(r"[^\x20-\x7E]", " ", text)[:64]


def _dicom_date(value=None) -> str:
    """Return YYYYMMDD from various input formats."""
    if isinstance(value, datetime.date):
        return value.strftime("%Y%m%d")
    if isinstance(value, str) and value.strip():
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d", "%Y/%m/%d"):
            try:
                return datetime.datetime.strptime(text, fmt).strftime("%Y%m%d")
            except ValueError:
                pass
    return datetime.datetime.now().strftime("%Y%m%d")


def _dicom_time(value=None) -> str:
    """Return HHMMSS from various input formats."""
    if isinstance(value, str) and value.strip():
        text = value.strip()
        for fmt in ("%H:%M:%S", "%H%M%S", "%H:%M"):
            try:
                return datetime.datetime.strptime(text, fmt).strftime("%H%M%S")
            except ValueError:
                pass
    return datetime.datetime.now().strftime("%H%M%S")


def _patient_name(entry: dict) -> str:
    """Return DICOM PN format: Last^First."""
    full  = _safe(entry.get("patient_name", ""))
    first = _safe(entry.get("first_name", ""))
    last  = _safe(entry.get("last_name", ""))
    if last and first:
        return f"{last}^{first}"
    if full:
        parts = full.split(" ", 1)
        return (f"{parts[1]}^{parts[0]}" if len(parts) == 2 else full)
    return "Unknown^Patient"


def _dicom_sex(value) -> str:
    """Return DICOM CS PatientSex: M, F, O, or U."""
    val = str(value or "").strip().upper()
    if val in ("M", "MALE"):
        return "M"
    if val in ("F", "FEMALE"):
        return "F"
    if val in ("O", "OTHER"):
        return "O"
    return "U"


def _dicom_age(value) -> str:
    """Return DICOM AS PatientAge: format nnnY / nnnM / nnnD."""
    text = str(value or "").strip()
    if not text:
        return ""
    nums = re.findall(r"\d+", text)
    if nums:
        age_num = int(nums[0])
        if "m" in text.lower() and "y" not in text.lower():
            return f"{age_num:03d}M"
        if "d" in text.lower():
            return f"{age_num:03d}D"
        return f"{age_num:03d}Y"
    return ""


def _findings_text(entry: dict) -> str:
    """Extract a plain-text findings string from the entry."""
    raw = (entry.get("findings")
           or entry.get("interpretation")
           or entry.get("conclusion")
           or "")
    if isinstance(raw, list):
        return "\n".join(f"- {f}" for f in raw if f)
    return str(raw)


# ── dataset builders ──────────────────────────────────────────────────────────

def _build_encapsulated_pdf_dataset(entry: dict, sop_uid: str, pdf_bytes: bytes) -> "Dataset":
    """Create a DICOM Encapsulated PDF dataset embedding the visual PDF report."""
    ds = Dataset()
    ds.SpecificCharacterSet   = "ISO_IR 192"  # UTF-8 encoding

    study_date = entry.get("date", "")
    study_time = entry.get("time", "")

    # Patient Module
    ds.PatientName            = _patient_name(entry)
    ds.PatientID              = _safe(
        entry.get("patient_id") or entry.get("mrn") or entry.get("id"), "UNKNOWN"
    )
    ds.PatientBirthDate       = _dicom_date(
        entry.get("dob") or entry.get("date_of_birth")
    )
    ds.PatientSex             = _dicom_sex(entry.get("gender", ""))
    age_str                   = _dicom_age(entry.get("age", ""))
    if age_str:
        ds.PatientAge         = age_str
    weight_str                = _safe(entry.get("weight", ""))
    if weight_str:
        try:
            ds.PatientWeight  = str(float(re.sub(r"[^\d.]", "", weight_str)))
        except Exception:
            pass
    height_str                = _safe(entry.get("height", ""))
    if height_str:
        try:
            ds.PatientSize    = str(float(re.sub(r"[^\d.]", "", height_str)) / 100.0)  # cm to meters
        except Exception:
            pass

    # General Study Module
    ds.StudyInstanceUID       = generate_uid()
    ds.StudyDate              = _dicom_date(study_date)
    ds.StudyTime              = _dicom_time(study_time)
    ds.StudyID                = re.sub(r"\W", "", f"{study_date}{study_time}")[:16] or "ECG001"
    ds.StudyDescription       = _safe(entry.get("report_type", "ECG Report"))
    ds.ReferringPhysicianName = _safe(entry.get("doctor", ""))
    ds.AccessionNumber        = ""

    # General Series Module
    ds.SeriesInstanceUID      = generate_uid()
    ds.SeriesNumber           = 1
    ds.SeriesDate             = _dicom_date(study_date)
    ds.SeriesTime             = _dicom_time(study_time)
    ds.SeriesDescription      = "ECG 12-Lead Report PDF"
    ds.Modality               = "ECG"  # Medical standard for PACS Cardiology filters

    # General Equipment Module
    ds.Manufacturer           = "CardioX"
    ds.ManufacturerModelName  = "RhythmUltra 12-Lead System"
    ds.InstitutionName        = _safe(entry.get("org_name") or entry.get("Org.", "CardioX Medical"))
    ds.InstitutionAddress     = _safe(entry.get("org_address", ""))
    ds.SoftwareVersions       = "1.0"

    # Encapsulated Document Module (DICOM PS3.3 C.24.2 Requirements)
    ds.InstanceNumber                 = 1
    ds.ContentDate                    = _dicom_date(study_date)
    ds.ContentTime                    = _dicom_time(study_time)
    ds.AcquisitionDateTime            = f"{_dicom_date(study_date)}{_dicom_time(study_time)}"
    ds.DocumentTitle                  = _safe(entry.get("report_type", "ECG Report"))
    ds.VerificationFlag               = "UNVERIFIED"
    ds.ConversionType                 = "WSD"  # Workstation Software Document
    ds.BurnedInAnnotation             = "YES"  # Embedded visual document
    ds.MIMETypeOfEncapsulatedDocument = "application/pdf"
    ds.EncapsulatedDocument           = pdf_bytes

    # SOP Common Module
    ds.SOPClassUID            = ENCAPSULATED_PDF_SOP_CLASS_UID
    ds.SOPInstanceUID         = sop_uid

    return ds


def _build_sr_dataset(entry: dict, sop_uid: str) -> "Dataset":
    """Create a Basic Text SR DICOM dataset (fallback when no PDF file is available)."""
    ds = Dataset()
    ds.SpecificCharacterSet   = "ISO_IR 192"  # UTF-8 encoding

    study_date = entry.get("date", "")
    study_time = entry.get("time", "")

    # Patient Module
    ds.PatientName            = _patient_name(entry)
    ds.PatientID              = _safe(
        entry.get("patient_id") or entry.get("mrn") or entry.get("id"), "UNKNOWN"
    )
    ds.PatientBirthDate       = _dicom_date(
        entry.get("dob") or entry.get("date_of_birth")
    )
    ds.PatientSex             = _dicom_sex(entry.get("gender", ""))
    age_str                   = _dicom_age(entry.get("age", ""))
    if age_str:
        ds.PatientAge         = age_str

    # General Study Module
    ds.StudyInstanceUID       = generate_uid()
    ds.StudyDate              = _dicom_date(study_date)
    ds.StudyTime              = _dicom_time(study_time)
    ds.StudyID                = re.sub(r"\W", "", f"{study_date}{study_time}")[:16] or "ECG001"
    ds.StudyDescription       = _safe(entry.get("report_type", "ECG"))
    ds.ReferringPhysicianName = _safe(entry.get("doctor", ""))
    ds.AccessionNumber        = ""

    # General Series Module
    ds.SeriesInstanceUID      = generate_uid()
    ds.SeriesNumber           = 1
    ds.SeriesDate             = _dicom_date(study_date)
    ds.SeriesTime             = _dicom_time(study_time)
    ds.SeriesDescription      = "ECG Report Summary"
    ds.Modality               = "ECG"


    # General Equipment Module
    ds.Manufacturer           = "CardioX"
    ds.InstitutionName        = _safe(entry.get("org_name") or entry.get("Org.", ""))
    ds.InstitutionAddress     = _safe(entry.get("org_address", ""))
    ds.SoftwareVersions       = "1.0"

    # SOP Common Module
    ds.SOPClassUID            = SR_SOP_CLASS_UID
    ds.SOPInstanceUID         = sop_uid
    ds.InstanceNumber         = "1"
    ds.ContentDate            = _dicom_date(study_date)
    ds.ContentTime            = _dicom_time(study_time)

    # Structured Report Content — free-text summary
    findings = _findings_text(entry)
    text_content = (
        "CardioX ECG Report Summary\n"
        "==========================\n"
        f"Patient : {_patient_name(entry)}\n"
        f"Date    : {study_date}  Time: {study_time}\n"
        f"Doctor  : {_safe(entry.get('doctor', ''))}\n"
        f"Org     : {_safe(entry.get('org_name', ''))}\n"
        f"Type    : {_safe(entry.get('report_type', 'ECG'))}\n"
        f"Status  : {_safe(entry.get('review_status', 'Pending'))}\n"
        f"Height  : {_safe(entry.get('height', ''))}\n"
        f"Weight  : {_safe(entry.get('weight', ''))}\n"
        "\nFindings:\n"
        + (findings or "No structured findings available.")
        + "\n"
    )

    content_item = Dataset()
    content_item.RelationshipType = "CONTAINS"
    content_item.ValueType        = "TEXT"
    content_item.TextValue        = text_content[:10240]

    ds.ContentSequence = Sequence([content_item])
    return ds


# ── public API ────────────────────────────────────────────────────────────────

def entry_to_dicom(entry: dict, output_path: str = "") -> str:
    """
    Convert a history entry dict to a DICOM file.
    If a valid PDF file exists for the report, encapsulates the PDF inside DICOM.

    Parameters
    ----------
    entry       : dict  — CardioX history entry from ecg_history.json
    output_path : str   — full path for output .dcm; auto-generated if empty

    Returns
    -------
    str — absolute path to saved DICOM file
    """
    if not _PYDICOM_OK:
        raise ImportError(
            "pydicom is not installed. "
            "Run:  pip install pydicom"
        )

    # Auto-generate output path under reports/dicom/
    if not output_path:
        try:
            from utils.app_paths import data_file
            dicom_dir = str(data_file(os.path.join("reports", "dicom")))
        except Exception:
            dicom_dir = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "..", "reports", "dicom")
            )
        os.makedirs(dicom_dir, exist_ok=True)
        patient = re.sub(r"\W+", "_", str(entry.get("patient_name") or "patient")).strip("_")
        date    = re.sub(r"\W+", "", str(entry.get("date", ""))).strip() or "nodate"
        base    = f"ECG_{patient}_{date}"[:60]
        output_path = os.path.join(dicom_dir, f"{base}.dcm")

    output_path = os.path.normpath(output_path)
    parent_dir  = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # Check if a valid PDF report file exists
    report_file = str(entry.get("report_file") or "").strip()
    pdf_bytes = None
    if report_file and os.path.isfile(report_file) and report_file.lower().endswith(".pdf"):
        try:
            with open(report_file, "rb") as f:
                pdf_bytes = f.read()
        except Exception:
            pdf_bytes = None

    sop_uid = generate_uid()
    if pdf_bytes:
        ds = _build_encapsulated_pdf_dataset(entry, sop_uid, pdf_bytes)
        sop_class = ENCAPSULATED_PDF_SOP_CLASS_UID
    else:
        ds = _build_sr_dataset(entry, sop_uid)
        sop_class = SR_SOP_CLASS_UID

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID    = sop_class
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID          = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID     = IMPL_CLASS_UID
    file_meta.ImplementationVersionName  = IMPL_VER_NAME

    ds.file_meta        = file_meta
    ds.is_implicit_VR   = False
    ds.is_little_endian = True

    pydicom.dcmwrite(output_path, ds, write_like_original=False)
    return os.path.abspath(output_path)


def is_available() -> bool:
    """Return True if pydicom is installed and DICOM export is enabled."""
    return _PYDICOM_OK
