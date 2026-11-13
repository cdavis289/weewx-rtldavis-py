"""Phase C hop scheduling and tune timing (no SDR hardware required)."""
from types import SimpleNamespace
import pytest
from user.rtldavis_receiver import Receiver
from user.rtldavis_phase_c_diagnostics import (
    PhaseCDiagnostics, observe_hardware_tune)


def test_hop_scheduling_records_expected_visit_and_deadline():
    diag = PhaseCDiagnostics(clock=lambda: 0)
    receiver = Receiver("US", [7])
    receiver.phase_c_diagnostics = diag
    receiver.start(0.0)
    receiver._last_visit[0] = 0.0
    receiver._last_hop[0] = 0
    receiver._hop_next(0.1)
    event = diag._history[-1]
    assert event["event"] == "hop_scheduled"
    assert event["transmitter"] == 8
    assert event["expected_visit_monotonic"] == pytest.approx(3.0)
    assert event["deadline_monotonic"] == pytest.approx(receiver._deadline)
    assert event["target_frequency_hz"] == receiver.frequency


def test_hardware_tune_records_duration_and_lead():
    times = iter([1.0, 1.012])
    diag = PhaseCDiagnostics(clock=lambda: 0)
    receiver = SimpleNamespace(_phase_c_expected_visit=2.0, channel=5)
    called = []
    result = observe_hardware_tune(diag,
        lambda freq: called.append(freq) or "ok", 902000000, receiver,
        clock=lambda: next(times))
    assert result == "ok"
    assert called == [902000000]
    event = diag._history[-1]
    assert event["tune_duration_ms"] == pytest.approx(12)
    assert event["tune_complete_lead_ms"] == pytest.approx(988)
    assert event["error"] is None


def test_hardware_tune_preserves_error():
    times = iter([1.0, 1.01])
    diag = PhaseCDiagnostics(clock=lambda: 0)
    receiver = SimpleNamespace(_phase_c_expected_visit=None, channel=1)
    def fail(_):
        raise OSError("tune failed")
    with pytest.raises(OSError, match="tune failed"):
        observe_hardware_tune(diag, fail, 902000000, receiver,
                              clock=lambda: next(times))
    assert diag._history[-1]["error"] == "OSError"


def test_diagnostics_disabled_by_default():
    receiver = Receiver("US", [7])
    assert receiver.phase_c_diagnostics is None
