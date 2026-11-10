"""A/B telemetry must not change receiver behavior."""
import csv
import json
from types import SimpleNamespace
from user.rtldavis_ab_diagnostics import ABDiagnostics


def test_ab_events_and_delta_snapshots(tmp_path):
    clock = lambda: 1000000000
    diag = ABDiagnostics(tmp_path, "A", "odysseyblue", "00000433",
                         {"receiver": "python"}, clock=clock)
    diag.event("synchronization_lost", missed_frames=52)
    saved = [json.loads(line) for line in
             (tmp_path / "ab-events.jsonl").read_text().splitlines()]
    assert saved[0]["missed_frames"] == 52
    manifest = json.loads((tmp_path / "ab-manifest.json").read_text())
    assert manifest["dongle_id"] == "00000433"

    receiver = SimpleNamespace(diagnostic_counts={"accepted": 10,
                                                    "missed_predictions": 2},
                               offset=1250, locked=True, _syncing=False,
                               _ab_last_frame=95)
    radio = SimpleNamespace(ab_counters={"usb_dropped_blocks": 1,
                                         "max_queue_depth": 3},
                            _synchronous=False)
    diag.snapshot(receiver, radio, monotonic_now=100)
    receiver.diagnostic_counts["accepted"] = 13
    diag.snapshot(receiver, radio, monotonic_now=105)
    with (tmp_path / "ab-summary.csv").open() as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 2
    assert [int(row["accepted"]) for row in rows] == [10, 3]
    assert [int(row["usb_dropped_blocks"]) for row in rows] == [1, 0]
    assert rows[0]["seconds_since_last_frame"] == "5"


def test_rotates_events(tmp_path):
    diag = ABDiagnostics(tmp_path, "B", "host", "dongle",
                         max_event_bytes=1024)
    for index in range(25):
        diag.event("missed_frame_streak", index=index)
    assert (tmp_path / "ab-events.previous.jsonl").exists()
    assert (tmp_path / "ab-events.jsonl").exists()
