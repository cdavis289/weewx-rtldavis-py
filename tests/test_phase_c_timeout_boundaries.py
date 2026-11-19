"""Phase C timing-guard boundary regressions (offline; no Docker changes).

Copy to tests/test_phase_c_timeout_boundaries.py, then run:
    PYTHONPATH=bin .venv/bin/python -m pytest -q tests/test_phase_c_timeout_boundaries.py

These tests deliberately assert desired behavior; a failure is evidence to inspect,
not permission to deploy. Uses the real Receiver._timeout and Receiver._accept.
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
    assert rx._last_visit[0] == pytest.approx(1000.0)
    return rx


def snapshot(rx):
    return (tuple(rx._last_visit), tuple(rx._last_hop), rx._deadline,
            rx.channel, rx.frequency, rx.offset, dict(rx.learned),
            tuple(rx.counts), tuple(rx._missed), dict(rx._accepted),
            dict(rx._last_accepted_payload))


def timeout_one_prediction(rx):
    """Advance the real scheduler exactly once, without fabricating state."""
    deadline = rx._deadline
    before = rx._last_visit[0]
    rx._timeout(deadline)
    assert not rx._syncing
    assert rx._last_visit[0] == pytest.approx(before + PERIOD)
    assert rx._missed[0] == 1
    return deadline


def test_valid_frame_after_one_missed_prediction():
    rx = primed()
    timeout_one_prediction(rx)
    expected = 1000.0 + 2 * PERIOD
    assert rx._accept(candidate(), expected, rx.channel, rx.frequency) is not None
    assert rx._last_visit[0] == pytest.approx(expected)
    assert rx._missed[0] == 0


def test_valid_frame_just_before_timeout_deadline():
    rx = primed()
    deadline = rx._deadline
    expected = 1000.0 + PERIOD
    assert deadline > expected
    assert rx._accept(candidate(), deadline - 0.001, rx.channel, rx.frequency) is not None
    assert rx._last_visit[0] == pytest.approx(deadline - 0.001)

def test_candidate_after_expired_deadline_is_rejected_without_reanchoring():
    """A candidate after an expired reception window must not reanchor the schedule."""
    rx = primed()
    deadline = timeout_one_prediction(rx)

    before = snapshot(rx)
    count = rx.diagnostic_counts.get('timing_early_suppressed', 0)

    frame = rx._accept(
        candidate(),
        deadline + 0.001,
        rx.channel,
        rx.frequency,
    )

    assert frame is None
    assert snapshot(rx) == before
    assert rx.diagnostic_counts.get('timing_early_suppressed', 0) == count + 1

@pytest.mark.parametrize('misses', [1, 3, 5])
def test_early_candidate_after_missed_predictions_does_not_reanchor(misses):
    rx = primed()
    for _ in range(misses):
        rx._timeout(rx._deadline)
        assert not rx._syncing
    expected = 1000.0 + (misses + 1) * PERIOD
    early = expected - 0.823
    before = snapshot(rx)
    count = rx.diagnostic_counts.get('timing_early_suppressed', 0)
    assert rx._accept(candidate(-6152.383), early, rx.channel, rx.frequency) is None
    assert snapshot(rx) == before
    assert rx.diagnostic_counts.get('timing_early_suppressed', 0) == count + 1
    assert rx._accept(candidate(-12), expected, rx.channel, rx.frequency) is not None
    assert rx._last_visit[0] == pytest.approx(expected)
