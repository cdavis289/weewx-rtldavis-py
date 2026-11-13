"""Phase C passive capture tests; no SDR hardware required."""
from user.rtldavis_phase_c_diagnostics import PhaseCDiagnostics


def test_pre_and_post_trigger_capture():
    d = PhaseCDiagnostics(before_seconds=5, after_seconds=3, clock=lambda: 0)
    d.observe("old", timestamp=1)
    d.observe("before", timestamp=7)
    assert d.trigger("missed_frame_streak", timestamp=10, missed=10)
    d.observe("after", timestamp=12)
    assert d.drain(timestamp=12) == []
    captures = d.drain(timestamp=13)
    assert len(captures) == 1
    assert captures[0]["reason"] == "missed_frame_streak"
    assert captures[0]["trigger_fields"]["missed"] == 10
    assert [e["event"] for e in captures[0]["events"]] == ["before", "after"]


def test_history_is_bounded_and_repeated_trigger_is_ignored():
    d = PhaseCDiagnostics(before_seconds=100, after_seconds=2, max_events=3)
    for n in range(5):
        d.observe("hop", timestamp=n, index=n)
    assert d.trigger("loss", timestamp=5)
    assert not d.trigger("duplicate", timestamp=5.5)
    capture, = d.drain(timestamp=7)
    assert [e["index"] for e in capture["events"]] == [2, 3, 4]


def test_pending_captures_are_bounded():
    d = PhaseCDiagnostics(before_seconds=0, after_seconds=0, max_pending=2)
    for n in range(3):
        assert d.trigger("loss", timestamp=n)
        d.observe("event", timestamp=n + 0.1)
    assert d.dropped_captures == 1
    assert len(d.drain(timestamp=10)) == 2


def test_drain_can_complete_without_additional_events():
    d = PhaseCDiagnostics(after_seconds=2)
    assert d.trigger("loss", timestamp=10)
    assert d.drain(timestamp=11) == []
    assert len(d.drain(timestamp=12)) == 1
    assert d.drain(timestamp=13) == []
