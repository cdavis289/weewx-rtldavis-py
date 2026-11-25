"""Offline regression tests for the 2026-11-18 Phase C early-frame event.

Place in the repository's tests/ directory and run:
    python -m pytest -q tests/test_phase_c_sync_regression.py

These tests use the real Receiver scheduling logic but inject prepared CRC-valid
candidates; they do not use a radio, Docker, or the production diagnostic JSON.
The guarded subclass is a PROTOTYPE of a possible fix, not a production patch.
"""

import pytest

from user import rtldavis_dsp as dsp
from user import rtldavis_receiver as receiver

TX = 7  # The diagnostic reports transmitter 8 (one-based); payload ID is 7.
PERIOD = receiver.transmitter_period(TX)
EXPECTED_EARLY_SECONDS = 0.822


def candidate(frequency_error=0.0):
    # _accept() consumes transmitter ID and frequency error. The payload here
    # is genuinely CRC-valid, so it is representative of a decoded candidate.
    body = bytes([0x80 | TX, 2, 128, 0x25, 0x18, 1])
    data = body + dsp.crc16(body).to_bytes(2, "big")
    return dsp.Candidate(0, data, frequency_error)


def primed(receiver_type=receiver.Receiver):
    """Prepare a synchronized receiver just before its next expected visit."""
    rx = receiver_type("US", [TX])
    rx.start(0.0)
    # The receiver is initially searching. A first packet establishes lock.
    first_channel = rx.channel
    first_time = 1000.0
    first = rx._accept(candidate(), first_time, first_channel, rx.frequency)
    assert first is not None
    assert not rx._syncing
    assert rx._last_visit[0] == pytest.approx(first_time)
    # The next channel is the predicted channel after a normal 3-second hop.
    return rx, first_time + PERIOD


def snapshot(rx):
    """Schedule and learning state that must not change on a rejected frame."""
    return (
        tuple(rx._last_visit), tuple(rx._last_hop), rx._deadline,
        rx.channel, rx.frequency, rx.offset, dict(rx.learned),
        tuple(rx.counts), tuple(rx._missed),
    )


class TimingGuardPrototype(receiver.Receiver):
    """Experimental guard: reject early frames before changing any state.

    This deliberately protects only the synchronized, single-transmitter
    early-arrival case. It is NOT a proposed final implementation: production
    handling needs multi-transmitter validation, clock-error analysis, and
    tests for late/adjacent-channel reception.
    """

    EARLY_TOLERANCE = 0.30  # illustrative only; not a calibrated threshold

    def _accept(self, candidate, now, channel, frequency):
        transmitter = candidate.payload[0] & 7
        if not self._syncing and transmitter in self.index:
            i = self.index[transmitter]
            last = self._last_visit[i]
            if last is not None:
                period = receiver.transmitter_period(transmitter)
                next_expected = last + period
                while next_expected + receiver.RECEIVE_WINDOW < now:
                    next_expected += period
                if now < next_expected - self.EARLY_TOLERANCE:
                    return None
        return super()._accept(candidate, now, channel, frequency)


def test_baseline_on_time_frame_keeps_expected_three_second_phase():
    rx, expected = primed()
    frame = rx._accept(candidate(-12.0), expected, rx.channel, rx.frequency)
    assert frame is not None
    assert rx._last_visit[0] == pytest.approx(expected)
    assert rx._deadline == pytest.approx(expected + PERIOD + receiver.RECEIVE_WINDOW)


def test_current_receiver_rejects_nov18_early_reanchor():
    """The production receiver rejects the early candidate without changing its phase."""
    rx, expected = primed()
    early = expected - EXPECTED_EARLY_SECONDS
    before = snapshot(rx)
    frame = rx._accept(candidate(-6152.383), early, rx.channel, rx.frequency)
    assert frame is None
    assert snapshot(rx) == before
    assert rx.diagnostic_counts["timing_early_suppressed"] == 1


def test_guard_prototype_rejects_early_frame_without_mutating_state():
    rx, expected = primed(TimingGuardPrototype)
    before = snapshot(rx)
    frame = rx._accept(candidate(-6152.383), expected - EXPECTED_EARLY_SECONDS,
                       rx.channel, rx.frequency)
    assert frame is None
    assert snapshot(rx) == before


def test_guard_prototype_accepts_next_real_frame_after_early_outlier():
    rx, expected = primed(TimingGuardPrototype)
    assert rx._accept(candidate(-6152.383), expected - EXPECTED_EARLY_SECONDS,
                      rx.channel, rx.frequency) is None
    frame = rx._accept(candidate(-12.0), expected, rx.channel, rx.frequency)
    assert frame is not None
    assert rx._last_visit[0] == pytest.approx(expected)


def test_guard_prototype_still_recovers_via_existing_missed_frame_path():
    rx, expected = primed(TimingGuardPrototype)
    assert rx._accept(candidate(-6152.383), expected - EXPECTED_EARLY_SECONDS,
                      rx.channel, rx.frequency) is None
    # Drive the receiver's normal timeout mechanism rather than fabricating
    # synchronization state. This should eventually enter search mode.
    for _ in range(receiver.MAX_MISSED + 1):
        rx._timeout(rx._deadline)
    assert rx._syncing
    # Search-mode reception must not be blocked by the timing guard.
    frame = rx._accept(candidate(), rx._deadline + 1.0, rx.channel, rx.frequency)
    assert frame is not None
    assert not rx._syncing


def test_guard_prototype_accepts_small_early_jitter():
    rx, expected = primed(TimingGuardPrototype)
    frame = rx._accept(candidate(-12.0), expected - 0.05, rx.channel, rx.frequency)
    assert frame is not None
    assert rx._last_visit[0] == pytest.approx(expected - 0.05)
