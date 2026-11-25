"""Regression tests for bounded persistence and shutdown."""
import json

from user.rtldavis_phase_c_diagnostics import (
    PhaseCDiagnostics, persist_captures)
from user.rtldavis_gust_diagnostics import GustDiagnostics


def test_phase_c_shutdown_preserves_incomplete_capture(tmp_path):
    diag = PhaseCDiagnostics(after_seconds=60)
    diag.observe("before", timestamp=10)
    diag.trigger("test", timestamp=11)
    diag.observe("after", timestamp=12)
    diag.finalize(timestamp=13)

    paths = persist_captures(diag, tmp_path, timestamp=13)
    assert len(paths) == 1
    capture = json.loads(paths[0].read_text())
    assert capture["incomplete"] is True
    assert capture["finalized_monotonic"] == 13
    assert len(capture["events"]) == 2


def test_phase_c_shutdown_marks_elapsed_capture_complete():
    diag = PhaseCDiagnostics(after_seconds=5)
    diag.trigger("test", timestamp=10)
    diag.finalize(timestamp=16)
    capture = diag.peek_pending(timestamp=16)
    assert capture["incomplete"] is False


def test_phase_c_persistence_limit(tmp_path):
    diag = PhaseCDiagnostics(after_seconds=1)
    for timestamp in (10, 20, 30):
        diag.trigger("test", timestamp=timestamp)
        diag.observe("complete", timestamp=timestamp + 2)

    paths = persist_captures(
        diag, tmp_path, max_captures=1)
    assert len(paths) == 1
    assert diag.peek_pending() is not None

    paths = persist_captures(diag, tmp_path)
    assert len(paths) == 2
    assert diag.peek_pending() is None


def test_gust_shutdown_bypasses_retry_delay(tmp_path):
    diag = GustDiagnostics(
        tmp_path, after_seconds=60, clock=lambda: 110)
    diag.check(55, timestamp=100)
    diag._retry_at = float("inf")

    diag.flush()

    paths = list(tmp_path.glob("gust-*.json"))
    assert len(paths) == 1
    capture = json.loads(paths[0].read_text())
    assert capture["incomplete"] is True
    assert capture["finalized_timestamp"] == 110
    assert not diag.pending


def test_gust_routine_persistence_limit(tmp_path):
    diag = GustDiagnostics(tmp_path)
    diag.pending.extend([{}, {}, {}])
    written = []
    diag._write = lambda capture: written.append(capture) or True

    diag._persist_pending()

    assert len(written) == 1
    assert len(diag.pending) == 2

    diag._persist_pending(force=True, max_captures=None)

    assert len(written) == 3
    assert not diag.pending
