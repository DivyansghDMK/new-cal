"""ECG packet parsing utilities"""
import os
import re
from typing import Dict, Tuple, Optional

# ── Packet structure constants ────────────────────────────────────────────────
# Hardware sends: START(1) + COUNTER(1) + FLAGS(2) + LEADS(8×2) + CRC(1) + END(1) = 22 bytes
PACKET_SIZE = 22
START_BYTE = 0xE8
END_BYTE = 0x8E
LEAD_NAMES_DIRECT = ["I", "II", "V1", "V2", "V3", "V4", "V5", "V6"]
PACKET_REGEX = re.compile(r"(?i)(E8(?:[0-9A-F\s]{2,})?8E)")

_DEBUG_PACKETS = os.getenv("ECG_DEBUG_PACKETS", "0").strip().lower() in {"1", "true", "yes", "y", "on"}


def hex_string_to_bytes(hex_str: str) -> bytes:
    """Convert hex string to bytes"""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", hex_str)
    if len(cleaned) % 2 != 0:
        raise ValueError("Hex string must have even length")
    return bytes(int(cleaned[i : i + 2], 16) for i in range(0, len(cleaned), 2))


def decode_lead(msb: int, lsb: int) -> Tuple[int, bool]:
    """Decode lead value from MSB and LSB bytes"""
    lower7 = lsb & 0x7F
    upper5 = msb & 0x1F
    value = (upper5 << 7) | lower7
    connected = (msb & 0x20) != 0
    return value, connected


def parse_packet(raw: bytes) -> Dict[str, Optional[int]]:
    """
    Parse ECG packet and return dictionary of lead values.

    BUG-19 FIX: Returns None for disconnected leads instead of plotting electrode noise.
    BUG-15 FIX: aVL and aVF now use correct Goldberger formulas.

    Returns:
        dict mapping lead name → int (ADC value) or None (lead disconnected)
    """
    if len(raw) != PACKET_SIZE or raw[0] != START_BYTE or raw[-1] != END_BYTE:
        return {}

    # Extract packet counter (byte 1) - sequence number 0-63
    packet_counter = raw[1] & 0x3F  # Counter is in lower 6 bits (0-63)

    lead_values: Dict[str, Optional[int]] = {}
    raw_values: Dict[str, int] = {}
    raw_connected: Dict[str, bool] = {}
    idx = 5  # first MSB position

    if _DEBUG_PACKETS:
        print(f"---- New Packet (Counter: {packet_counter}) ----")

    for name in LEAD_NAMES_DIRECT:
        msb = raw[idx]
        lsb = raw[idx + 1]
        idx += 2

        value, connected = decode_lead(msb, lsb)
        raw_values[name] = value
        raw_connected[name] = connected

        if _DEBUG_PACKETS:
            print(f"{name}: MSB={msb:02X}, LSB={lsb:02X}, value={value}, connected={connected}")

    # ── Electrode presence bits ──────────────────────────────────────────
    # bit = 1 → electrode IS present/connected. LA/RA/LL reuse the same MSB
    # bytes as leads I/II, but LL is a separate bit (0x40) never read above.
    la_present = (raw[5] & 0x20) != 0   # LA — Lead I  MSB bit5
    ra_present = (raw[7] & 0x20) != 0   # RA — Lead II MSB bit5
    ll_present = (raw[7] & 0x40) != 0   # LL — Lead II MSB bit6

    def is_flat(name: str) -> bool:
        # RA absent -> everything invalid
        if not ra_present:
            return True

        # LA absent
        if not la_present and name in (
            "I", "V1", "V2", "V3", "V4", "V5", "V6"
        ):
            return True

        # LL absent
        if not ll_present and name in (
            "II", "V1", "V2", "V3", "V4", "V5", "V6"
        ):
            return True

        # Individual chest lead disconnected
        if name in ("V1", "V2", "V3", "V4", "V5", "V6") and not raw_connected[name]:
            return True

        return False

    # BUG-19 FIX: respect the full RA/LA/LL cascade, not just each lead's own bit.
    # When a lead is flat, return None so display shows "LEAD OFF" instead of
    # plotting garbage ADC noise as an ECG waveform.
    for name in LEAD_NAMES_DIRECT:
        lead_values[name] = None if is_flat(name) else raw_values[name]

    # Derived limb leads — only calculate when source leads are connected
    lead_i  = lead_values.get("I")
    lead_ii = lead_values.get("II")

    if lead_i is not None and lead_ii is not None:
        # ── BUG-15 FIX: Correct Goldberger/Einthoven formulas ────────────────
        # OLD (wrong): aVL = (I - III) / 2,  aVF = (II + III) / 2
        # NEW (correct Goldberger):
        lead_iii = lead_ii - lead_i                    # Einthoven's law ✅
        avr      = -(lead_i + lead_ii) / 2             # Goldberger ✅
        avl      = lead_i  - lead_ii / 2               # Goldberger ✅ (was wrong)
        avf      = lead_ii - lead_i  / 2               # Goldberger ✅ (was wrong)

        lead_values["III"] = int(round(lead_iii))
        lead_values["aVR"] = int(round(avr))
        lead_values["aVL"] = int(round(avl))
        lead_values["aVF"] = int(round(avf))
    else:
        # If source limb leads are disconnected, derived leads are also invalid
        lead_values["III"] = None
        lead_values["aVR"] = None
        lead_values["aVL"] = None
        lead_values["aVF"] = None

    if _DEBUG_PACKETS:
        print("Derived:", {
            "III": lead_values.get("III"),
            "aVR": lead_values.get("aVR"),
            "aVL": lead_values.get("aVL"),
            "aVF": lead_values.get("aVF"),
        })
        print("---------------------\n")

    return lead_values