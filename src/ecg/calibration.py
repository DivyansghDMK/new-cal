"""The one place that says how many ADC counts a millivolt is.

MEASURED, NOT ASSUMED
---------------------
31 August 2026, unit DM ECG V1.0 A989, on a Fluke ProSim 8. A 1.0 mV, 2 Hz square
wave was injected and the raw serial stream captured with tools/bench_capture.py,
so nothing in the software scaling chain was in the path:

    lead    II    V1    V2    V3    V4    V5    V6
    counts 1420  1424  1422  1427  1424  1422  1422      mean 1423, spread 0.5%

Lead I reads 0.70x on every capture and both waveform types; that is the ProSim's
own lead I : lead II ratio for performance waveforms, not a channel difference.

WHAT THIS REPLACED
------------------
Four different constants were shipping at once, in four files:

    1441   SV1 amplitude                    -1.3%   effectively correct
    1184   waveform drawing, per-lead ST     read 20% HIGH
    1200   QRS slope threshold, ST deviation read 19% HIGH
    2048   RV5 amplitude                     read 31% LOW

The 2048/1441 pair was commented "hardware calibration", so at some point someone
believed V1 and V5 had different gains. The bench says they do not: 1424 and 1422.

An earlier analysis of patient recordings argued for 1184 because only it produced
physiological amplitudes. That reasoning was too strong - at 1423 a lead II R wave
reads 0.83 mV, which is equally physiological. Two candidates cannot be separated
from recordings alone, which is why the pulse was needed.

WHAT IT IS NOT
--------------
This is the gain of the acquisition chain. It says nothing about the chain's
usable range, which the same bench session measured at +/-1.44 mV against the
+/-5 mV IEC 60601-2-25 asks for. See docs/BENCH_RESULTS_2026-08-31.md.
"""

# Counts per millivolt, identical on every acquisition channel.
ADC_PER_MV: float = 1423.0

# Bookkeeping for the report and for anyone re-deriving the number.
CALIBRATION_SOURCE = "Fluke ProSim 8, 1.0 mV square wave, 31 Aug 2026"
CALIBRATION_UNIT = "DM ECG V1.0 A989"

# Full-scale reach of the 12-bit converter from mid-rail, in millivolts. Kept here
# because every amplitude threshold has to be read against it: Sokolow-Lyon calls
# LVH at RV5 + SV1 >= 3.5 mV, and two channels saturating at 1.44 mV cannot sum
# past 2.88 mV, so that threshold is unreachable on this hardware.
ADC_FULL_SCALE_COUNTS: int = 2048
FULL_SCALE_MV: float = ADC_FULL_SCALE_COUNTS / ADC_PER_MV
