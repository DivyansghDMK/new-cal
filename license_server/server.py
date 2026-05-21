"""
license_server/server.py
========================
CardioX License Validation Server (Flask).

Endpoints
---------
POST /api/v1/activate          First-time activation (ties key to hardware).
POST /api/v1/validate          Validate an already-activated key.
POST /api/v1/deactivate        Release a seat.
GET  /api/v1/status            Health-check.
GET  /api/v1/latest-version    Public — returns latest published release info.
GET  /admin/keys               List all keys (requires admin token).
POST /admin/keys/create        Create a new license key.
POST /admin/keys/revoke        Revoke a license key.
POST /admin/release/publish    Publish a new release manifest (admin only).

Setup
-----
pip install flask flask-limiter

Set environment variables before running:
  LICENSE_HMAC_SECRET   — same secret as in license_manager.py
  ADMIN_TOKEN           — bearer token for /admin/* endpoints
  PORT                  — defaults to 5000

Run:
  python server.py

For production use a proper WSGI server (gunicorn, etc.) behind HTTPS (nginx).
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
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, jsonify, request, abort
from dotenv import find_dotenv, load_dotenv

# Load environment variables from the project .env or the current working dir.
load_dotenv(find_dotenv(usecwd=True), override=False)

# ── Configuration ─────────────────────────────────────────────────────────────
HMAC_SECRET: bytes = os.getenv(
    "LICENSE_HMAC_SECRET", "CHANGE_ME_32_BYTES_RANDOM_SECRET!"
).encode()
ADMIN_TOKEN: str   = os.getenv("ADMIN_TOKEN", "CHANGE_THIS_ADMIN_TOKEN")
PORT: int               = int(os.getenv("PORT", 5000))
DB_FILE: Path           = Path(os.getenv("LICENSE_DB", "license_db.json"))
RELEASE_FILE: Path      = Path(os.getenv("RELEASE_MANIFEST", "release_manifest.json"))

# Base-32 alphabet (no ambiguous 0/O, 1/I)
_B32_ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

TIER_NAMES = {0: "Trial", 1: "Standard", 2: "Professional", 3: "Enterprise"}
MAX_ACTIVATIONS = {0: 1, 1: 2, 2: 3, 3: 10}  # Allow 2 activations for Standard tier

app = Flask(__name__)

# ── Database (simple JSON file — swap for PostgreSQL in production) ────────────

def _load_db() -> dict:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text())
        except Exception:
            pass
    return {"keys": {}}


def _save_db(db: dict) -> None:
    DB_FILE.write_text(json.dumps(db, indent=2))


# ── License Key Codec (mirrors license_manager.py) ────────────────────────────

def _b32_encode(data: bytes) -> str:
    result = []
    acc = 0
    bits = 0
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
    acc = 0
    bits = 0
    result = []
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
    """
    Create a new signed license key.

    tier          0=trial, 1=standard, 2=pro, 3=enterprise
    validity_days 0 = perpetual; >0 = expires after N days from now
    """
    expiry = 0 if validity_days == 0 else int(time.time()) + validity_days * 86400
    nonce  = secrets.token_bytes(4)

    payload = bytes([tier & 0xFF]) + struct.pack(">I", expiry) + nonce  # 9 bytes
    checksum = hmac.new(HMAC_SECRET, payload, hashlib.sha256).digest()[:3]
    raw_bytes = payload + checksum  # 12 bytes

    raw_key = _b32_encode(raw_bytes)                 # 20 chars
    # Format as XXXXX-XXXXX-XXXXX-XXXXX
    return "-".join(raw_key[i:i+5] for i in range(0, 20, 5))


def decode_key(license_key: str) -> dict | None:
    """Decode and verify a license key. Returns None if invalid."""
    try:
        raw = license_key.upper().replace("-", "").replace(" ", "")
        if len(raw) != 20:
            return None
        data = _b32_decode(raw)
        if len(data) < 12:
            return None
        tier     = data[0]
        expiry   = struct.unpack(">I", data[1:5])[0]
        nonce    = data[5:9]
        checksum = data[9:12]

        expected = hmac.new(HMAC_SECRET, data[:9], hashlib.sha256).digest()[:3]
        if not hmac.compare_digest(checksum, expected):
            return None

        return {"tier": tier, "expiry": expiry, "nonce": nonce.hex()}
    except Exception:
        return None


# ── Request signature verification ────────────────────────────────────────────

def _verify_request_sig() -> bool:
    """Verify that the client signed the request body with the shared secret."""
    sig = request.headers.get("X-Request-Sig", "")
    if not sig:
        return True  # Tolerate missing sig (older clients)
    body = request.get_data()
    expected = hmac.new(HMAC_SECRET, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _signed_response(data: dict, status: int = 200):
    """Return a JSON response signed with the server's HMAC."""
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


# ── API Endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/v1/status")
def status():
    return jsonify({
        "status": "ok",
        "product": "CardioX License Server",
        "time": datetime.now(timezone.utc).isoformat(),
    })


# ── Release Manifest helpers ───────────────────────────────────────────────────

def _load_release_manifest() -> dict:
    """Load the release manifest from disk, or return an empty dict."""
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
    """
    Public endpoint — no authentication required.
    Returns the most-recently published release for the requested channel.

    Query params:
      channel  (optional) — 'stable' or 'beta'. Defaults to 'stable'.
    """
    channel = request.args.get("channel", "stable").strip().lower()
    manifest = _load_release_manifest()
    channel_data = manifest.get(channel)
    if not channel_data:
        return jsonify({
            "channel": channel,
            "version": None,
            "message": "No release published yet for this channel.",
        }), 404
    return jsonify(channel_data)


@app.post("/admin/release/publish")
@_require_admin
def admin_publish_release():
    """
    Admin-only endpoint.
    The designated reviewer calls this (via push_release.py) after testing a
    new build to make it visible to all licensed users.

    Expected JSON body:
      {
        "version": "2026.05.21.1003",
        "channel": "stable",          // optional, default 'stable'
        "release_notes": "...",        // optional
        "download_url": "https://..." // optional
      }
    """
    body = request.get_json(silent=True) or {}
    version = body.get("version", "").strip()
    if not version:
        return jsonify({"error": "'version' is required."}), 400

    channel      = body.get("channel", "stable").strip().lower()
    release_notes = body.get("release_notes", "").strip()
    download_url  = body.get("download_url", "").strip()
    force_notify  = bool(body.get("force_notify", False))   # True = show banner even on rollback

    manifest = _load_release_manifest()
    manifest[channel] = {
        "version":       version,
        "channel":       channel,
        "release_notes": release_notes,
        "download_url":  download_url,
        "force_notify":  force_notify,
        "published_at":  datetime.now(timezone.utc).isoformat(),
    }
    _save_release_manifest(manifest)

    action = "Rollback" if force_notify else "Published"
    return jsonify({
        "success": True,
        "message": f"{action}: version {version} pushed to '{channel}' channel.",
        "data":    manifest[channel],
    })


@app.post("/api/v1/activate")
def activate():
    if not _verify_request_sig():
        return _signed_response({"valid": False, "message": "Bad request signature."}, 400)

    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    fingerprint  = body.get("hardware_fingerprint", "").strip()
    machine_name = body.get("machine_name", "")

    if not license_key or not fingerprint:
        return _signed_response({"valid": False, "message": "Missing required fields."}, 400)

    key_data = decode_key(license_key)
    if key_data is None:
        return _signed_response({"valid": False, "message": "Invalid license key."}, 400)

    now = int(time.time())
    if key_data["expiry"] != 0 and now > key_data["expiry"]:
        return _signed_response({"valid": False, "message": "License key has expired."}, 403)

    db   = _load_db()
    entry = db["keys"].get(license_key)

    if entry is None:
        # First-ever activation
        entry = {
            "tier":          key_data["tier"],
            "expiry":        key_data["expiry"],
            "activations":   {},
            "revoked":       False,
            "created_at":    now,
        }

    if entry.get("revoked"):
        return _signed_response({"valid": False, "message": "License has been revoked."}, 403)

    activations: dict = entry.setdefault("activations", {})
    max_act = MAX_ACTIVATIONS.get(key_data["tier"], 1)

    if fingerprint in activations:
        # Re-activating the same machine — always allowed
        activations[fingerprint]["last_seen"]    = now
        activations[fingerprint]["machine_name"] = machine_name or activations[fingerprint].get("machine_name", "")
    elif len(activations) >= max_act:
        return _signed_response({
            "valid":   False,
            "message": f"Maximum activations ({max_act}) reached for this license tier.",
        }, 403)
    else:
        activations[fingerprint] = {
            "activated_at": now,
            "last_seen":    now,
            "machine_name": machine_name,
        }

    db["keys"][license_key] = entry
    _save_db(db)

    return _signed_response({
        "valid":   True,
        "message": "Activation successful.",
        "tier":    key_data["tier"],
        "tier_name": TIER_NAMES.get(key_data["tier"], "Unknown"),
        "expires": key_data["expiry"],
    })


@app.post("/api/v1/validate")
def validate():
    if not _verify_request_sig():
        return _signed_response({"valid": False, "message": "Bad request signature."}, 400)

    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    fingerprint  = body.get("hardware_fingerprint", "").strip()

    if not license_key or not fingerprint:
        return _signed_response({"valid": False, "message": "Missing required fields."}, 400)

    key_data = decode_key(license_key)
    if key_data is None:
        return _signed_response({"valid": False, "message": "Invalid license key."}, 400)

    now = int(time.time())
    if key_data["expiry"] != 0 and now > key_data["expiry"]:
        return _signed_response({"valid": False, "message": "License key has expired."}, 403)

    db    = _load_db()
    entry = db["keys"].get(license_key)

    if entry is None:
        # Key exists (passes checksum) but was never activated via this server.
        # Auto-activate if there is capacity.
        return activate()   # reuse activation logic

    if entry.get("revoked"):
        return _signed_response({"valid": False, "message": "License has been revoked."}, 403)

    activations: dict = entry.get("activations", {})
    if fingerprint not in activations:
        # This hardware was never activated — try to activate it now.
        return activate()

    # Update last-seen
    activations[fingerprint]["last_seen"] = now
    _save_db(db)

    return _signed_response({
        "valid":      True,
        "message":    "License valid.",
        "tier":       entry["tier"],
        "tier_name":  TIER_NAMES.get(entry["tier"], "Unknown"),
        "expires":    entry["expiry"],
        "activations": len(activations),
    })


@app.post("/api/v1/deactivate")
def deactivate():
    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()
    fingerprint  = body.get("hardware_fingerprint", "").strip()

    db    = _load_db()
    entry = db["keys"].get(license_key)
    if entry and fingerprint in entry.get("activations", {}):
        del entry["activations"][fingerprint]
        _save_db(db)

    return jsonify({"success": True, "message": "Deactivated."})


# ── Admin Endpoints ────────────────────────────────────────────────────────────

@app.get("/admin/keys")
@_require_admin
def admin_list_keys():
    db = _load_db()
    now = int(time.time())
    result = []
    for key, entry in db["keys"].items():
        exp = entry.get("expiry", 0)
        result.append({
            "key":          key,
            "tier":         TIER_NAMES.get(entry.get("tier", 0), "?"),
            "expiry":       datetime.fromtimestamp(exp, timezone.utc).isoformat() if exp else "perpetual",
            "expired":      (exp != 0 and now > exp),
            "revoked":      entry.get("revoked", False),
            "activations":  len(entry.get("activations", {})),
        })
    return jsonify({"keys": result, "total": len(result)})


@app.post("/admin/keys/create")
@_require_admin
def admin_create_key():
    body  = request.get_json(silent=True) or {}
    tier  = int(body.get("tier", 1))
    days  = int(body.get("validity_days", 365))   # 0 = perpetual
    count = int(body.get("count", 1))

    if tier not in TIER_NAMES:
        return jsonify({"error": "Invalid tier."}), 400

    keys = []
    for _ in range(min(count, 100)):   # cap at 100 per request
        key = generate_license_key(tier, days)
        keys.append(key)

    return jsonify({
        "keys":     keys,
        "tier":     TIER_NAMES[tier],
        "expires_in_days": days if days else "perpetual",
    })


@app.post("/admin/keys/revoke")
@_require_admin
def admin_revoke_key():
    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()

    db = _load_db()
    if license_key not in db["keys"]:
        db["keys"][license_key] = {}
    db["keys"][license_key]["revoked"] = True
    db["keys"][license_key]["revoked_at"] = int(time.time())
    _save_db(db)

    return jsonify({"success": True, "message": f"Key {license_key} revoked."})


@app.post("/admin/keys/unrevoke")
@_require_admin
def admin_unrevoke_key():
    body = request.get_json(silent=True) or {}
    license_key = body.get("license_key", "").strip().upper()

    db = _load_db()
    if license_key in db["keys"]:
        db["keys"][license_key]["revoked"] = False
        _save_db(db)

    return jsonify({"success": True, "message": f"Key {license_key} un-revoked."})


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[LicenseServer] Starting on port {PORT}")
    print(f"[LicenseServer] DB: {DB_FILE.resolve()}")
    print(f"[LicenseServer] HMAC secret set: {'YES' if HMAC_SECRET != b'CHANGE_ME_32_BYTES_RANDOM_SECRET!' else 'NO — change it!'}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
