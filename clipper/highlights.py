"""Chat-spike highlight detection.

This is deliberately simple: count chat messages per fixed window, compare each
window to the median rate, and turn the strongest spikes into clip segments.
A future loudness/AI detector can implement the same `find_highlights` interface.
"""
from __future__ import annotations

from statistics import median
from typing import Any


def find_highlights(
    message_times: list[float],
    window_seconds: float = 10.0,
    spike_factor: float = 3.0,
    clip_before_seconds: float = 15.0,
    clip_after_seconds: float = 20.0,
    min_gap_seconds: float = 60.0,
    max_clips: int = 8,
) -> list[dict[str, Any]]:
    """Return clip segments sorted by spike strength (strongest first).

    Each segment is ``{"start": seconds, "end": seconds, "score": count}``.
    """
    message_times = sorted(t for t in message_times if t is not None and t >= 0)
    if not message_times:
        return []

    if window_seconds <= 0:
        raise ValueError("window_seconds must be > 0")

    counts: dict[int, int] = {}
    for t in message_times:
        bucket = int(t // window_seconds)
        counts[bucket] = counts.get(bucket, 0) + 1

    values = list(counts.values())
    med = median(values)
    threshold = spike_factor * med if med > 0 else spike_factor

    spikes = [(bucket, count) for bucket, count in counts.items() if count > threshold]
    if not spikes:
        return []

    raw: list[dict[str, Any]] = []
    for bucket, count in spikes:
        window_start = bucket * window_seconds
        start = max(0.0, window_start - clip_before_seconds)
        end = window_start + window_seconds + clip_after_seconds
        raw.append({"start": float(start), "end": float(end), "score": count})

    # Merge overlaps / near-neighbours.
    raw.sort(key=lambda seg: seg["start"])
    merged: list[dict[str, Any]] = []
    for seg in raw:
        if merged and seg["start"] <= merged[-1]["end"] + min_gap_seconds:
            prev = merged[-1]
            prev["end"] = max(prev["end"], seg["end"])
            prev["score"] = max(prev["score"], seg["score"])
        else:
            merged.append(dict(seg))

    merged.sort(key=lambda seg: seg["score"], reverse=True)
    return merged[:max_clips]
