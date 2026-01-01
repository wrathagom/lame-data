"""
Gait Segmentation Algorithm for Horse Biomechanics

Detects gait changes using variance and frequency analysis of accelerometer magnitude.
"""

import numpy as np
from typing import List, Dict


def segment_gait(magnitude: List[float],
                 sample_rate: int = 194,
                 variance_threshold: float = 2.0,
                 frequency_threshold: float = 0.3,
                 min_segment_seconds: float = 2.0) -> Dict:
    """
    Detect gait changes in accelerometer magnitude data.

    Parameters:
    - magnitude: List of magnitude values (sqrt(x² + y² + z²))
    - sample_rate: Samples per second (default 194 Hz)
    - variance_threshold: Z-score threshold for variance changes (default 2.0)
    - frequency_threshold: Hz change to detect frequency shifts (default 0.3)
    - min_segment_seconds: Minimum segment duration in seconds (default 2.0)

    Returns:
    - dict with boundaries (sample indices), times (seconds), confidence scores
    """
    if len(magnitude) < sample_rate * 2:
        # Too short for meaningful segmentation
        return {
            'boundaries': [0],
            'times': [0.0],
            'confidence': [1.0],
            'count': 1,
            'params': {
                'variance_threshold': variance_threshold,
                'frequency_threshold': frequency_threshold,
                'min_segment_seconds': min_segment_seconds
            }
        }

    mag = np.array(magnitude)
    window_size = sample_rate  # 1 second window
    window_step = sample_rate // 2  # 50% overlap
    min_samples = int(min_segment_seconds * sample_rate)

    # Calculate windowed statistics
    windows = []
    window_centers = []

    for i in range(0, len(mag) - window_size + 1, window_step):
        window = mag[i:i + window_size]
        windows.append(window)
        window_centers.append(i + window_size // 2)

    if len(windows) < 2:
        return {
            'boundaries': [0],
            'times': [0.0],
            'confidence': [1.0],
            'count': 1,
            'params': {
                'variance_threshold': variance_threshold,
                'frequency_threshold': frequency_threshold,
                'min_segment_seconds': min_segment_seconds
            }
        }

    # Compute variance for each window
    variances = np.array([np.var(w) for w in windows])

    # Compute dominant frequency for each window using FFT
    frequencies = []
    for window in windows:
        # Remove DC component
        centered = window - np.mean(window)
        # Apply Hanning window to reduce spectral leakage
        windowed = centered * np.hanning(len(centered))
        # FFT
        fft = np.fft.rfft(windowed)
        fft_mag = np.abs(fft)
        # Find dominant frequency (skip DC component at index 0)
        if len(fft_mag) > 1:
            freq_bins = np.fft.rfftfreq(len(window), 1.0 / sample_rate)
            # Focus on gait-relevant frequencies (0.5 - 5 Hz covers walk to canter)
            valid_mask = (freq_bins >= 0.5) & (freq_bins <= 5.0)
            if np.any(valid_mask):
                valid_fft = fft_mag.copy()
                valid_fft[~valid_mask] = 0
                dominant_idx = np.argmax(valid_fft)
                dominant_freq = freq_bins[dominant_idx]
            else:
                dominant_freq = 0.0
        else:
            dominant_freq = 0.0
        frequencies.append(dominant_freq)

    frequencies = np.array(frequencies)

    # Detect variance change points using z-score
    if len(variances) > 1 and np.std(variances) > 0:
        variance_zscore = np.abs((variances - np.mean(variances)) / np.std(variances))
        variance_changes = variance_zscore > variance_threshold
    else:
        variance_changes = np.zeros(len(variances), dtype=bool)

    # Detect frequency change points
    if len(frequencies) > 1:
        freq_diff = np.abs(np.diff(frequencies))
        freq_changes = np.concatenate([[False], freq_diff > frequency_threshold])
    else:
        freq_changes = np.zeros(len(frequencies), dtype=bool)

    # Combine signals with weighting (60% variance, 40% frequency)
    combined_score = 0.6 * variance_changes.astype(float) + 0.4 * freq_changes.astype(float)
    change_detected = combined_score > 0.4

    # Find boundary sample indices
    raw_boundaries = [0]  # Always start with 0
    raw_confidence = [1.0]

    for i, is_change in enumerate(change_detected):
        if is_change:
            sample_idx = window_centers[i]
            raw_boundaries.append(sample_idx)
            raw_confidence.append(float(combined_score[i]))

    # Merge boundaries that are too close together
    final_boundaries = [raw_boundaries[0]]
    final_confidence = [raw_confidence[0]]

    for i in range(1, len(raw_boundaries)):
        if raw_boundaries[i] - final_boundaries[-1] >= min_samples:
            final_boundaries.append(raw_boundaries[i])
            final_confidence.append(raw_confidence[i])
        elif raw_confidence[i] > final_confidence[-1]:
            # Keep the higher confidence boundary
            final_boundaries[-1] = raw_boundaries[i]
            final_confidence[-1] = raw_confidence[i]

    # Convert to times
    times = [b / sample_rate for b in final_boundaries]

    return {
        'boundaries': final_boundaries,
        'times': times,
        'confidence': final_confidence,
        'count': len(final_boundaries),
        'params': {
            'variance_threshold': variance_threshold,
            'frequency_threshold': frequency_threshold,
            'min_segment_seconds': min_segment_seconds
        }
    }
