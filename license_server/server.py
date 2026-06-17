"""
license_server/server.py
========================
CardioX License Validation Server (Flask) — v2.0 Three-Pillar Architecture.

Endpoints
---------
POST /api/v1/register          First-time device registration.  Validates key pool,
                                hardware fingerprint uniqueness, RhythmUltra serial
                                uniqueness → creates seat → returns signed token.
POST /api/v1/heartbeat         7-day check-in.  Verifies license not revoked.
                                Updates last_heartbeat timestamp.
POST /api/v1/activate          [Legacy] First-time activation (old key→fingerprint schema).
POST /api/v1/validate          [Legacy] Validate an already-activated key.
POST /api/v1/deactivate        Release / deactivate a seat.
GET  /api/v1/status            Health-check.
GET  /api/v1/latest-version    Public — returns latest published release info.

Admin (require Authorization: Bearer <ADMIN_TOKEN>)
----------------------------------------------------
POST /admin/keys/create        Generate new license key(s) and add to pool.
POST /admin/keys/revoke        Revoke an entire license (all seats blocked at next heartbeat).
POST /admin/keys/unrevoke      Un-revoke a license.
POST /admin/reset-seat         Clear bound_fingerprint on a seat (crash recovery).
GET  /admin/view-seats         List all seats and their status for a license key.
GET  /admin/keys               List all licenses in the pool.
POST /admin/release/publish    Publish a new release manifest.

Database schema (JSON-backed; PostgreSQL-ready structure)
---------------------------------------------------------
{
  "licenses": {
    "<key>": {
      "created_for":  str,
      "plan_type":    "single" | "clinic" | "hospital" | "enterprise",
      "max_seats":    int,
      "status":       "unused" | "active" | "revoked",
      "valid_until":  "YYYY-MM-DD" | null,
      "notes":        str,
      "created_at":   int (unix),
      "seats": {
        "1": {
          "bound_fingerprint":  str | null,
          "RhythmUltra_serial":  str | null,
          "machine_serial_id":  str | null,
          "pc_name":            str | null,
          "windows_version":    str | null,
          "status":             "available" | "active" | "crashed",
          "activated_at":       int | null,
          "last_heartbeat":     int | null,
          "full_name":          str | null,
          "doctor_name":        str | null,
          "org_name":           str | null,
          "org_address":        str | null,
          "phone":              str | null,
          "password_hash":      str | null
        }
      }
    }
  }
}

Backward-compat migration
-------------------------
On startup, any old-style entry under "keys" is migrated to "licenses" with a
single seat per activation.  Old /activate and /validate endpoints still work.

Setup
-----
pip install flask

Set environment variables:
  LICENSE_HMAC_SECRET   — same secret used in license_manager.py
  ADMIN_TOKEN           — bearer token for /admin/* endpoints
  PORT                  — defaults to 5000

Run:
  python server.py
"""

import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass

from flask import Flask, jsonify, request, abort  # type: ignore

# ── Configuration ─────────────────────────────────────────────────────────────
HMAC_SECRET: bytes = os.getenv(
    "LICENSE_HMAC_SECRET", "CHANGE_ME_32_BYTES_RANDOM_SECRET!"
).encode()
ADMIN_TOKEN: str = os.getenv("ADMIN_TOKEN", "CHANGE_THIS_ADMIN_TOKEN")
PORT: int = int(os.getenv("PORT", 5000))
DB_FILE: Path = Path(os.getenv("LICENSE_DB", "license_db.json"))
RELEASE_FILE: Path = Path(os.getenv("RELEASE_MANIFEST", "release_manifest.json"))

_B32_ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TIER_NAMES = {0: "Trial", 1: "Standard", 2: "Professional", 3: "Enterprise"}
MAX_ACTIVATIONS = {0: 1, 1: 2, 2: 3, 3: 10}

# Plan type → default max seats mapping
PLAN_SEATS = {
    "single": 1,
    "clinic": 3,
    "hospital": 5,
    "enterprise": 10,
}

app = Flask(__name__)

MAX_REGISTRATIONS_PER_DEVICE = 5


# ── Database ──────────────────────────────────────────────────────────────────

def _load_db() -> dict:
    if DB_FILE.exists():
        try:
            data = json.loads(DB_FILE.read_text(encoding="utf-8"))
            # Ensure top-level structure is correct
            if "licenses" not in data:
                data["licenses"] = {}
            return data
        except Exception:
            pass
    return {"licenses": {}, "keys": {}}  # "keys" kept for legacy migration


def _save_db(db: dict) -> None:
    DB_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")


def _migrate_legacy(db: dict) -> dict:
    """
    One-time migration: convert old 'keys' dict (key→activations) to
    the new 'licenses' dict (key→seats).  Runs on every load but is
    idempotent — already-migrated keys are skipped.
    """
    old_keys = db.get("keys", {})
    if not old_keys:
        return db

    changed = False
    for key, entry in list(old_keys.items()):
        if key in db.get("licenses", {}):
            continue  # already migrated
        if not isinstance(entry, dict):
            continue

        activations = entry.get("activations", {})
        seats: dict = {}
        seat_num = 1
        for fp, act in activations.items():
            seats[str(seat_num)] = {
                "bound_fingerprint": fp,
                "RhythmUltra_serial": None,
                "machine_serial_id": act.get("machine_name", ""),
                "pc_name": act.get("machine_name", ""),
                "windows_version": None,
                "status": "active",
                "activated_at": act.get("activated_at"),
                "last_heartbeat": act.get("last_seen"),
                "full_name": None,
                "doctor_name": None,
                "org_name": None,
                "org_address": None,
                "phone": None,
                "password_hash": None,
            }
            seat_num += 1

        tier = entry.get("tier", 1)
        db["licenses"][key] = {
            "created_for": "Migrated from legacy",
            "plan_type": list(PLAN_SEATS.keys())[min(tier, len(PLAN_SEATS) - 1)],
            "max_seats": MAX_ACTIVATIONS.get(tier, 1),
            "status": "revoked" if entry.get("revoked") else ("active" if seats else "unused"),
            "valid_until": None,
            "notes": "Auto-migrated from v1 schema",
            "created_at": entry.get("created_at", int(time.time())),
            "seats": seats,
        }
        changed = True

    if changed:
        # Remove migrated keys to avoid confusion
        db.pop("keys", None)
        _save_db(db)

    return db


def get_db() -> dict:
    """Load DB and run migration if needed."""
    db = _load_db()
    db = _migrate_legacy(db)
    if "licenses" not in db:
        db["licenses"] = {}
    return db


# ── License Key Codec ─────────────────────────────────────────────────────────

def _b32_encode(data: bytes) -> str:
    result, acc, bits = [], 0, 0
    for byte in data:
        acc = (acc << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            result.append(_B32_ALPHA[(acc >> bits) & 0x1F])
    if bits > 0:
        result.append(_B32_ALPHA[(acc << (5 - bits)) & 0x1F])
    return "".join(result)


def _b32_decode(s: str) -> bytes:
    s = s.upper().replace("-", "").replace(" ", "")
    acc, bits, result = 0, 0, []
    for char in s:
        idx = _B32_ALPHA.find(char)
        if idx < 0:
            raise ValueError(f"Invalid base-32 character: {char!r}")
        acc = (acc << 5) | idx
        bits += 5
        if bits >= 8:
            bits -= 8
            result.append((acc >> bits) & 0xFF)
    return bytes(result)


def generate_license_key(tier: int, validity_days: int) -> str:
    expiry = 0 if validity_days == 0 else int(time.time()) + validity_days * 86400
    nonce = secrets.token_bytes(4)
    payload = bytes([tier & 0xFF]) + struct.pack(">I", expiry) + nonce
    checksum = hmac.new(HMAC_SECRET, payload, hashlib.sha256).digest()[:3]
    raw_bytes = payload + checksum
    raw_key = _b32_encode(raw_bytes)
    return "-".join(raw_key[i:i+5] for i in range(0, 20, 5))


def decode_key(license_key: str) -> dict | None:
    try:
        raw = license_key.upper().replace("-", "").replace(" ", "")
        if len(raw) != 20:
            return None
        data = _b32_decode(raw)
        if len(data) < 12:
            return None
        tier = data[0]
        expiry = struct.unpack(">I", data[1:5])[0]
        nonce = data[5:9]
        checksum = data[9:12]
        expected = hmac.new(HMAC_SECRET, data[:9], hashlib.sha256).digest()[:3]
        if not hmac.compare_digest(checksum, expected):
            return None
        return {"tier": tier, "expiry": expiry, "nonce": nonce.hex()}
    except Exception:
        return None


# ── Token issuance ────────────────────────────────────────────────────────────

def _issue_token(
    license_key: str,
    fingerprint: str,
    RhythmUltra_serial: str,
    seat_number: int,
    tier: int,
    expiry: int,
) -> str:
    """
    Build and sign a token payload.
    Returns a base64-encoded JSON envelope: {payload, sig}.
    The client stores this in cardiox.lic.
    """
    now = int(time.time())
    payload = {
        "license_key": license_key,
        "fingerprint": fingerprint,
        "RhythmUltra_serial": RhythmUltra_serial,
        "seat_number": seat_number,
        "tier": tier,
        "expires": expiry,
        "last_server_check": now,
        "issued_at": now,
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    sig = hmac.new(HMAC_SECRET, payload_bytes, hashlib.sha256).hexdigest()
    envelope = {"payload": payload, "sig": sig}
    return json.dumps(envelope)


# ── Request helpers ───────────────────────────────────────────────────────────

def _verify_request_sig() -> bool:
    sig = request.headers.get("X-Request-Sig", "")
    if not sig:
        return True
    body = request.get_data()
    expected = hmac.new(HMAC_SECRET, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _signed_response(data: dict, status: int = 200):
    payload_bytes = json.dumps(data, sort_keys=True).encode()
    sig = hmac.new(HMAC_SECRET, payload_bytes, hashlib.sha256).hexdigest()
    data["server_sig"] = sig
    return jsonify(data), status


def _require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "")
        if token != f"Bearer {ADMIN_TOKEN}":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _find_seat_by_fingerprint(license_entry: dict, fingerprint: str) -> tuple[str | None, dict | None]:
    """Return (seat_number_str, seat_dict) for a bound fingerprint, or (None, None)."""
    for seat_num, seat in license_entry.get("seats", {}).items():
        if seat.get("bound_fingerprint") == fingerprint:
            return seat_num, seat
    return None, None


def _find_seat_by_machine_serial(license_entry: dict, machine_serial_id: str) -> tuple[str | None, dict | None]:
    """Return (seat_number_str, seat_dict) for a bound machine serial, or (None, None)."""
    if not machine_serial_id:
        return None, None
    for seat_num, seat in license_entry.get("seats", {}).items():
        if (seat.get("machine_serial_id") or "") == machine_serial_id:
            return seat_num, seat
    return None, None


def _find_seat_by_RhythmUltra(license_entry: dict, RhythmUltra_serial: str) -> tuple[str | None, dict | None]:
    """Return (seat_number_str, seat_dict) for a bound RhythmUltra serial, or (None, None)."""
    for seat_num, seat in license_entry.get("seats", {}).items():
        stored_serial = seat.get("RhythmUltra_serial") or seat.get("rhythmulta_serial") or seat.get("rhythmultra_serial")
        if stored_serial == RhythmUltra_serial and RhythmUltra_serial:
            return seat_num, seat
    return None, None


def _find_global_seat_by_RhythmUltra(
    db: dict,
    RhythmUltra_serial: str,
    *,
    exclude_license_key: str | None = None,
    exclude_seat_num: str | None = None,
) -> tuple[str | None, str | None, dict | None]:
    """Return the first active seat using this RhythmUltra serial anywhere in the DB."""
    if not RhythmUltra_serial:
        return None, None, None

    for license_key, license_entry in db.get("licenses", {}).items():
        for seat_num, seat in license_entry.get("seats", {}).items():
            if license_key == exclude_license_key and exclude_seat_num is not None and seat_num == str(exclude_seat_num):
                continue
            stored_serial = seat.get("RhythmUltra_serial") or seat.get("rhythmulta_serial") or seat.get("rhythmultra_serial")
            if seat.get("status") == "active" and stored_serial == RhythmUltra_serial:
                return license_key, seat_num, seat
    return None, None, None


def _count_active_registrations_by_RhythmUltra(
    db: dict,
    RhythmUltra_serial: str,
    *,
    exclude_license_key: str | None = None,
    exclude_seat_num: str | None = None,
) -> int:
    """Count active registrations using this RhythmUltra serial across the DB, with optional exclusion."""
    if not RhythmUltra_serial:
        return 0
    count = 0
    for license_key, license_entry in db.get("licenses", {}).items():
        for seat_num, seat in license_entry.get("seats", {}).items():
            if license_key == exclude_license_key and exclude_seat_num is not None and seat_num == str(exclude_seat_num):
                continue
            stored_serial = seat.get("RhythmUltra_serial") or seat.get("rhythmulta_serial") or seat.get("rhythmultra_serial")
            if seat.get("status") == "active" and stored_serial == RhythmUltra_serial:
                count += 1
    return count


def _clear_license_seat_bindings(license_entry: dict) -> int:
    """
    Remove machine/device bindings from all seats on a license.

    This keeps the seat slots around, but makes them reusable after a revoke
    or admin reset without leaving stale machine associations behind.
    """
    cleared = 0
    for seat in license_entry.get("seats", {}).values():
        if not isinstance(seat, dict):
            continue
        if (seat.get("bound_fingerprint") is not None or 
            seat.get("RhythmUltra_serial") is not None or 
            seat.get("rhythmulta_serial") is not None or 
            seat.get("rhythmultra_serial") is not None):
            cleared += 1
        seat["bound_fingerprint"] = None
        seat["RhythmUltra_serial"] = None
        seat["rhythmulta_serial"] = None
        seat["rhythmultra_serial"] = None
        seat["machine_serial_id"] = None
        seat["pc_name"] = None
        seat["windows_version"] = None
        seat["status"] = "available"
        seat["activated_at"] = None
        seat["last_heartbeat"] = None
    return cleared


def _license_has_bound_seats(license_entry: dict) -> bool:
    for seat in license_entry.get("seats", {}).values():
        if isinstance(seat, dict) and seat.get("bound_fingerprint"):
            return True
    return False


def _next_available_seat(license_entry: dict) -> str | None:
    """Return seat number str of the next available seat, or None if all taken."""
    max_seats = license_entry.get("max_seats", 1)
    seats = license_entry.setdefault("seats", {})
    # First look for an existing 'available' slot
    for seat_num, seat in seats.items():
        if seat.get("status") in ("available", None) and seat.get("bound_fingerprint") is None:
            return seat_num
    # If fewer seats than max, create a new slot
    if len(seats) < max_seats:
        new_num = str(max(int(k) for k in seats.keys()) + 1 if seats else 1)
        return new_num
    return None


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/v1/status")
def status():
    return jsonify({
        "status": "ok",
        "product": "CardioX License Server",
        "version": "2.0.0",
        "time": datetime.now(timezone.utc).isoformat(),
    })


# ── NEW: Registration endpoint (Three-Pillar Architecture) ────────────────────

@app.post("/api/v1/register")
def register():
    """
    First-time device registration.

    Validation sequence (§3.3 of the SDD):
      1. License key valid and not expired?
      2. License not revoked / has available seats?
      3. Hardware fingerprint unique across all seats?
      4. RhythmUltra serial unique across all seats?
    On success: create seat, issue signed token.
    """
    if not _verify_request_sig():
        return _signed_response({"valid": False, "message": "Bad request signature."}, 400)

    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    fingerprint = body.get("hardware_fingerprint", "").strip()
    RhythmUltra_serial = body.get("RhythmUltra_serial", body.get("rhythmulta_serial", body.get("rhythmultra_serial", ""))).strip()
    full_name = body.get("full_name", "")
    doctor_name = body.get("doctor_name", "")
    org_name = body.get("org_name", "")
    org_address = body.get("org_address", "")
    phone = body.get("phone", "")
    password_hash = body.get("password_hash", "")
    machine_serial_id = body.get("machine_serial_id", "")
    pc_name = body.get("pc_name", "")
    windows_version = body.get("windows_version", "")

    if not fingerprint:
        return _signed_response({"valid": False, "message": "Missing hardware fingerprint."}, 400)

    db = get_db()
    if not license_key:
        for k, entry in db.get("licenses", {}).items():
            if entry.get("status") == "unused":
                license_key = k
                break
        if not license_key:
            return _signed_response({"valid": False, "message": "No unused license keys available on the server."}, 400)

    # Decode and verify key format
    key_data = decode_key(license_key)
    if key_data is None:
        return _signed_response({"valid": False, "message": "Invalid license key."}, 400)

    now = int(time.time())
    if key_data["expiry"] != 0 and now > key_data["expiry"]:
        return _signed_response({"valid": False, "message": "License key has expired."}, 403)

    db = get_db()
    license_entry = db["licenses"].get(license_key)

    # Create license entry if this is the first registration for this key
    if license_entry is None:
        tier = key_data["tier"]
        license_entry = {
            "created_for": org_name or full_name or "Unknown",
            "plan_type": list(PLAN_SEATS.keys())[min(tier, len(PLAN_SEATS) - 1)],
            "max_seats": MAX_ACTIVATIONS.get(tier, 1),
            "status": "unused",
            "valid_until": None,
            "notes": "",
            "created_at": now,
            "seats": {},
        }

    if license_entry.get("status") == "revoked":
        return _signed_response({"valid": False, "message": "License has been revoked."}, 403)

    # ── Check 2: Seat available? ──────────────────────────────────────────────
    # First check if this fingerprint is already registered (re-registration OK)
    seat_num, existing_seat = _find_seat_by_fingerprint(license_entry, fingerprint)

    if existing_seat is not None:
        # Re-registration of same machine — update seat info and re-issue token
        if RhythmUltra_serial:
            active_count = _count_active_registrations_by_RhythmUltra(
                db,
                RhythmUltra_serial,
                exclude_license_key=license_key,
                exclude_seat_num=seat_num,
            )
            if active_count >= MAX_REGISTRATIONS_PER_DEVICE:
                return _signed_response({
                    "valid": False,
                    "error": "DEVICE_ALREADY_REGISTERED",
                    "message": f"Maximum {MAX_REGISTRATIONS_PER_DEVICE} activations allowed for this RhythmUltra device."
                }, 403)
        existing_seat["last_heartbeat"] = now
        existing_seat["pc_name"] = pc_name or existing_seat.get("pc_name", "")
        existing_seat["status"] = "active"
        # Update RhythmUltra if provided and not already bound
        if RhythmUltra_serial and not existing_seat.get("RhythmUltra_serial"):
            existing_seat["RhythmUltra_serial"] = RhythmUltra_serial
        db["licenses"][license_key] = license_entry
        _save_db(db)

        token_str = _issue_token(
            license_key, fingerprint,
            existing_seat.get("RhythmUltra_serial", ""),
            int(seat_num), key_data["tier"], key_data["expiry"],
        )
        return _signed_response({
            "valid": True,
            "message": "Device re-registered successfully.",
            "seat_number": int(seat_num),
            "tier": key_data["tier"],
            "tier_name": TIER_NAMES.get(key_data["tier"], "Unknown"),
            "expires": key_data["expiry"],
            "token": token_str,
        })

    # ── Check 3: Hardware fingerprint unique? ─────────────────────────────────
    # Already checked above — no match means fingerprint is unique.

    # ── Check 3b: RhythmUltra serial unique? ──────────────────────────────────
    if RhythmUltra_serial:
        active_count = _count_active_registrations_by_RhythmUltra(db, RhythmUltra_serial)
        if active_count >= MAX_REGISTRATIONS_PER_DEVICE:
            return _signed_response({
                "valid": False,
                "error": "DEVICE_ALREADY_REGISTERED",
                "message": f"Maximum {MAX_REGISTRATIONS_PER_DEVICE} activations allowed for this RhythmUltra device."
            }, 403)

    # ── Check 2b: Find next available seat ───────────────────────────────────
    next_seat = _next_available_seat(license_entry)
    if next_seat is None:
        max_seats = license_entry.get("max_seats", 1)
        return _signed_response({
            "valid": False,
            "message": f"All {max_seats} seat(s) for this license are in use. Contact Deckmount to upgrade.",
        }, 403)

    # ── Create seat ───────────────────────────────────────────────────────────
    new_seat = {
        "bound_fingerprint": fingerprint,
        "RhythmUltra_serial": RhythmUltra_serial or None,
        "machine_serial_id": machine_serial_id,
        "pc_name": pc_name,
        "windows_version": windows_version,
        "status": "active",
        "activated_at": now,
        "last_heartbeat": now,
        "full_name": full_name,
        "doctor_name": doctor_name,
        "org_name": org_name,
        "org_address": org_address,
        "phone": phone,
        "password_hash": password_hash,
    }
    license_entry["seats"][next_seat] = new_seat
    license_entry["status"] = "active"
    db["licenses"][license_key] = license_entry
    _save_db(db)

    # ── Issue signed token ────────────────────────────────────────────────────
    token_str = _issue_token(
        license_key, fingerprint, RhythmUltra_serial,
        int(next_seat), key_data["tier"], key_data["expiry"],
    )

    return _signed_response({
        "valid": True,
        "message": "Registration successful.",
        "seat_number": int(next_seat),
        "license_key": license_key,
        "tier": key_data["tier"],
        "tier_name": TIER_NAMES.get(key_data["tier"], "Unknown"),
        "expires": key_data["expiry"],
        "token": token_str,
    }, 201)


# ── NEW: Heartbeat endpoint ───────────────────────────────────────────────────

@app.post("/api/v1/heartbeat")
def heartbeat():
    """
    7-day check-in.  Verifies license not revoked.  Updates last_heartbeat.
    The client calls this only when > 7 days have passed since last check.
    """
    if not _verify_request_sig():
        return _signed_response({"valid": False, "message": "Bad request signature."}, 400)

    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    fingerprint = body.get("hardware_fingerprint", "").strip()
    machine_serial_id = body.get("machine_serial_id", "").strip()
    seat_number = body.get("seat_number", None)

    if not license_key or not fingerprint:
        return _signed_response({"valid": False, "message": "Missing required fields."}, 400)

    db = get_db()
    license_entry = db["licenses"].get(license_key)

    if license_entry is None:
        return _signed_response({"valid": False, "message": "License key not found."}, 404)

    if license_entry.get("status") == "revoked":
        return _signed_response({"valid": False, "revoked": True, "message": "License has been revoked."}, 403)

    # Check key expiry
    key_data = decode_key(license_key)
    now = int(time.time())
    if key_data and key_data["expiry"] != 0 and now > key_data["expiry"]:
        return _signed_response({"valid": False, "message": "License has expired."}, 403)

    # Find the seat by fingerprint and update heartbeat
    seat_num, seat = _find_seat_by_fingerprint(license_entry, fingerprint)
    if seat is None and machine_serial_id:
        seat_num, seat = _find_seat_by_machine_serial(license_entry, machine_serial_id)
        if seat is not None:
            seat["bound_fingerprint"] = fingerprint

    if seat is None:
        return _signed_response({
            "valid": False,
            "message": "This machine is not registered under this license. Please register first.",
        }, 403)

    if seat.get("status") == "crashed":
        return _signed_response({
            "valid": False,
            "message": "This seat has been flagged as crashed. Please contact Deckmount support.",
        }, 403)

    seat["last_heartbeat"] = now
    seat["status"] = "active"
    seat["machine_serial_id"] = machine_serial_id or seat.get("machine_serial_id")
    db["licenses"][license_key] = license_entry
    _save_db(db)

    return _signed_response({
        "valid": True,
        "message": "Heartbeat accepted.",
        "seat_number": int(seat_num),
        "tier": key_data["tier"] if key_data else 0,
        "tier_name": TIER_NAMES.get(key_data["tier"] if key_data else 0, "Unknown"),
        "expires": key_data["expiry"] if key_data else 0,
        "rebound": bool(machine_serial_id),
    })


# ── NEW: Deactivate ───────────────────────────────────────────────────────────

@app.post("/api/v1/deactivate")
def deactivate():
    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    fingerprint = body.get("hardware_fingerprint", "").strip()

    db = get_db()
    entry = db["licenses"].get(license_key)
    if entry:
        seat_num, seat = _find_seat_by_fingerprint(entry, fingerprint)
        if seat is not None:
            seat["bound_fingerprint"] = None
            seat["RhythmUltra_serial"] = None
            seat["status"] = "available"
            db["licenses"][license_key] = entry
            _save_db(db)

    return _signed_response({"success": True, "message": "Seat deactivated."})


# ── Legacy: Activate (v1 compat) ──────────────────────────────────────────────

@app.post("/api/v1/activate")
def activate():
    """Legacy activation endpoint — kept for backward compatibility."""
    if not _verify_request_sig():
        return _signed_response({"valid": False, "message": "Bad request signature."}, 400)

    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    fingerprint = body.get("hardware_fingerprint", "").strip()
    machine_name = body.get("machine_name", "")
    machine_serial_id = body.get("machine_serial_id", "") or machine_name
    RhythmUltra_serial = body.get("RhythmUltra_serial", body.get("rhythmulta_serial", body.get("rhythmultra_serial", ""))).strip()

    if not license_key or not fingerprint:
        return _signed_response({"valid": False, "message": "Missing required fields."}, 400)

    # Delegate to new register flow with minimal fields
    body["RhythmUltra_serial"] = body.get("RhythmUltra_serial", "")
    body["pc_name"] = machine_name
    body["machine_serial_id"] = machine_serial_id

    # Call register logic inline
    key_data = decode_key(license_key)
    if key_data is None:
        return _signed_response({"valid": False, "message": "Invalid license key."}, 400)

    now = int(time.time())
    if key_data["expiry"] != 0 and now > key_data["expiry"]:
        return _signed_response({"valid": False, "message": "License key has expired."}, 403)

    db = get_db()
    license_entry = db["licenses"].get(license_key)
    if license_entry is None:
        tier = key_data["tier"]
        license_entry = {
            "created_for": machine_serial_id or machine_name or "Legacy activation",
            "plan_type": list(PLAN_SEATS.keys())[min(tier, len(PLAN_SEATS) - 1)],
            "max_seats": MAX_ACTIVATIONS.get(tier, 1),
            "status": "unused",
            "valid_until": None,
            "notes": "Created via legacy /activate",
            "created_at": now,
            "seats": {},
        }

    if license_entry.get("status") == "revoked":
        return _signed_response({"valid": False, "message": "License has been revoked."}, 403)

    seat_num, existing_seat = _find_seat_by_fingerprint(license_entry, fingerprint)
    if existing_seat is not None:
        if RhythmUltra_serial:
            active_count = _count_active_registrations_by_RhythmUltra(
                db,
                RhythmUltra_serial,
                exclude_license_key=license_key,
                exclude_seat_num=seat_num,
            )
            if active_count >= MAX_REGISTRATIONS_PER_DEVICE:
                return _signed_response({
                    "valid": False,
                    "error": "DEVICE_ALREADY_REGISTERED",
                    "message": f"Maximum {MAX_REGISTRATIONS_PER_DEVICE} activations allowed for this RhythmUltra device."
                }, 403)
        existing_seat["last_heartbeat"] = now
        existing_seat["machine_serial_id"] = machine_serial_id or existing_seat.get("machine_serial_id", "")
        existing_seat["pc_name"] = machine_name or existing_seat.get("pc_name", "")
        if RhythmUltra_serial and not existing_seat.get("RhythmUltra_serial"):
            existing_seat["RhythmUltra_serial"] = RhythmUltra_serial
        db["licenses"][license_key] = license_entry
        _save_db(db)
        return _signed_response({
            "valid": True,
            "message": "Activation successful.",
            "tier": key_data["tier"],
            "tier_name": TIER_NAMES.get(key_data["tier"], "Unknown"),
            "expires": key_data["expiry"],
        })

    next_seat = _next_available_seat(license_entry)
    if next_seat is None:
        return _signed_response({
            "valid": False,
            "message": f"Maximum activations reached for this license.",
        }, 403)

    if RhythmUltra_serial:
        active_count = _count_active_registrations_by_RhythmUltra(db, RhythmUltra_serial)
        if active_count >= MAX_REGISTRATIONS_PER_DEVICE:
            return _signed_response({
                "valid": False,
                "error": "DEVICE_ALREADY_REGISTERED",
                "message": f"Maximum {MAX_REGISTRATIONS_PER_DEVICE} activations allowed for this RhythmUltra device."
            }, 403)

    license_entry["seats"][next_seat] = {
        "bound_fingerprint": fingerprint,
        "RhythmUltra_serial": RhythmUltra_serial or None,
        "machine_serial_id": machine_serial_id,
        "pc_name": machine_name,
        "windows_version": body.get("machine_os", ""),
        "status": "active",
        "activated_at": now,
        "last_heartbeat": now,
        "full_name": None,
        "doctor_name": None,
        "org_name": None,
        "org_address": None,
        "phone": None,
        "password_hash": None,
    }
    license_entry["status"] = "active"
    db["licenses"][license_key] = license_entry
    _save_db(db)

    return _signed_response({
        "valid": True,
        "message": "Activation successful.",
        "tier": key_data["tier"],
        "tier_name": TIER_NAMES.get(key_data["tier"], "Unknown"),
        "expires": key_data["expiry"],
    })


# ── Legacy: Validate (v1 compat) ──────────────────────────────────────────────

@app.post("/api/v1/validate")
def validate():
    """Legacy validate endpoint — delegates to heartbeat logic."""
    if not _verify_request_sig():
        return _signed_response({"valid": False, "message": "Bad request signature."}, 400)

    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    fingerprint = body.get("hardware_fingerprint", "").strip()

    if not license_key or not fingerprint:
        return _signed_response({"valid": False, "message": "Missing required fields."}, 400)

    key_data = decode_key(license_key)
    if key_data is None:
        return _signed_response({"valid": False, "message": "Invalid license key."}, 400)

    now = int(time.time())
    if key_data["expiry"] != 0 and now > key_data["expiry"]:
        return _signed_response({"valid": False, "message": "License key has expired."}, 403)

    db = get_db()
    license_entry = db["licenses"].get(license_key)

    if license_entry is None:
        # Key passes checksum but never registered — delegate to activate
        with app.test_request_context(
            "/api/v1/activate",
            method="POST",
            json=body,
        ):
            return activate()

    if license_entry.get("status") == "revoked":
        return _signed_response({"valid": False, "revoked": True, "message": "License has been revoked."}, 403)

    seat_num, seat = _find_seat_by_fingerprint(license_entry, fingerprint)
    if seat is None and machine_serial_id:
        seat_num, seat = _find_seat_by_machine_serial(license_entry, machine_serial_id)
        if seat is not None:
            seat["bound_fingerprint"] = fingerprint

    if seat is None:
        # Not registered on this machine — try to activate
        with app.test_request_context(
            "/api/v1/activate",
            method="POST",
            json=body,
        ):
            return activate()

    seat["last_heartbeat"] = now
    seat["machine_serial_id"] = machine_serial_id or seat.get("machine_serial_id")
    db["licenses"][license_key] = license_entry
    _save_db(db)

    return _signed_response({
        "valid": True,
        "message": "License valid.",
        "tier": key_data["tier"],
        "tier_name": TIER_NAMES.get(key_data["tier"], "Unknown"),
        "expires": key_data["expiry"],
        "activations": len(license_entry.get("seats", {})),
        "seat_number": int(seat_num),
        "rebound": bool(machine_serial_id),
    })


# ── Release Manifest ──────────────────────────────────────────────────────────

def _load_release_manifest() -> dict:
    if RELEASE_FILE.exists():
        try:
            return json.loads(RELEASE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_release_manifest(data: dict) -> None:
    RELEASE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


@app.get("/api/v1/latest-version")
def latest_version():
    channel = request.args.get("channel", "stable").strip().lower()
    manifest = _load_release_manifest()
    channel_data = manifest.get(channel)
    if not channel_data:
        return jsonify({"channel": channel, "version": None, "message": "No release published yet."}), 404
    return jsonify(channel_data)


@app.post("/admin/release/publish")
@_require_admin
def admin_publish_release():
    body = request.get_json(silent=True) or {}
    version = body.get("version", "").strip()
    if not version:
        return jsonify({"error": "'version' is required."}), 400
    channel = body.get("channel", "stable").strip().lower()
    manifest = _load_release_manifest()
    manifest[channel] = {
        "version": version,
        "channel": channel,
        "release_notes": body.get("release_notes", "").strip(),
        "download_url": body.get("download_url", "").strip(),
        "force_notify": bool(body.get("force_notify", False)),
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_release_manifest(manifest)
    return jsonify({"success": True, "message": f"Published v{version} to '{channel}'.", "data": manifest[channel]})


# ── Admin Endpoints ───────────────────────────────────────────────────────────

@app.get("/admin/keys")
@_require_admin
def admin_list_keys():
    db = get_db()
    now = int(time.time())
    result = []
    for key, entry in db["licenses"].items():
        key_data = decode_key(key)
        exp = key_data["expiry"] if key_data else 0
        seats_count = len([
            s for s in entry.get("seats", {}).values()
            if s.get("bound_fingerprint")
        ])
        result.append({
            "key": key,
            "created_for": entry.get("created_for", ""),
            "plan_type": entry.get("plan_type", ""),
            "max_seats": entry.get("max_seats", 1),
            "active_seats": seats_count,
            "status": entry.get("status", "unknown"),
            "expiry": datetime.fromtimestamp(exp, timezone.utc).isoformat() if exp else "perpetual",
            "expired": (exp != 0 and now > exp),
        })
    return jsonify({"licenses": result, "total": len(result)})


@app.post("/admin/keys/create")
@_require_admin
def admin_create_key():
    body = request.get_json(silent=True) or {}
    tier = int(body.get("tier", 1))
    days = int(body.get("validity_days", 365))
    count = int(body.get("count", 1))
    plan_type = body.get("plan_type", list(PLAN_SEATS.keys())[min(tier, len(PLAN_SEATS) - 1)])
    max_seats = int(body.get("max_seats", PLAN_SEATS.get(plan_type, 1)))
    created_for = body.get("created_for", "")
    notes = body.get("notes", "")

    if tier not in TIER_NAMES:
        return jsonify({"error": "Invalid tier."}), 400

    db = get_db()
    keys = []
    now = int(time.time())
    for _ in range(min(count, 100)):
        key = generate_license_key(tier, days)
        keys.append(key)
        db["licenses"][key] = {
            "created_for": created_for,
            "plan_type": plan_type,
            "max_seats": max_seats,
            "status": "unused",
            "valid_until": None,
            "notes": notes,
            "created_at": now,
            "seats": {},
        }
    _save_db(db)

    return jsonify({
        "keys": keys,
        "tier": TIER_NAMES[tier],
        "plan_type": plan_type,
        "max_seats": max_seats,
        "expires_in_days": days if days else "perpetual",
    })


@app.post("/admin/keys/revoke")
@_require_admin
def admin_revoke_key():
    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    db = get_db()
    if license_key not in db["licenses"]:
        db["licenses"][license_key] = {
            "created_for": "",
            "plan_type": "single",
            "max_seats": 1,
            "status": "revoked",
            "valid_until": None,
            "notes": "Revoked before first registration",
            "created_at": int(time.time()),
            "seats": {},
        }
    entry = db["licenses"][license_key]
    cleared = _clear_license_seat_bindings(entry)
    entry["status"] = "revoked"
    entry["revoked_at"] = int(time.time())
    entry["revoked_seats_cleared"] = cleared
    db["licenses"][license_key] = entry
    _save_db(db)
    return jsonify({
        "success": True,
        "message": f"License {license_key} revoked.",
        "cleared_seats": cleared,
    })


@app.post("/admin/keys/unrevoke")
@_require_admin
def admin_unrevoke_key():
    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    db = get_db()
    if license_key in db["licenses"]:
        entry = db["licenses"][license_key]
        # Restore to active only if at least one seat is still actually bound.
        # If revoke cleared bindings, the license should go back to unused.
        entry["status"] = "active" if _license_has_bound_seats(entry) else "unused"
        entry.pop("revoked_at", None)
        entry.pop("revoked_seats_cleared", None)
        db["licenses"][license_key] = entry
        _save_db(db)
    return jsonify({"success": True, "message": f"License {license_key} un-revoked."})


@app.post("/admin/reset-seat")
@_require_admin
def admin_reset_seat():
    """
    Crash recovery: clear the bound_fingerprint and RhythmUltra serial
    on a specific seat so the user can re-register on a new machine.
    """
    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    # Accept seat_number as int or str
    seat_number = str(body.get("seat_number", "1"))
    # Optionally identify seat by fingerprint instead
    fingerprint = body.get("bound_fingerprint", "").strip()

    if not license_key:
        return jsonify({"error": "'license_key' is required."}), 400

    db = get_db()
    entry = db["licenses"].get(license_key)
    if entry is None:
        return jsonify({"error": "License key not found."}), 404

    seats = entry.get("seats", {})
    target_seat = None
    target_key = None

    if fingerprint:
        # Find seat by fingerprint
        for sn, seat in seats.items():
            if seat.get("bound_fingerprint") == fingerprint:
                target_seat = seat
                target_key = sn
                break
        if target_seat is None:
            return jsonify({"error": "No seat found with that fingerprint."}), 404
    elif seat_number in seats:
        target_seat = seats[seat_number]
        target_key = seat_number
    else:
        return jsonify({"error": f"Seat {seat_number} not found."}), 404

    old_fp = target_seat.get("bound_fingerprint", "")
    target_seat["bound_fingerprint"] = None
    target_seat["RhythmUltra_serial"] = None
    target_seat["status"] = "available"
    target_seat["reset_at"] = int(time.time())

    db["licenses"][license_key] = entry
    _save_db(db)

    return jsonify({
        "success": True,
        "message": f"Seat {target_key} reset. Old fingerprint cleared.",
        "seat_number": int(target_key),
        "old_fingerprint": old_fp,
    })


@app.get("/admin/view-seats")
@_require_admin
def admin_view_seats():
    """List all seats for a given license key."""
    license_key = request.args.get("license_key", "").strip().upper()
    if not license_key:
        return jsonify({"error": "'license_key' query parameter is required."}), 400

    db = get_db()
    entry = db["licenses"].get(license_key)
    if entry is None:
        return jsonify({"error": "License key not found."}), 404

    seats_out = []
    for seat_num, seat in sorted(entry.get("seats", {}).items(), key=lambda x: int(x[0])):
        last_hb = seat.get("last_heartbeat")
        seats_out.append({
            "seat_number": int(seat_num),
            "status": seat.get("status", "unknown"),
            "bound_fingerprint": seat.get("bound_fingerprint") or "(unbound)",
            "RhythmUltra_serial": seat.get("RhythmUltra_serial") or "(unbound)",
            "pc_name": seat.get("pc_name") or "",
            "machine_serial_id": seat.get("machine_serial_id") or "",
            "windows_version": seat.get("windows_version") or "",
            "full_name": seat.get("full_name") or "",
            "doctor_name": seat.get("doctor_name") or "",
            "org_name": seat.get("org_name") or "",
            "phone": seat.get("phone") or "",
            "activated_at": (
                datetime.fromtimestamp(seat["activated_at"], timezone.utc).isoformat()
                if seat.get("activated_at") else None
            ),
            "last_heartbeat": (
                datetime.fromtimestamp(last_hb, timezone.utc).isoformat()
                if last_hb else None
            ),
        })

    return jsonify({
        "license_key": license_key,
        "created_for": entry.get("created_for", ""),
        "plan_type": entry.get("plan_type", ""),
        "max_seats": entry.get("max_seats", 1),
        "status": entry.get("status", ""),
        "valid_until": entry.get("valid_until"),
        "notes": entry.get("notes", ""),
        "seats": seats_out,
        "total_seats": len(seats_out),
        "active_seats": len([s for s in seats_out if s["status"] == "active"]),
    })


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[LicenseServer v2.0] Starting on port {PORT}")
    print(f"[LicenseServer] DB: {DB_FILE.resolve()}")
    secret_ok = HMAC_SECRET != b"CHANGE_ME_32_BYTES_RANDOM_SECRET!"
    print(f"[LicenseServer] HMAC secret configured: {'YES' if secret_ok else 'NO — change it!'}")
    # Run migration on startup
    db = get_db()
    print(f"[LicenseServer] Licenses in pool: {len(db.get('licenses', {}))}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
