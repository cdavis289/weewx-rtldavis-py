"""Phase C USB sample-block processing measurements; no SDR required."""
import pytest
from user.rtldavis_phase_c_diagnostics import (
    PhaseCDiagnostics, observe_sample_processing)


def test_processing_timing_and_original_result():
    times = iter([10.025, 10.035])
    diag = PhaseCDiagnostics(clock=lambda: 10.0)
    calls = []
    def feed(data, arrival):
        calls.append((data, arrival))
        return ["frame"]
    result = observe_sample_processing(
        diag, feed, b"\x00\xff", 10.0, queue_depth=3,
        clock=lambda: next(times))
    assert result == ["frame"]
    assert calls == [(b"\x00\xff", 10.0)]
    event = diag._history[-1]
    assert event["event"] == "sample_processing"
    assert event["queue_wait_ms"] == pytest.approx(25)
    assert event["demod_duration_ms"] == pytest.approx(10)
    assert event["completion_age_ms"] == pytest.approx(35)
    assert event["queue_depth"] == 3
    assert event["sample_bytes"] == 2
    assert event["error"] is None
    assert "data" not in event


def test_processing_preserves_exception():
    times = iter([2.0, 2.005])
    diag = PhaseCDiagnostics(clock=lambda: 2.0)
    def fail(data, arrival):
        raise RuntimeError("demod failure")
    with pytest.raises(RuntimeError, match="demod failure"):
        observe_sample_processing(diag, fail, b"abc", 1.99,
                                  clock=lambda: next(times))
    assert diag._history[-1]["error"] == "RuntimeError"


def test_processing_event_is_bounded():
    current = [0.0]
    diag = PhaseCDiagnostics(max_events=3, before_seconds=60,
                             clock=lambda: current[0])
    for i in range(10):
        current[0] = float(i)
        observe_sample_processing(diag, lambda data, arrival: [],
                                  b"x", float(i),
                                  clock=lambda: current[0])
    assert len(diag._history) == 3
    assert all(event["event"] == "sample_processing" for event in diag._history)


def test_processing_diagnostics_do_not_require_usb_hardware():
    from user.rtldavis_receiver import Receiver, Radio
    receiver = Receiver("US", [7])
    radio = Radio(receiver)
    assert receiver.phase_c_diagnostics is None



def test_sample_summary_retains_history_and_maxima():
    diag = PhaseCDiagnostics(before_seconds=180, max_events=20000,
                             sample_summary_seconds=1)
    for i in range(30000):
        diag.observe("sample_processing", timestamp=i / 200,
                     sample_bytes=16, queue_wait_ms=i % 7,
                     demod_duration_ms=2, completion_age_ms=9,
                     queue_depth=i % 4, error=None)
    diag.trigger("test", timestamp=150)
    records = diag.drain(timestamp=210)[0]["events"]
    assert len(records) == 150
    assert sum(r["count"] for r in records) == 30000
    assert max(r["max_queue_wait_ms"] for r in records) == 6
    assert max(r["max_queue_depth"] for r in records) == 3
    assert sum(r["sample_bytes"] for r in records) == 480000


def test_sample_summary_preserves_errors_and_capture_boundary():
    diag = PhaseCDiagnostics(after_seconds=1, sample_summary_seconds=1)
    fields = dict(sample_bytes=16, queue_wait_ms=1, demod_duration_ms=2,
                  completion_age_ms=3, queue_depth=1)
    diag.observe("sample_processing", timestamp=0, **fields)
    diag.trigger("test", timestamp=0.5)
    diag.observe("sample_processing", timestamp=1, **fields)
    diag.observe("sample_processing", timestamp=1.1, error="RuntimeError", **fields)
    diag.observe("sample_processing", timestamp=1.2, **fields)
    diag.observe("sample_processing", timestamp=1.6, **fields)
    records = diag.drain(timestamp=2)[0]["events"]
    assert [r["event"] for r in records] == [
        "sample_processing_summary", "sample_processing_summary",
        "sample_processing", "sample_processing_summary"]
    assert records[2]["error"] == "RuntimeError"
    assert records[-1]["monotonic"] == 1.2
