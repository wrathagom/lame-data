"""
Gait Segmentation Algorithm for Horse Biomechanics

Detects:
1. Movement vs non-movement (stationary)
2. Gait changes using variance and frequency analysis
"""

import numpy as np
from typing import List, Dict


def segment_gait(magnitude: List[float],
                 sample_rate: int = 194,
                 movement_threshold: float = 0.02,
                 variance_threshold: float = 2.0,
                 frequency_threshold: float = 0.3,
                 min_segment_seconds: float = 2.0) -> Dict:
    """
    Detect movement and gait changes in accelerometer magnitude data.

    Parameters:
    - magnitude: List of magnitude values (sqrt(x² + y² + z²))
    - sample_rate: Samples per second (default 194 Hz)
    - movement_threshold: Variance threshold for movement detection (default 0.02)
      Below this = stationary, above = moving
    - variance_threshold: Z-score threshold for gait variance changes (default 2.0)
    - frequency_threshold: Hz change to detect frequency shifts (default 0.3)
    - min_segment_seconds: Minimum segment duration in seconds (default 2.0)

    Returns:
    - dict with boundaries, times, types (stationary/moving), confidence scores
    """
    if len(magnitude) < sample_rate * 2:
        # Too short for meaningful segmentation
        return _empty_result(magnitude, sample_rate, movement_threshold,
                            variance_threshold, frequency_threshold, min_segment_seconds)

    mag = np.array(magnitude)
    window_size = sample_rate  # 1 second window
    window_step = sample_rate // 2  # 50% overlap
    min_samples = int(min_segment_seconds * sample_rate)

    # Calculate windowed statistics
    windows = []
    window_starts = []
    window_centers = []

    for i in range(0, len(mag) - window_size + 1, window_step):
        window = mag[i:i + window_size]
        windows.append(window)
        window_starts.append(i)
        window_centers.append(i + window_size // 2)

    if len(windows) < 2:
        return _empty_result(magnitude, sample_rate, movement_threshold,
                            variance_threshold, frequency_threshold, min_segment_seconds)

    # Compute variance for each window
    variances = np.array([np.var(w) for w in windows])

    # Step 1: Classify each window as moving or stationary
    is_moving = variances > movement_threshold

    # Step 2: Detect movement state transitions
    movement_changes = np.diff(is_moving.astype(int))  # 1 = start moving, -1 = stop moving

    # Step 3: Compute gait metrics for moving windows only
    frequencies = []
    for i, window in enumerate(windows):
        if is_moving[i]:
            # Remove DC component
            centered = window - np.mean(window)
            # Apply Hanning window to reduce spectral leakage
            windowed = centered * np.hanning(len(centered))
            # FFT
            fft = np.fft.rfft(windowed)
            fft_mag = np.abs(fft)
            # Find dominant frequency
            if len(fft_mag) > 1:
                freq_bins = np.fft.rfftfreq(len(window), 1.0 / sample_rate)
                # Focus on gait-relevant frequencies (0.5 - 5 Hz)
                valid_mask = (freq_bins >= 0.5) & (freq_bins <= 5.0)
                if np.any(valid_mask):
                    valid_fft = fft_mag.copy()
                    valid_fft[~valid_mask] = 0
                    dominant_idx = np.argmax(valid_fft)
                    frequencies.append(freq_bins[dominant_idx])
                else:
                    frequencies.append(0.0)
            else:
                frequencies.append(0.0)
        else:
            frequencies.append(0.0)

    frequencies = np.array(frequencies)

    # Step 4: Detect gait changes within moving sections
    # Only consider variance/frequency changes when both windows are moving
    gait_change_score = np.zeros(len(windows))

    for i in range(1, len(windows)):
        if is_moving[i] and is_moving[i-1]:
            # Both windows are moving - check for gait change
            # Variance z-score (local to moving sections)
            moving_variances = variances[is_moving]
            if len(moving_variances) > 1 and np.std(moving_variances) > 0:
                var_zscore = abs(variances[i] - np.mean(moving_variances)) / np.std(moving_variances)
                var_change = var_zscore > variance_threshold
            else:
                var_change = False

            # Frequency change
            freq_change = abs(frequencies[i] - frequencies[i-1]) > frequency_threshold

            # Combined score
            gait_change_score[i] = 0.6 * float(var_change) + 0.4 * float(freq_change)

    # Step 5: Build segment boundaries
    raw_boundaries = []
    raw_types = []
    raw_confidence = []

    # Always start with boundary at 0
    raw_boundaries.append(0)
    raw_types.append('moving' if is_moving[0] else 'stationary')
    raw_confidence.append(1.0)

    for i in range(len(windows)):
        sample_idx = window_centers[i]

        # Check for movement state change
        if i > 0 and movement_changes[i-1] != 0:
            raw_boundaries.append(sample_idx)
            raw_types.append('moving' if is_moving[i] else 'stationary')
            raw_confidence.append(1.0)  # Movement changes are high confidence

        # Check for gait change (only within moving sections)
        elif gait_change_score[i] > 0.4:
            raw_boundaries.append(sample_idx)
            raw_types.append('moving')  # Gait changes only happen during movement
            raw_confidence.append(float(gait_change_score[i]))

    # Step 6: Merge boundaries that are too close together
    final_boundaries = [raw_boundaries[0]]
    final_types = [raw_types[0]]
    final_confidence = [raw_confidence[0]]

    for i in range(1, len(raw_boundaries)):
        if raw_boundaries[i] - final_boundaries[-1] >= min_samples:
            final_boundaries.append(raw_boundaries[i])
            final_types.append(raw_types[i])
            final_confidence.append(raw_confidence[i])
        else:
            # Too close - keep the higher priority boundary
            # Priority: movement changes > gait changes
            is_movement_change = (raw_types[i] != final_types[-1]) or \
                                (raw_types[i] == 'stationary' and final_types[-1] == 'moving') or \
                                (raw_types[i] == 'moving' and final_types[-1] == 'stationary')
            if is_movement_change or raw_confidence[i] > final_confidence[-1]:
                final_boundaries[-1] = raw_boundaries[i]
                final_types[-1] = raw_types[i]
                final_confidence[-1] = raw_confidence[i]

    # Convert to times
    times = [b / sample_rate for b in final_boundaries]

    # Calculate segment durations
    durations = []
    for i in range(len(final_boundaries)):
        if i < len(final_boundaries) - 1:
            durations.append((final_boundaries[i+1] - final_boundaries[i]) / sample_rate)
        else:
            durations.append((len(magnitude) - final_boundaries[i]) / sample_rate)

    return {
        'boundaries': final_boundaries,
        'times': times,
        'types': final_types,
        'durations': durations,
        'confidence': final_confidence,
        'count': len(final_boundaries),
        'params': {
            'movement_threshold': movement_threshold,
            'variance_threshold': variance_threshold,
            'frequency_threshold': frequency_threshold,
            'min_segment_seconds': min_segment_seconds
        }
    }


def _empty_result(magnitude, sample_rate, movement_threshold,
                  variance_threshold, frequency_threshold, min_segment_seconds):
    """Return result for data too short to segment."""
    # Determine if the short segment is moving or stationary
    mag = np.array(magnitude)
    var = np.var(mag) if len(mag) > 0 else 0
    seg_type = 'moving' if var > movement_threshold else 'stationary'

    return {
        'boundaries': [0],
        'times': [0.0],
        'types': [seg_type],
        'durations': [len(magnitude) / sample_rate],
        'confidence': [1.0],
        'count': 1,
        'params': {
            'movement_threshold': movement_threshold,
            'variance_threshold': variance_threshold,
            'frequency_threshold': frequency_threshold,
            'min_segment_seconds': min_segment_seconds
        }
    }
