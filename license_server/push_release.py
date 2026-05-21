#!/usr/bin/env python3
"""
license_server/push_release.py
================================
Admin CLI — publish a new ECG Monitor release to the license server.

Run this AFTER you have:
  1. Verified the new build works correctly.
  2. Created the GitHub Release (CI does this automatically on push to main).

Usage
-----
  python push_release.py \\
    --version 2026.05.21.1003 \\
    --notes "New arrhythmia rules, HRV improvements" \\
    --url "https://github.com/DivyansghDMK/qww_new/releases/download/stable-2026.05.21.1003/ECGMonitorSetup.exe"

Optional flags
--------------
  --channel   stable (default) | beta
  --server    Override LICENSE_SERVER_URL from .env
  --token     Override ADMIN_TOKEN from .env

Environment variables (read from .env automatically)
----------------------------------------------------
  LICENSE_SERVER_URL   URL of the running license server
  ADMIN_TOKEN          Bearer token for /admin/* endpoints

What this does
--------------
  Calls POST /admin/release/publish on the license server.
  The server stores the version info in release_manifest.json.
  Every licensed user who opens the app will then see:
    "🔔 Update available — v2026.05.21.1003  [Download]  [Dismiss]"
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    from pathlib import Path

    # Load license_server/.env first (has ADMIN_TOKEN, HMAC_SECRET, etc.)
    _script_dir = Path(__file__).parent.resolve()
    _local_env  = _script_dir / ".env"
    if _local_env.exists():
        load_dotenv(_local_env, override=False)

    # Then load the project root .env (has LICENSE_SERVER_URL, AWS keys, etc.)
    _root_env = _script_dir.parent / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=False)

except ImportError:
    pass  # dotenv not installed — values must be set in the environment


def _push(server_url: str, admin_token: str, payload: dict) -> dict:
    """POST to /admin/release/publish and return the parsed JSON response."""
    url = f"{server_url.rstrip('/')}/admin/release/publish"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type":  "application/json",
            "X-Admin-Token": admin_token,          # ← changed from Authorization: Bearer
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        return {"error": f"HTTP {e.code}: {e.reason}", "body": body}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish a new ECG Monitor release to the license server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--version", "-v",
        required=True,
        help="Version string, e.g. 2026.05.21.1003  (must match the GitHub Release tag)",
    )
    parser.add_argument(
        "--notes", "-n",
        default="",
        metavar="TEXT",
        help="Short release notes shown to the user in the update banner.",
    )
    parser.add_argument(
        "--url", "-u",
        default="",
        metavar="URL",
        help="Direct download URL for the installer (.exe).",
    )
    parser.add_argument(
        "--channel", "-c",
        default="stable",
        choices=["stable", "beta"],
        help="Update channel (default: stable).",
    )
    parser.add_argument(
        "--force", "--rollback",
        action="store_true",
        dest="force",
        help=(
            "Force-notify all users even if the published version is OLDER than "
            "their installed version (rollback mode). Use when the current release "
            "has a critical bug and users must downgrade."
        ),
    )
    parser.add_argument(
        "--server",
        default="",
        metavar="URL",
        help="License server URL (overrides LICENSE_SERVER_URL env var).",
    )
    parser.add_argument(
        "--token",
        default="",
        metavar="TOKEN",
        help="Admin token (overrides ADMIN_TOKEN env var).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload without actually calling the server.",
    )

    args = parser.parse_args()

    # ── Resolve configuration ─────────────────────────────────────────────────
    raw_url = (args.server or os.getenv("LICENSE_SERVER_URL", "")).strip()

    # The root .env stores the API v1 base URL (…/prod/api/v1).
    # Our admin endpoints live at the server root (…/prod), not under /api/v1.
    # Strip the trailing /api/v1 (or /api/v1/) so the path is correct.
    import re as _re
    server_url = _re.sub(r"/api/v\d+/?$", "", raw_url).rstrip("/")

    # Accept either ADMIN_TOKEN (license_server/.env) or LICENSE_API_TOKEN (root .env)
    admin_token = (
        args.token
        or os.getenv("ADMIN_TOKEN", "").strip()
        or os.getenv("LICENSE_API_TOKEN", "").strip()
    )

    if not server_url:
        print(
            "\n  [ERROR] LICENSE_SERVER_URL is not set.\n"
            "          Set it in license_server/.env or the project root .env, or pass --server <url>\n"
        )
        sys.exit(1)

    if not admin_token:
        print(
            "\n  [ERROR] ADMIN_TOKEN is not set.\n"
            "          Set ADMIN_TOKEN in license_server/.env or LICENSE_API_TOKEN in root .env,\n"
            "          or pass --token <token>\n"
        )
        sys.exit(1)

    payload = {
        "version":       args.version,
        "channel":       args.channel,
        "release_notes": args.notes,
        "download_url":  args.url,
        "force_notify":  args.force,
        "admin_token":   admin_token,   # ← add karo
    }

    # ── Summary ──────────────────────────────────────────────────────────────
    action_label = "ROLLBACK" if args.force else "Publish Release"
    print()
    print(f"  +--------------------------------------------------+")
    print(f"  |   ECG Monitor  --  {action_label:<30}|")
    print(f"  +--------------------------------------------------+")
    print(f"  Server  : {server_url}")
    print(f"  Version : {args.version}  [{args.channel}]")
    if args.force:
        print(f"  Mode    : !! ROLLBACK -- users will be forced to reinstall")
    if args.notes:
        print(f"  Notes   : {args.notes[:80]}{'...' if len(args.notes) > 80 else ''}")
    if args.url:
        print(f"  DL URL  : {args.url[:80]}{'...' if len(args.url) > 80 else ''}")
    print()

    if args.dry_run:
        print("  [DRY RUN] Would POST the following payload:")
        print(f"  {json.dumps(payload, indent=4)}")
        print()
        sys.exit(0)

    # ── Confirm ───────────────────────────────────────────────────────────────
    if args.force:
        confirm_msg = (
            "  !! ROLLBACK MODE: All users will see a red 'Action Required' banner.\n"
            "  Are you sure you want to roll back all users to this version? [y/N] "
        )
    else:
        confirm_msg = "  Are you sure you want to publish this update to all users? [y/N] "

    try:
        confirm = input(confirm_msg).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Aborted.\n")
        sys.exit(0)

    if confirm not in ("y", "yes"):
        print("\n  Aborted.\n")
        sys.exit(0)

    # ── Send ──────────────────────────────────────────────────────────────────
    print(f"\n  Sending to {server_url}/admin/release/publish ...")
    result = _push(server_url, admin_token, payload)

    if result.get("success"):
        data = result.get("data", {})
        published_at = data.get("published_at", datetime.now(timezone.utc).isoformat())
        print(f"\n  [SUCCESS] Release published successfully!")
        print(f"            Version    : {data.get('version', args.version)}")
        print(f"            Channel    : {data.get('channel', args.channel)}")
        print(f"            Published  : {published_at}")
        print()
        print("  Users will see the update banner next time they open the app.\n")
    else:
        error = result.get("error", "Unknown error")
        body  = result.get("body", "")
        print(f"\n  [ERROR] Failed: {error}")
        if body:
            print(f"          Server response: {body[:200]}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
