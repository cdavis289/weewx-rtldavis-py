"""Tests the real Receiver._accept after applying apply_phase_c_timing_guard.py.

Run: PYTHONPATH=bin python -m pytest -q tests/test_phase_c_guard_integration.py
"""
import pytest
from user import rtldavis_dsp as dsp
from user import rtldavis_receiver as receiver

TX = 7
PERIOD = receiver.transmitter_period(TX)


def candidate(frequency_error=0.0):
    body = bytes([0x80 | TX, 2, 128, 0x25, 0x18, 1])
    return dsp.Candidate(0, body + dsp.crc16(body).to_bytes(2, 'big'), frequency_error)


def primed():
    rx = receiver.Receiver('US', [TX])
    rx.start(0.0)
    assert rx._accept(candidate(), 1000.0, rx.channel, rx.frequency) is not None
    assert not rx._syncing
    return rx


def snapshot(rx):
    return (tuple(rx._last_visit), tuple(rx._last_hop), rx._deadline,
            rx.channel, rx.frequency, rx.offset, dict(rx.learned),
            tuple(rx.counts), tuple(rx._missed), dict(rx._accepted),
            dict(rx._last_accepted_payload))


def test_phase_c_guard_rejects_nov18_candidate_without_state_mutation():
    rx = primed()
    before = snapshot(rx)
    assert rx._accept(candidate(-6152.383), 1002.1773002,
                      rx.channel, rx.frequency) is None
    assert snapshot(rx) == before
    assert rx.diagnostic_counts['timing_early_suppressed'] == 1


def test_phase_c_guard_keeps_next_legitimate_frame():
    rx = primed()
    assert rx._accept(candidate(-6152.383), 1002.1773002,
                      rx.channel, rx.frequency) is None
    assert rx._accept(candidate(-12), 1003.0, rx.channel, rx.frequency) is not None
    assert rx._last_visit[0] == pytest.approx(1003.0)


@pytest.mark.parametrize('early_seconds', [0.0, 0.05, 0.25, 0.299])
def test_phase_c_guard_allows_normal_and_moderate_early_arrivals(early_seconds):
    rx = primed()
    assert rx._accept(candidate(), 1003.0 - early_seconds,
                      rx.channel, rx.frequency) is not None


def test_phase_c_guard_does_not_block_search_reacquisition():
    rx = primed()
    for _ in range(receiver.MAX_MISSED + 1):
        rx._timeout(rx._deadline)
    assert rx._syncing
    assert rx._accept(candidate(), rx._deadline + 1.0,
                      rx.channel, rx.frequency) is not None
    assert not rx._syncing
