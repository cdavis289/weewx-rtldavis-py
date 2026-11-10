"""Opt-in, non-intrusive evidence capture for suspicious Davis wind gusts.

This module does not modify, filter, or validate weather observations.
"""
from collections import deque
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time

LOG = logging.getLogger(__name__)


class GustDiagnostics:
    """Keep a bounded history of decoded RF frames and write anomaly evidence."""

    def __init__(self, directory, absolute_mph=50.0, ratio=5.0,
                 ratio_minimum_mph=25.0, before_seconds=300,
                 after_seconds=60, max_files=100, clock=None):
        self.directory = Path(directory)
        self.absolute_mph = float(absolute_mph)
        self.ratio = float(ratio)
        self.ratio_minimum_mph = float(ratio_minimum_mph)
        self.before_seconds = max(0.0, float(before_seconds))
        self.after_seconds = max(0.0, float(after_seconds))
        self.max_files = max(1, int(max_files))
        self.clock = clock or time.time
        self.history = deque()
        self.pending = []
        self.sequence = 0

    def observe(self, payload, timestamp=None, **metadata):
        """Record a decoded eight-byte payload; never retain IQ samples."""
        now = float(self.clock() if timestamp is None else timestamp)
        item = {
            "timestamp": now,
            "payload_hex": bytes(payload).hex(),
            "channel": (payload[0] & 7) + 1 if payload else None,
            "message_type": payload[0] >> 4 if payload else None,
        }
        item.update(metadata)
        self.history.append(item)
        cutoff = now - self.before_seconds
        while self.history and self.history[0]["timestamp"] < cutoff:
            self.history.popleft()
        for capture in list(self.pending):
            if now <= capture["until"]:
                capture["frames"].append(dict(item))
            else:
                self._write(capture)
                self.pending.remove(capture)

    def check(self, gust_mph, average_mph=None, timestamp=None, **metadata):
        """Trigger capture for an absolute or relative gust anomaly.

        Relative detection requires a positive average to avoid division by zero.
        An absolute trigger is independent of the average.
        """
        if gust_mph is None:
            return False
        gust = float(gust_mph)
        avg = None if average_mph is None else float(average_mph)
        absolute = gust >= self.absolute_mph
        relative = (avg is not None and avg > 0
                    and gust >= self.ratio_minimum_mph
                    and gust / avg >= self.ratio)
        if not (absolute or relative):
            return False
        now = float(self.clock() if timestamp is None else timestamp)
        capture = {
            "timestamp": now,
            "until": now + self.after_seconds,
            "gust_mph": gust,
            "average_mph": avg,
            "reasons": [reason for reason, enabled in (
                ("absolute", absolute), ("ratio", relative)) if enabled],
            "metadata": metadata,
            "frames": [dict(item) for item in self.history
                       if now - self.before_seconds <= item["timestamp"] <= now],
        }
        if self.after_seconds == 0:
            self._write(capture)
        else:
            self.pending.append(capture)
        return True

    def flush(self):
        """Persist pending captures, including incomplete post-trigger windows."""
        for capture in self.pending:
            self._write(capture)
        self.pending.clear()

    def _write(self, capture):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.sequence += 1
            stamp = datetime.fromtimestamp(
                capture["timestamp"], tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            path = self.directory / ("gust-%s-%06d.json" % (stamp, self.sequence))
            with path.open("x", encoding="utf-8") as stream:
                json.dump(capture, stream, sort_keys=True, default=str)
                stream.write("\n")
            files = sorted(self.directory.glob("gust-*.json"),
                           key=lambda entry: (entry.stat().st_mtime_ns, entry.name))
            for old in files[:-self.max_files]:
                old.unlink()
        except OSError:
            LOG.exception("Unable to persist gust diagnostic capture")
