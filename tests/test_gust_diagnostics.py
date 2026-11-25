"""Unit tests for the optional gust evidence collector."""
import json

from user.rtldavis_gust_diagnostics import GustDiagnostics


def test_normal_gust_is_not_flagged(tmp_path):
    diag = GustDiagnostics(tmp_path, after_seconds=0)
    diag.observe(bytes.fromhex("9000000b00100000"), timestamp=10)
    assert not diag.check(11, 5, timestamp=10)
    assert list(tmp_path.iterdir()) == []


def test_absolute_gust_retains_payload(tmp_path):
    diag = GustDiagnostics(tmp_path, after_seconds=0)
    raw = bytes.fromhex("9000004600100000")
    diag.observe(raw, timestamp=10, frequency_offset=123)
    assert diag.check(70, 5, timestamp=10)
    saved = json.loads(next(tmp_path.glob("gust-*.json")).read_text())
    assert saved["reasons"] == ["absolute", "ratio"]
    assert saved["frames"][0]["payload_hex"] == raw.hex()
    assert saved["frames"][0]["frequency_offset"] == 123


def test_ratio_trigger(tmp_path):
    diag = GustDiagnostics(tmp_path, after_seconds=0)
    assert diag.check(30, 2, timestamp=10)
    saved = json.loads(next(tmp_path.glob("gust-*.json")).read_text())
    assert saved["reasons"] == ["ratio"]


def test_post_trigger_frames_and_retention(tmp_path):
    diag = GustDiagnostics(tmp_path, before_seconds=5, after_seconds=2, max_files=1)
    diag.observe(b"before", timestamp=10)
    assert diag.check(60, timestamp=11)
    diag.observe(b"after", timestamp=12)
    diag.observe(b"next", timestamp=14)
    saved = json.loads(next(tmp_path.glob("gust-*.json")).read_text())
    assert [f["payload_hex"] for f in saved["frames"]] == [
        b"before".hex(), b"after".hex()]
    assert diag.check(60, timestamp=20)
    diag.flush()
    assert len(list(tmp_path.glob("gust-*.json"))) == 1


def test_write_failure_does_not_raise(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    diag = GustDiagnostics(blocked, after_seconds=0)
    assert diag.check(70, timestamp=10)


def test_overlapping_triggers_merge_and_extend(tmp_path):
    diag = GustDiagnostics(tmp_path, before_seconds=300, after_seconds=60)
    diag.observe(b"first", timestamp=100)
    assert diag.check(70, timestamp=100, source="type9")
    diag.observe(b"middle", timestamp=130)
    assert diag.check(80, timestamp=130, source="type9")
    diag.tick(161)
    assert not list(tmp_path.glob("gust-*.json"))
    diag.observe(b"last", timestamp=175)
    diag.tick(191)
    saved = json.loads(next(tmp_path.glob("gust-*.json")).read_text())
    assert len(saved["events"]) == 2
    assert saved["gust_mph"] == 80
    assert [f["payload_hex"] for f in saved["frames"]] == [
        b"first".hex(), b"middle".hex(), b"last".hex()]


def test_idle_tick_finalizes_without_new_frames(tmp_path):
    diag = GustDiagnostics(tmp_path, after_seconds=60)
    assert diag.check(70, timestamp=100)
    diag.tick(160)
    assert not list(tmp_path.glob("gust-*.json"))
    diag.tick(161)
    assert len(list(tmp_path.glob("gust-*.json"))) == 1


def test_history_is_count_bounded(tmp_path):
    diag = GustDiagnostics(
        tmp_path, before_seconds=300, max_frames=5)

    for i in range(20):
        diag.observe(bytes([i]), timestamp=i)

    assert len(diag.history) == 5
    assert diag.history[0]["timestamp"] == 15


def test_capture_frames_are_bounded(tmp_path):
    diag = GustDiagnostics(
        tmp_path, max_frames=3, after_seconds=60)

    diag.observe(b"before", timestamp=10)
    assert diag.check(70, timestamp=11)

    for i in range(10):
        diag.observe(bytes([i]), timestamp=12 + i)

    diag.flush()

    saved = json.loads(
        next(tmp_path.glob("gust-*.json")).read_text())

    assert len(saved["frames"]) == 3
    assert saved["truncated_frames"] == 8


def test_repeated_triggers_have_hard_deadline(tmp_path):
    diag = GustDiagnostics(
        tmp_path, after_seconds=60,
        max_capture_seconds=180)

    assert diag.check(70, timestamp=100)

    for timestamp in (150, 200, 250):
        assert diag.check(80, timestamp=timestamp)

    assert diag.active["until"] == 280

    diag.tick(281)

    assert diag.active is None
    assert len(list(tmp_path.glob("gust-*.json"))) == 1


def test_anomaly_events_are_bounded(tmp_path):
    diag = GustDiagnostics(
        tmp_path, after_seconds=60, max_events=3)

    for i in range(10):
        assert diag.check(70 + i, timestamp=100 + i)

    diag.flush()

    saved = json.loads(
        next(tmp_path.glob("gust-*.json")).read_text())

    assert len(saved["events"]) == 3
    assert saved["truncated_events"] == 7
    assert saved["gust_mph"] == 79


def test_failed_writes_are_retained_for_retry(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")

    diag = GustDiagnostics(blocked, after_seconds=0, retry_seconds=0)

    assert diag.check(70, timestamp=100)
    assert len(diag.pending) == 1
    assert diag.write_failures >= 1

    blocked.unlink()
    blocked.mkdir()

    diag.tick(101)

    assert len(diag.pending) == 0
    assert len(list(blocked.glob("gust-*.json"))) == 1


def test_failed_write_queue_is_bounded(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")

    diag = GustDiagnostics(
        blocked, after_seconds=0, max_pending=2)

    for i in range(5):
        assert diag.check(70, timestamp=100 + i)

    assert len(diag.pending) == 2
    assert diag.dropped_captures == 3


def test_atomic_write_failure_leaves_no_partial_capture(
        tmp_path, monkeypatch):
    import user.rtldavis_gust_diagnostics as gust_module

    original_replace = gust_module.os.replace

    def fail_replace(*args, **kwargs):
        raise OSError("simulated atomic replacement failure")

    monkeypatch.setattr(
        gust_module.os, "replace", fail_replace)

    diag = GustDiagnostics(tmp_path, after_seconds=0, retry_seconds=0)
    assert diag.check(70, timestamp=100)

    assert len(diag.pending) == 1
    assert not list(tmp_path.glob("gust-*.json"))
    assert not list(tmp_path.glob(".gust-*.tmp"))

    monkeypatch.setattr(
        gust_module.os, "replace", original_replace)

    diag.tick(101)

    assert len(diag.pending) == 0
    assert len(list(tmp_path.glob("gust-*.json"))) == 1


def test_retention_preserves_unrelated_files(tmp_path):
    unrelated = tmp_path / "gust-manual.json"
    unrelated.write_text("preserve")

    diag = GustDiagnostics(
        tmp_path, after_seconds=0, max_files=1)

    assert diag.check(70, timestamp=100)
    assert diag.check(80, timestamp=101)

    assert unrelated.read_text() == "preserve"

    generated = [
        path for path in tmp_path.glob("gust-*.json")
        if path != unrelated
    ]

    assert len(generated) == 1


def test_failed_write_retry_is_throttled(
        tmp_path, monkeypatch):
    import user.rtldavis_gust_diagnostics as gust_module

    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")

    now = [100.0]

    monkeypatch.setattr(
        gust_module.time, "monotonic",
        lambda: now[0])

    diag = GustDiagnostics(
        blocked, after_seconds=0, retry_seconds=30)

    assert diag.check(70, timestamp=100)
    assert diag.write_failures == 1

    now[0] = 129
    diag.tick(129)

    assert diag.write_failures == 1
    assert len(diag.pending) == 1

    blocked.unlink()
    blocked.mkdir()

    now[0] = 130
    diag.tick(130)

    assert len(diag.pending) == 0
    assert len(list(blocked.glob("gust-*.json"))) == 1


def test_fractional_average_preserves_ratio_threshold(tmp_path):
    diag = GustDiagnostics(tmp_path, after_seconds=0)

    # 25 / 5.0625 is below the 5x threshold.
    assert not diag.check(25.0, 5.0625, timestamp=100)

    # 25 / 4.9375 is above the 5x threshold.
    assert diag.check(25.0, 4.9375, timestamp=101)

    saved = json.loads(
        next(tmp_path.glob("gust-*.json")).read_text())

    assert saved["average_mph"] == 4.9375
    assert saved["reasons"] == ["ratio"]


def test_fractional_gust_preserves_absolute_threshold(tmp_path):
    diag = GustDiagnostics(tmp_path, after_seconds=0)

    assert not diag.check(49.9375, timestamp=100)
    assert diag.check(50.0625, timestamp=101)

    saved = json.loads(
        next(tmp_path.glob("gust-*.json")).read_text())

    assert saved["gust_mph"] == 50.0625
    assert saved["reasons"] == ["absolute"]


def test_fractional_gust_preserves_ratio_minimum(tmp_path):
    diag = GustDiagnostics(tmp_path, after_seconds=0)

    assert not diag.check(24.9375, 1.0, timestamp=100)
    assert diag.check(25.0625, 1.0, timestamp=101)

    saved = json.loads(
        next(tmp_path.glob("gust-*.json")).read_text())

    assert saved["gust_mph"] == 25.0625
    assert saved["reasons"] == ["ratio"]
