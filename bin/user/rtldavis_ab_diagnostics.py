"""Opt-in, observation-only A/B crossover telemetry for the RTL-Davis receiver.

Events use UTC wall-clock timestamps; internal timing uses monotonic seconds.
Only transitions and periodic aggregates are persisted, never raw IQ samples.
Diagnostic I/O errors are logged without affecting reception.
"""
import csv
import datetime
import json
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

COLUMNS = ("timestamp_utc", "phase", "host", "dongle_id", "accepted",
           "missed_predictions", "sync_losses", "sync_acquired",
           "usb_dropped_blocks", "usb_zero_blocks", "usb_stream_restarts",
           "usb_tune_errors", "usb_mode", "max_queue_depth",
           "frequency_offset_hz", "seconds_since_last_frame",
           "syncing", "locked")


class ABDiagnostics:
    """Small, bounded and optional JSONL/CSV writer.

    The receiver calls event() only for meaningful state changes. snapshot()
    is invoked outside the RF processing thread from the WeeWX loop.
    """

    def __init__(self, directory, phase, host, dongle_id, manifest=None,
                 clock=None, max_event_bytes=2_000_000):
        self.directory = Path(directory)
        self.phase = str(phase)
        self.host = str(host)
        self.dongle_id = str(dongle_id)
        self.clock = clock or time.time
        self.max_event_bytes = max(1024, int(max_event_bytes))
        self._lock = threading.Lock()
        self._previous = {}
        self._last_frame_monotonic = None
        self._summary_path = self.directory / "ab-summary.csv"
        self._events_path = self.directory / "ab-events.jsonl"
        self._manifest_path = self.directory / "ab-manifest.json"
        self._enabled = True
        self._write_manifest(manifest or {})

    @staticmethod
    def _utc(ts):
        return datetime.datetime.fromtimestamp(
            ts, datetime.timezone.utc).isoformat()

    def _write_manifest(self, details):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            # A test manifest is per-run: make the timestamp part of its identity.
            metadata = {"created_utc": self._utc(self.clock()),
                        "phase": self.phase, "host": self.host,
                        "dongle_id": self.dongle_id}
            metadata.update(details)
            with self._manifest_path.open("w", encoding="utf-8") as output:
                json.dump(metadata, output, indent=2, sort_keys=True)
                output.write("\n")
        except (OSError, ValueError, TypeError):
            log.exception("Cannot write A/B diagnostic manifest")
            self._enabled = False

    def event(self, name, **fields):
        if not self._enabled:
            return
        item = {"timestamp_utc": self._utc(self.clock()),
                "event": name, "phase": self.phase, "host": self.host,
                "dongle_id": self.dongle_id}
        item.update(fields)
        try:
            with self._lock:
                self.directory.mkdir(parents=True, exist_ok=True)
                # Rotate one bounded backup so event logging cannot grow without limit.
                if (self._events_path.exists() and
                        self._events_path.stat().st_size >= self.max_event_bytes):
                    self._events_path.replace(
                        self.directory / "ab-events.previous.jsonl")
                with self._events_path.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(item, sort_keys=True) + "\n")
        except (OSError, ValueError, TypeError):
            log.exception("A/B diagnostic event write failed")

    def snapshot(self, receiver, radio, monotonic_now=None):
        """Persist five-minute deltas; no changes to receiver state."""
        if not self._enabled:
            return
        now = time.monotonic() if monotonic_now is None else monotonic_now
        counts = dict(receiver.diagnostic_counts)
        counts.update(getattr(radio, "ab_counters", {}))
        keys = ("accepted", "missed_predictions", "sync_losses", "sync_acquired",
                "usb_dropped_blocks", "usb_zero_blocks", "usb_stream_restarts",
                "usb_tune_errors")
        previous = self._previous
        row = {"timestamp_utc": self._utc(self.clock()), "phase": self.phase,
               "host": self.host, "dongle_id": self.dongle_id}
        row.update({key: counts.get(key, 0) - previous.get(key, 0)
                    for key in keys})
        row["usb_mode"] = ("sync" if getattr(radio, "_synchronous", False)
                           else "async")
        row["max_queue_depth"] = counts.get("max_queue_depth", 0)
        row["frequency_offset_hz"] = round(receiver.offset, 1)
        last = getattr(receiver, "_ab_last_frame", None)
        row["seconds_since_last_frame"] = (round(now - last, 2)
                                             if last is not None else "")
        row["syncing"] = bool(getattr(receiver, "_syncing", True))
        row["locked"] = bool(receiver.locked)
        try:
            with self._lock:
                self.directory.mkdir(parents=True, exist_ok=True)
                header = (not self._summary_path.exists() or
                          self._summary_path.stat().st_size == 0)
                with self._summary_path.open("a", encoding="utf-8",
                                             newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=COLUMNS)
                    if header:
                        writer.writeheader()
                    writer.writerow(row)
            self._previous = counts
        except (OSError, ValueError, TypeError):
            log.exception("A/B diagnostic summary write failed")
