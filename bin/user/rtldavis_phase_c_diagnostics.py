"""Passive, bounded Phase C receiver event capture.

The producer thread only appends small records in memory. Completed captures
are drained by a consumer (the WeeWX loop), which owns persistence.
"""
from collections import deque
import threading
import time


class PhaseCDiagnostics:
    def __init__(self, before_seconds=60, after_seconds=60,
                 max_events=4096, max_pending=8, clock=None):
        self.before_seconds = max(0.0, float(before_seconds))
        self.after_seconds = max(0.0, float(after_seconds))
        self.max_events = max(1, int(max_events))
        self.max_pending = max(1, int(max_pending))
        self.clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._history = deque(maxlen=self.max_events)
        self._active = None
        self._pending = deque(maxlen=self.max_pending)
        self.dropped_captures = 0

    def _queue_completed(self):
        if self._active is None:
            return
        if len(self._pending) == self.max_pending:
            self.dropped_captures += 1
        self._pending.append(self._active)
        self._active = None

    def observe(self, event, timestamp=None, **fields):
        """Record one passive event; no disk I/O or receiver mutations."""
        now = self.clock() if timestamp is None else float(timestamp)
        item = {"monotonic": now, "event": str(event), **fields}
        with self._lock:
            self._history.append(item)
            cutoff = now - self.before_seconds
            while self._history and self._history[0]["monotonic"] < cutoff:
                self._history.popleft()
            if self._active is not None:
                if now <= self._active["end_monotonic"]:
                    self._active["events"].append(item)
                else:
                    self._queue_completed()
        return item

    def trigger(self, reason, timestamp=None, **fields):
        """Start one capture; repeated triggers don't discard an active capture."""
        now = self.clock() if timestamp is None else float(timestamp)
        with self._lock:
            if self._active is not None:
                return False
            start = now - self.before_seconds
            self._active = {
                "reason": str(reason), "trigger_monotonic": now,
                "end_monotonic": now + self.after_seconds,
                "trigger_fields": dict(fields),
                "events": [dict(item) for item in self._history
                           if start <= item["monotonic"] <= now],
            }
            return True

    def drain(self, timestamp=None):
        """Return completed captures to the consumer; never perform file I/O."""
        now = self.clock() if timestamp is None else float(timestamp)
        with self._lock:
            if self._active is not None and now >= self._active["end_monotonic"]:
                self._queue_completed()
            result = list(self._pending)
            self._pending.clear()
        return result
