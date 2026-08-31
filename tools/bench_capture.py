#!/usr/bin/env python3
"""Bench capture — RAW ADC counts straight off the wire, for calibration work.

WHY THIS EXISTS
---------------
Every other path in this codebase scales the samples by one of four different
ADC-per-mV constants (1184, 1200, 2048, 1441) before you can see them, so none of
them can be used to find out which constant is right. This tool decodes the 22-byte
packet itself and prints the counts, unscaled and unfiltered.

WHAT THE WIRE ACTUALLY CARRIES
------------------------------
    START(0xE8) COUNTER FLAGS(2) 8x[MSB LSB] CRC END(0x8E)      = 22 bytes

    value     = (MSB & 0x1F) << 7 | (LSB & 0x7F)     -> 12 bits, 0..4095
    connected = (MSB & 0x20) != 0                    -> per-lead electrode flag

Eight channels: I, II, V1, V2, V3, V4, V5, V6. III, aVR, aVL and aVF do not exist
on the wire; they are computed in software.

USAGE
-----
    python tools/bench_capture.py --list
    python tools/bench_capture.py --port /dev/tty.usbserial-XXXX --seconds 10 \
                                  --out bench/cal_1mV.csv --label "ProSim 1.0 mV"

    # measure a repeating square/pulse amplitude in counts, per channel
    python tools/bench_capture.py --port ... --seconds 10 --pulse

    # measure steady amplitude of a sine, for a bandwidth sweep
    python tools/bench_capture.py --port ... --seconds 6 --rms --label "10 Hz"

Every mode prints headroom to the 0 and 4095 rails, because a clipped channel
invalidates the measurement and looks like a small one.
"""
import argparse
import csv
import os
import sys
import time

import numpy as np

PACKET_SIZE = 22
START_BYTE = 0xE8
END_BYTE = 0x8E
LEADS = ["I", "II", "V1", "V2", "V3", "V4", "V5", "V6"]
ADC_MAX = 4095


def decode(msb: int, lsb: int):
    """One channel out of two wire bytes: 12-bit value plus the electrode flag."""
    return ((msb & 0x1F) << 7) | (lsb & 0x7F), bool(msb & 0x20)


def read_packets(port: str, baud: int, seconds: float):
    """Yield (values, connected) per packet for `seconds`, resynchronising on START."""
    import serial
    ser = serial.Serial(port, baud, timeout=0.2)
    buf = bytearray()
    t0 = time.monotonic()
    n_bad = 0
    try:
        while time.monotonic() - t0 < seconds:
            chunk = ser.read(512)
            if chunk:
                buf.extend(chunk)
            while len(buf) >= PACKET_SIZE:
                if buf[0] != START_BYTE:
                    del buf[0]
                    n_bad += 1
                    continue
                pkt = bytes(buf[:PACKET_SIZE])
                if pkt[-1] != END_BYTE:
                    del buf[0]
                    n_bad += 1
                    continue
                del buf[:PACKET_SIZE]
                vals, conn = [], []
                i = 5
                for _ in LEADS:
                    v, c = decode(pkt[i], pkt[i + 1])
                    vals.append(v)
                    conn.append(c)
                    i += 2
                yield vals, conn
    finally:
        ser.close()
        if n_bad:
            print(f"  (resynchronised past {n_bad} stray bytes)", file=sys.stderr)


def summarise(a: np.ndarray, conn: np.ndarray, label: str, mode: str):
    """a: samples x 8 raw counts."""
    print(f"\n{'='*74}\n{label}   {a.shape[0]} samples, {a.shape[0]/500.0:.1f} s at 500 Hz\n{'='*74}")
    if mode == "pulse":
        hdr = f"{'lead':>5} {'baseline':>9} {'step':>8} {'p-p':>8} {'min':>6} {'max':>6} {'headroom':>9} {'elec':>5}"
    elif mode == "rms":
        hdr = f"{'lead':>5} {'baseline':>9} {'rms':>8} {'p-p':>8} {'min':>6} {'max':>6} {'headroom':>9} {'elec':>5}"
    else:
        hdr = f"{'lead':>5} {'baseline':>9} {'p-p':>8} {'sd':>8} {'min':>6} {'max':>6} {'headroom':>9} {'elec':>5}"
    print(hdr)
    clipped = []
    for i, name in enumerate(LEADS):
        s = a[:, i].astype(float)
        base = float(np.median(s))
        lo, hi = float(s.min()), float(s.max())
        head = min(lo, ADC_MAX - hi)
        pp = hi - lo
        elec = "on" if conn[:, i].mean() > 0.5 else "OFF"
        if mode == "pulse":
            # A square wave spends its time at two levels: the gap between the
            # 10th and 90th percentile is the step, and is immune to the edges.
            step = float(np.percentile(s, 90) - np.percentile(s, 10))
            mid = f"{step:>8.0f} {pp:>8.0f}"
        elif mode == "rms":
            mid = f"{float(np.std(s)):>8.1f} {pp:>8.0f}"
        else:
            mid = f"{pp:>8.0f} {float(np.std(s)):>8.1f}"
        flag = "  <-- CLIPPED" if head <= 2 else ""
        print(f"{name:>5} {base:>9.0f} {mid} {lo:>6.0f} {hi:>6.0f} {head:>9.0f} {elec:>5}{flag}")
        if head <= 2:
            clipped.append(name)
    if clipped:
        print(f"\n  !! {', '.join(clipped)} reached an ADC rail — reduce amplitude and repeat.")
        print("     A clipped channel reads SMALLER than it should, not larger.")
    print("\n  12-bit converter: 0..4095, so full swing from mid-rail is about +/-2048 counts.")
    if mode == "pulse":
        print("  For a 1 mV input, 'step' IS the counts-per-mV for that channel.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list serial ports and exit")
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--out", help="write raw counts to this CSV")
    ap.add_argument("--label", default="capture")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pulse", action="store_true", help="square/pulse amplitude per channel")
    g.add_argument("--rms", action="store_true", help="RMS amplitude per channel (sine sweep)")
    a = ap.parse_args()

    if a.list:
        from serial.tools import list_ports
        found = list(list_ports.comports())
        if not found:
            sys.exit("no serial ports found — check the cable and that the unit is powered")
        for p in found:
            print(f"  {p.device:<28} {p.description}")
        return

    if not a.port:
        sys.exit("--port is required (run --list to find it)")

    print(f"capturing {a.seconds:.0f}s from {a.port} at {a.baud} …")
    vals, conns = [], []
    for v, c in read_packets(a.port, a.baud, a.seconds):
        vals.append(v)
        conns.append(c)
    if not vals:
        sys.exit("no packets decoded — wrong port, wrong baud, or the unit is not streaming")

    arr = np.array(vals, dtype=int)
    con = np.array(conns, dtype=bool)
    mode = "pulse" if a.pulse else "rms" if a.rms else "plain"
    summarise(arr, con, a.label, mode)

    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        with open(a.out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sample"] + LEADS + [n + "_connected" for n in LEADS])
            for i, (v, c) in enumerate(zip(vals, conns)):
                w.writerow([i] + list(v) + [int(x) for x in c])
        print(f"\n  raw counts written to {a.out}")


if __name__ == "__main__":
    main()
