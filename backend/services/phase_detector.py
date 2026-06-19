# Reference 2θ peaks for τ-MnAl — replace with your lab's calibrated values.
TAU_MNAL_PEAKS_DEG = [35.5, 42.1, 58.3]
PEAK_TOLERANCE_DEG = 0.35


def detect_tau_mnal(peaks: list[dict]) -> dict:
    angles = [p["angle"] for p in peaks]
    matched_refs = []
    for ref in TAU_MNAL_PEAKS_DEG:
        if any(abs(angle - ref) <= PEAK_TOLERANCE_DEG for angle in angles):
            matched_refs.append(ref)

    matched = len(matched_refs)
    required = min(2, len(TAU_MNAL_PEAKS_DEG))
    return {
        "tauDetected": matched >= required,
        "matchedPeakCount": matched,
        "matchedReferenceAngles": matched_refs,
        "confidence": matched / len(TAU_MNAL_PEAKS_DEG) if TAU_MNAL_PEAKS_DEG else 0.0,
    }
