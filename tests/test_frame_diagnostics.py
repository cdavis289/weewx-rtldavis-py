"""Accepted-frame diagnostic telemetry never filters observations."""
from user.rtldavis_frame_diagnostics import FrameDiagnostics


def test_normal_frame_has_no_flags():
    d = FrameDiagnostics()
    assert d.inspect(bytes.fromhex("9000000b00100000"), 100, {"wind_gust": 5}) == []
    assert d.counts["accepted_frames"] == 1


def test_identical_and_changed_near_bursts_are_labeled():
    d = FrameDiagnostics()
    a = bytes.fromhex("9000000b00100000")
    b = bytes.fromhex("9000004600100000")
    assert d.inspect(a, 100, {}) == []
    assert d.inspect(a, 100.1, {}) == ["duplicate_candidate"]
    assert d.inspect(b, 100.2, {}) == ["near_burst_candidate"]
    assert d.inspect(b, 103, {}) == []


def test_impossible_humidity_is_flagged_without_mutation():
    d = FrameDiagnostics()
    values = {"humidity": 144.9, "wind_gust": 30}
    assert d.inspect(b"abcdefgh", 100, values) == ["out_of_bounds:humidity"]
    assert values == {"humidity": 144.9, "wind_gust": 30}


def test_separate_transmitters_do_not_trigger_duplicates():
    d = FrameDiagnostics()
    assert d.inspect(bytes.fromhex("9000000b00100000"), 100, {}) == []
    assert d.inspect(bytes.fromhex("9100000b00100000"), 100.1, {}) == []
