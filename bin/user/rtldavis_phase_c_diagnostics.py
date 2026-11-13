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
                    events = self._active["events"]
                    if len(events) >= self.max_events:
                        events.pop(0)
                        self._active["truncated_events"] += 1
                    events.append(item)
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
                "truncated_events": 0,
                "events": [dict(item) for item in self._history
                           if start <= item["monotonic"] <= now],
            }
            return True

    def peek_pending(self, timestamp=None):
        """Return the oldest completed capture without removing it.

        Persistence happens without holding the producer's lock.
        """
        now = self.clock() if timestamp is None else float(timestamp)
        with self._lock:
            if self._active is not None and now >= self._active["end_monotonic"]:
                self._queue_completed()
            return self._pending[0] if self._pending else None

    def acknowledge(self, capture):
        """Remove a successfully saved capture, if it is still queued."""
        with self._lock:
            for index, pending in enumerate(self._pending):
                if pending is capture:
                    del self._pending[index]
                    return True
        return False

    def drain(self, timestamp=None):
        """Return completed captures to the consumer; never perform file I/O."""
        now = self.clock() if timestamp is None else float(timestamp)
        with self._lock:
            if self._active is not None and now >= self._active["end_monotonic"]:
                self._queue_completed()
            result = list(self._pending)
            self._pending.clear()
        return result


def observe_hardware_tune(diagnostics, tune, frequency, receiver,
                          reason="hop", clock=None):
    """Time a real hardware tune; preserve its result and any exception.

    Called only when Phase C is enabled. The diagnostic event is in-memory.
    """
    timer = clock or time.monotonic
    started = timer()
    error = None
    try:
        return tune(frequency)
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        finished = timer()
        expected = getattr(receiver, "_phase_c_expected_visit", None)
        diagnostics.observe(
            "hardware_tune", timestamp=finished, reason=reason,
            target_frequency_hz=frequency,
            rf_channel=getattr(receiver, "channel", None),
            tune_duration_ms=round((finished - started) * 1000, 3),
            expected_visit_monotonic=expected,
            tune_complete_lead_ms=(round((expected - finished) * 1000, 3)
                                   if expected is not None else None),
            error=error)


def observe_sample_processing(diagnostics, feed, data, arrival,
                              queue_depth=None, clock=None):
    """Measure sample-block age and feed duration without changing feed semantics.

    The USB callback timestamps arrival with time.monotonic(). The radio thread
    invokes this helper only when Phase C is enabled. No IQ bytes are retained.
    """
    timer = clock or time.monotonic
    started = timer()
    error = None
    try:
        return feed(data, arrival)
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        finished = timer()
        diagnostics.observe(
            "sample_processing", timestamp=finished,
            queue_wait_ms=round(max(0.0, started - arrival) * 1000, 3),
            demod_duration_ms=round((finished - started) * 1000, 3),
            completion_age_ms=round(max(0.0, finished - arrival) * 1000, 3),
            queue_depth=queue_depth,
            sample_bytes=len(data),
            error=error)


def persist_captures(diagnostics, directory, timestamp=None, max_files=100):
    """Persist queued captures on the WeeWX loop thread, then acknowledge.

    Failed writes remain queued for retry. Producer never performs disk I/O.
    Retention only touches files with the exact Phase C capture filename shape.
    """
    import json
    import os
    import re
    import tempfile
    import uuid
    from pathlib import Path

    limit = max(1, int(max_files))
    destination = Path(directory)
    paths = []
    first = True
    while True:
        capture = diagnostics.peek_pending(timestamp=timestamp if first else None)
        first = False
        if capture is None:
            break
        destination.mkdir(parents=True, exist_ok=True)
        name = 'phase-c-%s-%s.json' % (
            time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()), uuid.uuid4().hex)
        target = destination / name
        temp_name = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix='.phase-c-', suffix='.tmp',
                                              dir=str(destination))
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump(capture, output, sort_keys=True, indent=2, allow_nan=False)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_name, target)
            temp_name = None
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
        diagnostics.acknowledge(capture)
        paths.append(target)

    # Prune only after successful writes. Never touch other JSON or temp files.
    if paths:
        pattern = re.compile(r'^phase-c-\d{8}T\d{6}Z-[0-9a-f]{12,32}\.json$')
        candidates = sorted(
            (p for p in destination.iterdir() if p.is_file() and pattern.fullmatch(p.name)),
            key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
        for old in candidates[limit:]:
            old.unlink()
    return paths
