# RTL-SDR A/B crossover test

This procedure is intended to identify whether intermittent Python receiver
synchronization losses follow a **dongle**, a **receiver implementation**, a
**host/USB/RF path**, or shared interference. An association is not proof of
cause.

## Before swapping anything

1. Run the same Python commit in both phases. Keep Go receiver version unchanged.
2. Enable `ab_diagnostics_enabled = true` only for the Python driver. The
   existing diagnostic feature is disabled by default.
3. Use a **persistent, writable** `ab_diagnostics_path` mounted from the host.
   Each phase should have a **separate directory**, because filenames are reused.
4. Record the actual physical dongle serial number (not only a device index),
   host, USB port, hub/cable, antenna, coax, gain setting, driver commit,
   librtlsdr version, and the assigned Go/Python receiver.
5. Capture a baseline before disconnecting hardware. Record test start/end and
   any maintenance downtime in Pacific time and UTC.
6. Align the Go and Python five-minute archive timestamps and keep both
   receivers observing the same Davis transmitter.

### Suggested Python configuration

```ini
[Rtldavis]
    ab_diagnostics_enabled = true
    ab_diagnostics_path = /data/ab-diagnostics/phase-a
    ab_phase = A
    ab_dongle_id = SERIAL_FROM_RTL_EEPROM
    ab_host = odysseyblue
    ab_diagnostic_summary_seconds = 300
```

Use distinct path and phase B labels after the swap. The manifest stores the
configured device selector, host, phase, Python version, and RF configuration.
Manually record the USB port and antenna path in the test notes.

## Crossover design

| Phase | Go | Python |
| --- | --- | --- |
| A | Dongle A | Dongle B |
| B | Dongle B | Dongle A |
| A2 (optional) | Dongle A | Dongle B |

Keep USB hosts, cables, antenna paths and software assignments fixed where
possible, moving **only** the dongle hardware. If moving a dongle also moves
its cable or antenna, document that confounder explicitly. Use dongle serial
numbers, not USB enumeration order, to select devices. Compare similar-length
windows; 4–7 days per phase is a starting point, not a guarantee of enough
synchronization failures for inference.

## Files and interpretation

- `ab-manifest.json`: phase and runtime metadata. Do not reuse one directory
  for separate test runs; this file is overwritten at start.
- `ab-events.jsonl`: state transitions: synchronization loss and recovery,
  missed-frame streak thresholds, probation failure, loss of frequency lock,
  USB read restarts and sample delivery problems.
- `ab-events.previous.jsonl`: one rotated events file.
- `ab-summary.csv`: **interval deltas**, including accepted and missed
  predictions, event counts, USB block drops and zero blocks; instantaneous
  frequency offset, lock state, queue high-water mark and seconds since
  successful frame. The first row is since receiver start.
- Existing WeeWX `rxCheckPercent`: independent reception-completeness metric.
  Do not interpret demodulator threshold attempts as independent RF packets.

The diagnostic timestamps use UTC. Receiver scheduling measures elapsed time
with a monotonic clock. Events are deliberately sparse; no IQ capture, signal
strength calibration, or per-frame logging is provided.

### How to investigate an outage

Compare the time of a `synchronization_lost` event with a preceding series of
missed predictions. Examine the learned frequency offset, queue high-water
mark, zero-sample/dropped-block counts, and receiver restarts. Check whether
both implementations lost reception simultaneously. Be careful: the new A/B
telemetry is Python-only unless comparable Go instrumentation is added.
Compare matched `rxCheckPercent` and event rates per observation-hour; do
not compare unlike counters.

## Safeguards

All A/B diagnostics are **observation-only** and off by default. None of the
frame decoding, frequency correction, hopping, timeout thresholds, and WeeWX
weather observations are modified by the A/B recorder. Do not modify these
parameters between phases. Telemetry is best-effort and should not interrupt
weather recording. If disk writes are too slow, disable the feature.
