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
