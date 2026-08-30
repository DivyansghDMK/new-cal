import json
import os
import re
from utils.app_paths import data_file

class SettingsManager:
    def __init__(self):
        # Use data_file to resolve writable paths in the runtime workspace for frozen builds
        self.settings_file = str(data_file("ecg_settings.json"))
        self.legacy_settings_file = os.path.abspath("ecg_settings.json")
        self.default_settings = {
            "wave_speed": "25",  # mm/s (default)
            "wave_gain": "10",   # mm/mV
            "lead_sequence": "Standard",
            "serial_port": "Select Port",
            "baud_rate": "115200",
            "hardware_version": "",
            "machine_serial_number": "",

            # Report Setup settings
            "report_format": "12_1",
            "lead_sequence": "Standard",

            # Filter settings
            "filter_ac": "50",
            # Default EMG cutoff for all modes (user can change in settings).
            #
            # 150 Hz is the diagnostic bandwidth IEC 60601-2-25 asks for, and it
            # measures -1.18 dB at 150 Hz through this chain, inside the -3 dB
            # limit. The previous default of 25 Hz put every out-of-box capture at
            # a monitoring bandwidth: measured on real 12-lead recordings it cost
            # 20-29% of the QRS peak-to-peak in the chest leads and moved the J
            # point by up to 1.1 mm. Carts ship 150 Hz as the diagnostic default
            # and label 25/35/40 as an explicit operator choice; so do we now.
            "filter_emg": "150",
            # Default baseline HP (DFT) cutoff for all modes (user can change in settings).
            # 0.05 Hz is the IEC 60601-2-25 lower diagnostic limit and passes the
            # standard's impulse-response test (0.027 mV displacement, 0.000 mV/s
            # slope against 0.1 mV / 0.30 mV/s limits). "off" left every capture
            # with no baseline correction at all.
            "filter_dft": "0.05",

            # System Setup settings
            "system_beat_vol": "off",
            "system_language": "en",

            # Factory Maintain settings
            "factory_calibration": "skip",
            "factory_self_test": "skip",
            "factory_memory_reset": "keep",
            "factory_reset": "cancel"
        }
        self.settings = self.load_settings()

    def _normalize_filter_value(self, key, value):
        """
        Normalize persisted filter settings so all consumers receive canonical values.
        Handles legacy/free-form values like "50 hz", "50Hz", etc.
        """
        if value is None:
            return value

        text = str(value).strip().lower()
        if key == "filter_ac":
            if text in ("off", "", "none", "0"):
                return "off"
            match = re.search(r"(\d+(?:\.\d+)?)", text)
            if match:
                hz = match.group(1)
                if hz in ("50", "50.0"):
                    return "50"
                if hz in ("60", "60.0"):
                    return "60"
            return "off"

        if key == "filter_emg":
            if text in ("off", "", "none", "0"):
                return "off"
            match = re.search(r"(\d+(?:\.\d+)?)", text)
            if match:
                try:
                    hz_value = float(match.group(1))
                except ValueError:
                    hz_value = None

                if hz_value is not None:
                    if abs(hz_value - round(hz_value)) < 1e-6:
                        hz = str(int(round(hz_value)))
                    else:
                        hz = format(hz_value, "g")
                else:
                    hz = match.group(1).strip()

                if hz in {"25", "35", "40", "75", "100", "150"}:
                    return hz
            return self.default_settings.get("filter_emg", "150") if hasattr(self, "default_settings") else "150"

        if key == "filter_dft":
            if text in ("off", "", "none", "0"):
                return "off"
            match = re.search(r"(\d+(?:\.\d+)?)", text)
            if match:
                val = float(match.group(1))
                if abs(val - 0.05) < 1e-6:
                    return "0.05"
                if abs(val - 0.5) < 1e-6:
                    return "0.5"
            return self.default_settings.get("filter_dft", "0.05") if hasattr(self, "default_settings") else "0.05"

        return value
    
    def load_settings(self):
        source_file = None
        if os.path.exists(self.settings_file):
            source_file = self.settings_file
        elif os.path.exists(self.legacy_settings_file):
            # Backward compatibility: migrate older cwd-relative config files.
            source_file = self.legacy_settings_file

        if source_file:
            try:
                with open(source_file, 'r') as f:
                    loaded_settings = json.load(f)

                merged_settings = self.default_settings.copy()
                merged_settings.update(loaded_settings)

                # If we loaded from an old path, persist the canonical copy so
                # all future runs use the same configuration file.
                if source_file != self.settings_file:
                    try:
                        with open(self.settings_file, 'w') as out_f:
                            json.dump(merged_settings, out_f, indent=2)
                    except Exception:
                        pass

                merged_settings = self._migrate_settings(merged_settings)
                return merged_settings
            except:
                return self.default_settings.copy()
        return self.default_settings.copy()

    # Bump this when a migration is added below.
    SETTINGS_VERSION = 1

    def _migrate_settings(self, settings):
        """One-time upgrades to a stored configuration.

        Changing default_settings only reaches FRESH installs: load_settings()
        merges the saved file over the defaults, so an existing unit keeps whatever
        cutoff it already had. When the diagnostic default moved from 25 Hz to
        150 Hz that left every field unit recording at a monitoring bandwidth,
        silently.

        This runs once per version bump, is written back to disk, and prints what it
        changed so the change is traceable. It only moves a cutoff that is BELOW the
        diagnostic bandwidth; a unit already at 150 Hz, or deliberately set to a
        monitoring bandwidth AFTER this migration ran, is left alone — and the
        report now prints NON-DIAGNOSTIC for those, so the choice is visible rather
        than silent.
        """
        try:
            if int(settings.get("settings_version", 0) or 0) >= self.SETTINGS_VERSION:
                return settings
            changed = []
            emg = str(settings.get("filter_emg", "")).strip().lower()
            if emg not in ("", "off", "150"):
                try:
                    if float(emg) < 150.0:
                        settings["filter_emg"] = "150"
                        changed.append(f"filter_emg {emg} -> 150")
                except ValueError:
                    pass
            settings["settings_version"] = self.SETTINGS_VERSION
            try:
                with open(self.settings_file, 'w') as f:
                    json.dump(settings, f, indent=2)
            except Exception:
                pass
            if changed:
                print(f"[SettingsManager] migrated to v{self.SETTINGS_VERSION}: "
                      + "; ".join(changed))
        except Exception as e:
            print(f"[SettingsManager] migration skipped: {e}")
        return settings
    
    def save_settings(self):
        with open(self.settings_file, 'w') as f:
            json.dump(self.settings, f, indent=2)
    
    def get_setting(self, key, default=None):
        value = self.settings.get(key, self.default_settings.get(key, default))
        if key in {"filter_ac", "filter_emg", "filter_dft"}:
            return self._normalize_filter_value(key, value)
        return value
    
    def set_setting(self, key, value):
        if key in {"filter_ac", "filter_emg", "filter_dft"}:
            value = self._normalize_filter_value(key, value)
        self.settings[key] = value
        self.save_settings()
        print(f"Setting updated: {key} = {value}")  # Terminal verification

    def reset_to_defaults(self):
        """Restore every persisted setting to its original factory default, preserving hardware and serial info."""
        current_hw_version = self.settings.get("hardware_version", "")
        current_sn = self.settings.get("machine_serial_number", "")
        self.settings = self.default_settings.copy()
        self.settings["hardware_version"] = current_hw_version
        self.settings["machine_serial_number"] = current_sn
        self.save_settings()
        return self.settings.copy()
    
    def get_wave_speed(self):
        return float(self.get_setting("wave_speed"))
    
    def get_wave_gain(self):
        return float(self.get_setting("wave_gain"))

    def get_serial_port(self):
        return self.get_setting("serial_port")
    
    def get_baud_rate(self):
        return self.get_setting("baud_rate")
    
    def set_serial_port(self, port):
        self.set_setting("serial_port", port)
    
    def set_baud_rate(self, baud_rate):
        self.set_setting("baud_rate", baud_rate)

    def get_calibration_notch_boxes(self):
        """Calculate calibration notch boxes based on wave gain"""
        wave_gain = self.get_wave_gain()
        if wave_gain == 20:
            return 4.0
        elif wave_gain == 10:
            return 2.0
        elif wave_gain == 5:
            return 1.0
        elif wave_gain == 2.5:
            return 0.5
        else:
            # Default calculation for other values
            return wave_gain / 5.0  # 5mm = 1 box baseline
