"""
Automatic Background Cloud Sync Service
Runs every 15 seconds to upload any new/modified files to cloud.
All uploads are tagged with the machine serial number (RhythmUltra device ID)
so every file on S3 is traceable back to the specific device.
"""

import os
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Set, Dict, List, Optional

from utils.app_paths import data_file


def _read_machine_serial() -> str:
    """
    Read machine_serial_number from ecg_settings.json.
    Falls back to hardware_version if serial is blank.
    Returns empty string if not found.
    """
    try:
        settings_paths = [
            Path(__file__).parent.parent.parent / "ecg_settings.json",
            data_file("ecg_settings.json"),
        ]
        for p in settings_paths:
            try:
                p = Path(p)
            except Exception:
                continue
            if p.exists():
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    cfg = json.load(f)
                sn = str(cfg.get("machine_serial_number") or "").strip()
                if sn:
                    return sn
                hw = str(cfg.get("hardware_version") or "").strip()
                if hw:
                    return hw
    except Exception:
        pass
    return ""


def _infer_report_type(filename: str) -> str:
    """Infer report_type from filename for S3 metadata and key prefixing."""
    name = filename.lower()
    if "hrv" in name:
        return "hrv"
    if "hyper" in name or "hyperkalemia" in name:
        return "hyperkalemia"
    if "ecg" in name or "report" in name or "12_lead" in name or "twelve" in name:
        return "12_lead_ecg"
    return "ecg_report"


class AutoSyncService:
    """Background service that automatically syncs files to cloud every 15 seconds.
    Every upload is tagged with the machine serial number so all S3 objects
    are linked to the RhythmUltra device that generated them."""

    def __init__(self, interval_seconds=15):
        self.interval = interval_seconds
        self.running = False
        self.thread = None
        self.cloud_uploader = None
        self.synced_files: Set[str] = set()
        self.last_sync_time = datetime.now()

        # Directories to monitor
        self.project_root = Path(__file__).parent.parent.parent
        self.reports_dir = self.project_root / "reports"
        self.users_file = data_file("users.json")

        # Track last modified times
        self.file_timestamps: Dict[str, float] = {}

        print(f"[INFO] Auto-sync service initialized (interval: {interval_seconds}s)")

    # ──────────────────────────────────────────────────────────────────────────
    # Cloud uploader init
    # ──────────────────────────────────────────────────────────────────────────

    def _init_cloud_uploader(self):
        """Initialize cloud uploader lazily"""
        if self.cloud_uploader is None:
            try:
                from utils.cloud_uploader import get_cloud_uploader
                self.cloud_uploader = get_cloud_uploader()
                return self.cloud_uploader.is_configured()
            except Exception as e:
                print(f"[WARN] Auto-sync: Cloud uploader not available: {e}")
                return False
        return self.cloud_uploader.is_configured()

    # ──────────────────────────────────────────────────────────────────────────
    # File scanning
    # ──────────────────────────────────────────────────────────────────────────

    def _get_modified_files(self) -> List[Path]:
        """Get list of files that have been modified since last sync"""
        modified_files = []

        try:
            if self.reports_dir.exists():
                # All PDFs recursively (covers HRV, Hyperkalemia, 12-lead)
                for file_path in self.reports_dir.rglob("*.pdf"):
                    if self._is_file_modified(file_path):
                        modified_files.append(file_path)

                # All JSONs recursively in reports/ (covers report data files)
                for file_path in self.reports_dir.rglob("*.json"):
                    # Skip the upload log itself
                    if "upload_log" in file_path.name.lower():
                        continue
                    if self._is_file_modified(file_path):
                        modified_files.append(file_path)

            # Check for new user signups
            try:
                users_file = Path(self.users_file)
            except Exception:
                users_file = None
            if users_file and users_file.exists() and self._is_file_modified(users_file):
                modified_files.append(users_file)

        except Exception as e:
            print(f"[WARN] Auto-sync: Error scanning files: {e}")

        return modified_files

    def _is_file_modified(self, file_path: Path) -> bool:
        """Check if file has been modified since last sync"""
        try:
            current_mtime = file_path.stat().st_mtime
            file_str = str(file_path)

            if file_str not in self.file_timestamps:
                self.file_timestamps[file_str] = current_mtime
                return True

            if current_mtime > self.file_timestamps[file_str]:
                self.file_timestamps[file_str] = current_mtime
                return True

            return False
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Upload helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _build_metadata(self, file_path: Path) -> dict:
        """
        Build upload metadata for a report file.
        Always includes machine_serial so every S3 object is device-linked.
        """
        machine_serial = _read_machine_serial()
        report_type = _infer_report_type(file_path.name)
        meta = {
            "filename": file_path.name,
            "report_type": report_type,
            "uploaded_at": datetime.now().isoformat(),
            "file_size": str(file_path.stat().st_size) if file_path.exists() else "0",
            "file_type": file_path.suffix.lstrip("."),
        }
        if machine_serial:
            meta["machine_serial"] = machine_serial
            meta["device_id"] = machine_serial        # alias for easy querying
        return meta

    def _upload_one(self, file_path: Path) -> str:
        """Upload a single file with machine-serial metadata. Returns status string."""
        if not self.cloud_uploader:
            return "no_uploader"
        try:
            metadata = self._build_metadata(file_path)
            result = self.cloud_uploader.upload_report(str(file_path), metadata=metadata)
            return result.get("status", "error")
        except Exception as e:
            print(f"[ERR] Auto-sync: Exception uploading {file_path.name}: {e}")
            return "error"

    def _upload_report_files(self, file_path: Path) -> bool:
        """Upload a report file (PDF or JSON) with full machine-serial metadata."""
        try:
            if not self.cloud_uploader:
                return False

            status = self._upload_one(file_path)

            if status == "success":
                print(f"[INFO] Auto-sync: Uploaded {file_path.name} "
                      f"[{_infer_report_type(file_path.name)}]")

                # If this was a PDF, also upload its JSON twin (if not already queued)
                if file_path.suffix.lower() == ".pdf":
                    json_twin = file_path.with_suffix(".json")
                    if json_twin.exists() and str(json_twin) not in [str(f) for f in []]:
                        twin_status = self._upload_one(json_twin)
                        if twin_status == "success":
                            print(f"[INFO] Auto-sync: Uploaded JSON twin {json_twin.name}")

                return True

            elif status == "already_uploaded":
                print(f"[INFO] Auto-sync: Skipped duplicate {file_path.name}")
                return True

            elif status == "skipped":
                # upload_report() decided the file isn't a report — force-upload with metadata
                # This handles edge cases where filename doesn't match the keyword filter
                try:
                    metadata = self._build_metadata(file_path)
                    machine_serial = _read_machine_serial()
                    report_type = _infer_report_type(file_path.name)
                    result = self.cloud_uploader._upload_to_s3(str(file_path), metadata) \
                        if hasattr(self.cloud_uploader, "_upload_to_s3") else {"status": "error"}
                    if result.get("status") == "success":
                        self.cloud_uploader._log_upload(str(file_path), result, metadata)
                        print(f"[INFO] Auto-sync: Force-uploaded {file_path.name} [{report_type}]")
                        return True
                except Exception as fe:
                    print(f"[WARN] Auto-sync: Force-upload failed for {file_path.name}: {fe}")
                return False

            else:
                print(f"[WARN] Auto-sync: Upload failed for {file_path.name}: status={status}")
                return False

        except Exception as e:
            print(f"[ERR] Auto-sync: Error uploading {file_path.name}: {e}")
            return False

    def _upload_user_signups(self) -> bool:
        """Upload any new user signups to cloud, tagged with machine serial."""
        try:
            users_file = Path(self.users_file)
            if not users_file.exists():
                return False

            with open(users_file, "r", encoding="utf-8", errors="replace") as f:
                users_data = json.load(f)

            machine_serial = _read_machine_serial()
            upload_count = 0

            for username, user_info in users_data.items():
                if not isinstance(user_info, dict):
                    continue

                serial_id = user_info.get("serial_id", username)
                phone = user_info.get("phone", "")

                user_key = f"{username}_{serial_id}"
                if user_key in self.synced_files:
                    continue

                user_data = {
                    "username": username,
                    "full_name": user_info.get("full_name", ""),
                    "phone": phone,
                    "serial_id": serial_id,
                    "email": user_info.get("email", ""),
                    "age": user_info.get("age", ""),
                    "gender": user_info.get("gender", ""),
                    "registration_date": user_info.get(
                        "registration_date",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                    "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                # Always attach machine serial to user signup
                if machine_serial:
                    user_data["machine_serial"] = machine_serial
                    user_data["device_id"] = machine_serial

                result = self.cloud_uploader.upload_user_signup(user_data)
                status = result.get("status")

                if status == "success":
                    print(f"[INFO] Auto-sync: Uploaded user signup: {username} "
                          f"[device: {machine_serial or 'unknown'}]")
                    self.synced_files.add(user_key)
                    upload_count += 1
                elif status == "already_uploaded":
                    print(f"[INFO] Auto-sync: Skipped duplicate user signup: {username}")
                    self.synced_files.add(user_key)
                else:
                    print(f"[WARN] Auto-sync: Failed to upload user {username}: "
                          f"{result.get('message', 'Unknown error')}")

            return upload_count > 0

        except Exception as e:
            print(f"[ERR] Auto-sync: Error uploading user signups: {e}")
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Sync cycle
    # ──────────────────────────────────────────────────────────────────────────

    def _sync_cycle(self):
        """Single sync cycle — upload any new/modified files"""
        try:
            if not self._init_cloud_uploader():
                if (datetime.now() - self.last_sync_time).seconds >= 60:
                    print("[INFO] Auto-sync: Cloud not configured (skipping sync)")
                    self.last_sync_time = datetime.now()
                return

            modified_files = self._get_modified_files()
            if not modified_files:
                return

            machine_serial = _read_machine_serial()
            print(f"\n[INFO] Auto-sync: Found {len(modified_files)} file(s) to sync "
                  f"[device: {machine_serial or 'unknown'}]")

            try:
                users_file_path = Path(self.users_file)
            except Exception:
                users_file_path = None

            for file_path in modified_files:
                if users_file_path and file_path == users_file_path:
                    self._upload_user_signups()
                else:
                    self._upload_report_files(file_path)

            self.last_sync_time = datetime.now()
            print(f"[INFO] Auto-sync: Cycle complete at "
                  f"{self.last_sync_time.strftime('%H:%M:%S')}\n")

        except Exception as e:
            print(f"[ERR] Auto-sync: Error in sync cycle: {e}")

    def _sync_loop(self):
        """Background loop that runs sync every N seconds"""
        print(f"[START] Auto-sync: Background service started (syncing every {self.interval}s)")
        while self.running:
            try:
                self._sync_cycle()
                time.sleep(self.interval)
            except Exception as e:
                print(f"[ERR] Auto-sync: Loop error: {e}")
                time.sleep(self.interval)
        print("[STOP] Auto-sync: Background service stopped")

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self):
        """Start the background sync service"""
        if self.running:
            print("[WARN] Auto-sync: Service already running")
            return
        self.running = True
        self.thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.thread.start()

        machine_serial = _read_machine_serial()
        print("=" * 70)
        print("=== AUTOMATIC CLOUD SYNC ENABLED! ===")
        print("=" * 70)
        print(f"📤 Syncing every {self.interval} seconds")
        print(f"🔑 Device ID (machine serial): {machine_serial or '(not yet detected)'}")
        print("📁 Monitoring:")
        print(f"   • Reports: {self.reports_dir}")
        print(f"   • Users: {self.users_file}")
        print("=" * 70)
        print()

    def stop(self):
        """Stop the background sync service"""
        if not self.running:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        print("[STOP] Auto-sync: Service stopped")

    def get_status(self) -> Dict:
        """Get current sync service status"""
        return {
            "running": self.running,
            "interval_seconds": self.interval,
            "last_sync": self.last_sync_time.strftime("%Y-%m-%d %H:%M:%S"),
            "synced_files_count": len(self.synced_files),
            "machine_serial": _read_machine_serial(),
            "cloud_configured": self._init_cloud_uploader() if self.running else False,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Global singleton
# ──────────────────────────────────────────────────────────────────────────────

_auto_sync_service = None


def get_auto_sync_service(interval_seconds=15) -> AutoSyncService:
    """Get or create global auto-sync service instance"""
    global _auto_sync_service
    if _auto_sync_service is None:
        _auto_sync_service = AutoSyncService(interval_seconds=interval_seconds)
    return _auto_sync_service


def start_auto_sync(interval_seconds=15):
    """Start automatic background sync service"""
    service = get_auto_sync_service(interval_seconds)
    service.start()
    return service


def stop_auto_sync():
    """Stop the automatic background sync service"""
    global _auto_sync_service
    if _auto_sync_service:
        _auto_sync_service.stop()


if __name__ == "__main__":
    print("Testing Auto-Sync Service...")
    service = start_auto_sync(interval_seconds=5)
    try:
        time.sleep(30)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop_auto_sync()
