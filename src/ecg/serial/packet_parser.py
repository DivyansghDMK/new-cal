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

# Latch to bridge hardware chatter when RL is disconnected
_rl_chatter_history = []


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

    # Bridge RL chatter: RL loss causes LA and LL to rapidly chatter.
    # If they both drop simultaneously even briefly, hold the RL absent state for 25 packets (50ms).
    global _rl_chatter_history
    if not la_present and not ll_present:
        _rl_chatter_history.append(True)
    else:
        _rl_chatter_history.append(False)
    
    if len(_rl_chatter_history) > 25:
        _rl_chatter_history.pop(0)
        
    rl_absent = any(_rl_chatter_history)

    def is_flat(name: str) -> bool:
        # RA or RL absent -> everything invalid
        if not ra_present or rl_absent:
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

    # ── Derived limb leads ────────────────────────────────────────────────────
    # Flat leads contribute 0 (= ADC 2048) to the math,
    # so derived leads remain valid whenever RA is present (at least one limb
    # lead can carry a real signal).
    #
    # Connectivity rules (match Kotlin Step 5 / Step 7):
    #   III  = II − I      valid if BOTH I and II are connected
    #   aVR  = −(I+II)/2   valid if I OR II connected
    #   aVL  = I − II/2    valid if I connected
    #   aVF  = II − I/2    valid if II connected
    #
    # If RA is absent every lead is flat → ra_present gate covers the
    # "everything invalid" case without extra checks here.

    i_flat  = is_flat("I")
    ii_flat = is_flat("II")

    if not ra_present or rl_absent:
        # Everything is invalid — no derived leads possible
        lead_values["III"] = None
        lead_values["aVR"] = None
        lead_values["aVL"] = None
        lead_values["aVF"] = None
    else:
        # Use raw ADC for flat leads (2048 = 0 mV), real value otherwise.
        # This lets derived leads compute even when one limb is disconnected,
        # with FLAT_LINE_MV = 0.0f.
        i_val  = raw_values["I"]  if not i_flat  else 2048
        ii_val = raw_values["II"] if not ii_flat else 2048

        lead_iii = ii_val - i_val
        avr      = -(i_val + ii_val) / 2
        avl      = i_val - ii_val / 2
        avf      = ii_val - i_val / 2

        # III, aVR, aVL, aVF all show when at least one limb lead is present
        any_limb = not i_flat or not ii_flat
        lead_values["III"] = int(round(lead_iii)) if any_limb else None
        lead_values["aVR"] = int(round(avr))      if any_limb else None
        lead_values["aVL"] = int(round(avl))      if any_limb else None
        lead_values["aVF"] = int(round(avf))      if any_limb else None

    if _DEBUG_PACKETS:
        print("Derived:", {
            "III": lead_values.get("III"),
            "aVR": lead_values.get("aVR"),
            "aVL": lead_values.get("aVL"),
            "aVF": lead_values.get("aVF"),
        })
        print("---------------------\n")

    return lead_values