"""Phase C Step 5: bounded automatic failure capture and persistence."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

from user.rtldavis_phase_c_diagnostics import PhaseCDiagnostics, persist_captures


def test_capture_contains_pre_and_post_failure_events():
    recorder = PhaseCDiagnostics(before_seconds=60, after_seconds=60,
                                 clock=lambda: 100.0)
    recorder.observe("before", timestamp=99)
    assert recorder.trigger("sync_lost", timestamp=100, missed_frames=53)
    recorder.observe("after", timestamp=120)
    assert recorder.drain(timestamp=159) == []
    captures = recorder.drain(timestamp=160)
    assert len(captures) == 1
    assert captures[0]["reason"] == "sync_lost"
    assert captures[0]["trigger_fields"]["missed_frames"] == 53
    assert [e["event"] for e in captures[0]["events"]] == ["before", "after"]


def test_capture_events_are_bounded_after_trigger():
    recorder = PhaseCDiagnostics(before_seconds=60, after_seconds=60,
                                 max_events=3, clock=lambda: 0)
    recorder.observe("before", timestamp=0)
    assert recorder.trigger("failure", timestamp=0)
    for index in range(10):
        recorder.observe("block", timestamp=1 + index, index=index)
    capture = recorder.drain(timestamp=60)[0]
    assert len(capture["events"]) == 3
    assert capture["truncated_events"] == 8
    assert [e["index"] for e in capture["events"]] == [7, 8, 9]


def test_persistence_writes_json_only_when_capture_completes(tmp_path):
    recorder = PhaseCDiagnostics(before_seconds=1, after_seconds=2,
                                 clock=lambda: 10)
    recorder.observe("before", timestamp=10)
    recorder.trigger("failure", timestamp=10)
    assert persist_captures(recorder, tmp_path, timestamp=11) == []
    paths = persist_captures(recorder, tmp_path, timestamp=12)
    assert len(paths) == 1
    assert paths[0].parent == tmp_path
    assert json.loads(paths[0].read_text())["reason"] == "failure"
    assert persist_captures(recorder, tmp_path, timestamp=20) == []


def test_repeat_trigger_does_not_replace_active_capture():
    recorder = PhaseCDiagnostics(clock=lambda: 100)
    assert recorder.trigger("first")
    assert not recorder.trigger("second")
    assert recorder.drain(timestamp=160)[0]["reason"] == "first"
