"""
ArrhythmiaEngine - Priority-based clinical rhythm classifier.

Priority order (highest -> lowest):
  1. Asystole
  2. Ventricular Fibrillation
  3. Ventricular Tachycardia
  4. Atrial Flutter
  5. Second-degree AV Block (Mobitz I - PR progression / RR pattern)
  6. Third-degree AV Block
  7. Atrial Fibrillation
  8. First-degree AV Block (Prolonged PR)
  9. Bundle Branch Block (LBBB / RBBB)
  10. Sinus rhythms (Bradycardia / NSR / Tachycardia)
  11. QT findings

The old dropped-beat -> Mobitz II shortcut has been disabled until it can be
validated against proper P-wave and PR evidence.

Additional secondary findings (BBB, QT, etc.) are appended AFTER the primary
rhythm - never replacing it. The first element of the returned list is always
the primary rhythm.
"""


class ArrhythmiaEngine:
    def __init__(self, features):
        self.f = features

    def is_irregular(self):
        rr = self.f.get("rr_intervals", [])
        if len(rr) < 3:
            return False
        import numpy as np
        rr = np.array(rr)
        return float(np.std(rr)) > 80

    def _rr_variability(self):
        rr = self.f.get("rr_intervals", [])
        if len(rr) < 2:
            return 0
        import numpy as np
        rr = np.array(rr)
        return float(np.std(rr))

    def _is_asystole(self):
        """Signal amplitude below clinical threshold -> no cardiac output."""
        signal_std = self.f.get("signal_std", None)
        if signal_std is not None:
            det_mean = float(self.f.get("signal_amplitude", 0) or 0)
            if det_mean > 100.0 and float(signal_std) < 50.0:
                return True

        amplitude = self.f.get("signal_amplitude", None)
        if amplitude is not None:
            if float(amplitude) < 0.05:
                return True

        hr = self.f.get("hr", 0)
        qrs = self.f.get("qrs", 0)
        return hr < 5 and qrs == 0

    def _is_vf(self):
        vf_score = self.f.get("vf_score", 0)
        if vf_score and float(vf_score) > 0.35:
            return True
        hr = self.f.get("hr", 0)
        qrs = self.f.get("qrs", 0)
        amplitude = self.f.get("signal_amplitude", None)
        has_signal = amplitude is None or float(amplitude) >= 0.05
        return has_signal and (hr == 0 or hr > 150) and not qrs

    def _is_vt(self):
        hr = self.f.get("hr", 0)
        qrs = self.f.get("qrs", 0)
        dominant_ratio = float(self.f.get("dominant_ratio", 0.0) or 0.0)
        return hr > 150 and qrs > 120 and dominant_ratio < 0.7

    def _is_atrial_flutter(self):
        flutter_flag = self.f.get("atrial_flutter", False)
        flutter_score = self.f.get("flutter_score", 0)
        rr_var = float(self._rr_variability() or 0.0)

        p = self.f.get("p_detected", True)

        if p:
            return False
        if rr_var > 80.0:
            return False

        return flutter_flag and float(flutter_score) > 0.18

    def detect(self):
        hr = self.f.get("hr", 0)
        pr = self.f.get("pr", 0)
        qrs = self.f.get("qrs", 0)
        qtc = self.f.get("qtc", 0)
        p = self.f.get("p_detected", True)
        indicator = self.f.get("lbbb_indicator", 0)
        cluster_count = int(self.f.get("cluster_count", 0) or 0)
        ectopic_ratio = float(self.f.get("ectopic_ratio", 0.0) or 0.0)

        if self._is_asystole():
            primary = "Asystole"
        elif self._is_vf():
            primary = "Ventricular Fibrillation"
        elif self._is_vt():
            primary = "Ventricular Tachycardia"
        elif self._is_atrial_flutter():
            primary = "Atrial Flutter"
        elif self.f.get("pr_progression"):
            primary = "Second-degree AV Block (Mobitz I)"
        elif self.f.get("av_dissociation"):
            primary = "Third-degree AV Block"
        elif not p and self.is_irregular():
            primary = "Atrial Fibrillation"
        elif pr > 200 and p:
            primary = "First-degree AV Block (Prolonged PR)"
        elif 60 <= hr <= 100 and p:
            primary = "Normal Sinus Rhythm"
        elif hr > 100 and p:
            primary = "Sinus Tachycardia"
        elif hr < 60 and p:
            primary = "Sinus Bradycardia"
        elif hr < 60:
            primary = "Bradycardia (non-sinus)"
        elif hr > 100:
            primary = "Tachycardia (non-sinus)"
        else:
            primary = "Rhythm Undetermined"

        results = [primary]

        if primary == "Asystole":
            return results

        LETHAL = {"Asystole", "Ventricular Fibrillation", "Ventricular Tachycardia"}

        if qrs >= 110 and primary not in LETHAL:
            if indicator > 0.2:
                results.append("Complete Left Bundle Branch Block")
            elif indicator < -0.2:
                results.append("Complete Right Bundle Branch Block")
            elif qrs >= 120 and "Wide QRS" not in results:
                results.append("Wide QRS (non-specific)")

        if qtc > 500 and "Long QT Syndrome" not in results:
            results.append("Long QT Syndrome")
        elif 460 < qtc <= 500 and "Prolonged QTc" not in results:
            results.append("Prolonged QTc")

        if ectopic_ratio > 0.2 and "Frequent PVCs" not in results:
            results.append("Frequent PVCs")
        if cluster_count > 2 and "Multifocal PVCs" not in results:
            results.append("Multifocal PVCs")

        return results
