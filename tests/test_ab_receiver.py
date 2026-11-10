"""Regression tests for passive A/B synchronization telemetry.

No RTL-SDR hardware is required.
"""
from types import SimpleNamespace

from user.rtldavis_receiver import Receiver, Radio, MAX_MISSED


class Recorder:
    def __init__(self):
        self.events = []

    def event(self, name, **fields):
        self.events.append((name, fields))


def test_missed_frames_trigger_loss_and_reacquisition():
    receiver = Receiver("US", [7])
    recorder = Recorder()
    receiver.ab_diagnostics = recorder
    receiver.start(0.0)

    # Simulate an already synchronized receiver; keep the same timeout path
    # used in production to verify loss classification and counter increments.
    receiver._syncing = False
    receiver.locked = True
    receiver._last_visit[0] = 0.0
    receiver._last_hop[0] = 0
    receiver._next = 0
    receiver._missed[0] = 0
    receiver._ab_last_frame = 0.0
    for index in range(MAX_MISSED + 1):
        receiver._timeout(receiver._deadline)

    names = [name for name, _ in recorder.events]
    assert "synchronization_lost" in names
    assert receiver._syncing
    assert receiver.diagnostic_counts["missed_predictions"] == MAX_MISSED + 1
    assert receiver.diagnostic_counts["sync_losses"] == 1
    assert [details["missed_frames"] for name, details in recorder.events
            if name == "missed_frame_streak"] == [1, 10, 25, 50]
    assert next(details for name, details in recorder.events
                if name == "synchronization_lost")["missed_frames"] == 52

    # Use a valid candidate to reacquire the configured transmitter.
    candidate = SimpleNamespace(
        payload=bytes([0x87, 0, 0, 0, 0, 0, 0, 0]),
        frequency_error=0.0)
    frame = receiver._accept(
        candidate, receiver._deadline - 1, receiver.channel, receiver.frequency)
    assert frame is not None
    assert not receiver._syncing
    assert receiver.diagnostic_counts["sync_acquired"] == 1
    assert any(name == "synchronization_acquired" and details["recovery_seconds"] is not None
               for name, details in recorder.events)


def test_lock_loss_event_does_not_change_frequency_reset_policy():
    receiver = Receiver("EU", [0])
    recorder = Recorder()
    receiver.ab_diagnostics = recorder
    receiver.start(0.0)
    receiver.locked = True
    receiver.learned[(0, 0)] = 8000
    receiver._heard = False
    for _ in range(2):
        receiver._timeout(receiver._deadline)
    assert not receiver.locked
    assert receiver.learned == {}
    assert receiver.diagnostic_counts["sync_losses"] == 1
    assert any(name == "frequency_lock_lost" for name, _ in recorder.events)


def test_ab_disabled_has_no_external_recorder():
    rx = Receiver("EU", [0])
    radio = Radio(rx)
    assert rx.ab_diagnostics is None
    assert radio.ab_diagnostics is None
