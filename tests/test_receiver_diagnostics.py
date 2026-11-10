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
