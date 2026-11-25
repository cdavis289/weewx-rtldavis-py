"""Receiver diagnostics do not alter burst acceptance."""
from types import SimpleNamespace
from user.rtldavis_receiver import Receiver


def test_burst_counters_track_identical_and_different_payloads():
    receiver = Receiver("US", [7])
    receiver._accepted = {}
    receiver.diagnostic_counts = {
        "burst_suppressed": 0, "burst_identical": 0,
        "burst_different": 0, "accepted": 0,
    }
    receiver._last_accepted_payload = {}
    receiver._reported = set()
    a = SimpleNamespace(payload=bytes([0x90, 0, 0, 11, 0, 0, 0, 0]),
                        frequency_error=0)
    b = SimpleNamespace(payload=bytes([0x90, 0, 0, 70, 0, 0, 0, 0]),
                        frequency_error=0)
    # Set a prior accepted burst without depending on hop scheduling.
    receiver._accepted[0] = 100.0
    receiver._last_accepted_payload[0] = a.payload
    assert receiver._accept(a, 100.1, 0, receiver.frequencies[0]) is None
    assert receiver._accept(b, 100.2, 0, receiver.frequencies[0]) is None
    assert receiver.diagnostic_counts["burst_suppressed"] == 2
    assert receiver.diagnostic_counts["burst_identical"] == 1
    assert receiver.diagnostic_counts["burst_different"] == 1
    assert receiver.diagnostic_counts["accepted"] == 0


def test_timing_guard_counter_initialized():
    from user.rtldavis_receiver import Receiver

    receiver = Receiver("US", [0])

    assert receiver.diagnostic_counts[
        "timing_early_suppressed"] == 0


def test_timing_guard_rejection_records_diagnostic_event():
    from types import SimpleNamespace
    from user.rtldavis_receiver import (
        Receiver,
        transmitter_period,
    )
    from user.rtldavis_phase_c_diagnostics import PhaseCDiagnostics

    receiver = Receiver("US", [0])
    receiver.start(0.0)

    receiver.phase_c_diagnostics = PhaseCDiagnostics(
        clock=lambda: 0.0)

    receiver._syncing = False
    receiver._last_visit[0] = 100.0

    expected = 100.0 + transmitter_period(0)
    now = expected - 0.8

    candidate = SimpleNamespace(
        payload=bytes.fromhex("8000000000000000"),
        frequency_error=-6150.0,
    )

    accepted_before = receiver.diagnostic_counts["accepted"]
    learned_before = dict(receiver.learned)
    visits_before = list(receiver._last_visit)

    result = receiver._accept(
        candidate, now,
        receiver.channel, receiver.frequency)

    assert result is None
    assert receiver.diagnostic_counts[
        "timing_early_suppressed"] == 1

    assert receiver.diagnostic_counts["accepted"] == accepted_before
    assert receiver.learned == learned_before
    assert receiver._last_visit == visits_before

    event = receiver.phase_c_diagnostics._history[-1]

    assert event["event"] == "candidate_rejected"
    assert event["reason"] == "timing_early_suppressed"
    assert event["transmitter"] == 1
    assert event["early_by_ms"] == 800.0
    assert event["frequency_error_hz"] == -6150.0
    assert event["expected_visit_monotonic"] == expected
