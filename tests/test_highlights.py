from clipper.highlights import find_highlights


def test_empty_chat():
    assert find_highlights([]) == []


def test_steady_chat_has_no_spikes():
    times = [float(i * 10) for i in range(10)]  # 1 message per 10s window
    assert find_highlights(times, window_seconds=10, spike_factor=3) == []


def test_single_spike_returns_one_segment():
    times = [1.0, 2.0, 3.0, 4.0, 5.0, 60.0, 70.0]  # 5 msgs in first window
    segments = find_highlights(
        times,
        window_seconds=10,
        spike_factor=2,
        clip_before_seconds=5,
        clip_after_seconds=5,
    )
    assert len(segments) == 1
    assert segments[0]["score"] == 5
    assert segments[0]["start"] == 0.0  # clamped at zero
    assert segments[0]["end"] == 15.0


def test_close_spikes_are_merged():
    times = [1, 2, 3, 4, 5, 51, 52, 53, 54, 55, 100, 110, 120]
    segments = find_highlights(
        [float(t) for t in times],
        window_seconds=10,
        spike_factor=2,
        clip_before_seconds=2,
        clip_after_seconds=2,
        min_gap_seconds=60,
    )
    assert len(segments) == 1
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 62.0


def test_max_clips_is_respected():
    times = (
        [float(i) for i in range(10)]
        + [100.0, 200.0, 300.0]
        + [float(1000 + i) for i in range(10)]
    )
    segments = find_highlights(
        times,
        window_seconds=10,
        spike_factor=2,
        min_gap_seconds=0,
        max_clips=1,
    )
    assert len(segments) == 1
    assert segments[0]["score"] == 10
