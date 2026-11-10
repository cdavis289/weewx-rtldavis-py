# Development history and rationale

This log records the major changes made to `weewx-rtldavis-py` in 2026,
why they were made, and how they were evaluated. It supplements the
[README](../README.md), [configuration reference](configuration.md),
[A/B crossover test](ab-crossover-test.md), and git history.

## October 21–23: correctness, tests, distribution

- **Signed temperatures, rain spikes and wind:** correct sensor decoding,
  limit corruption, and improve receiver lifecycle handling
  ([commit 39907bd](https://github.com/cdavis289/weewx-rtldavis-py/commit/39907bd77c50333c817c7caf76f3e5734c4434eb)).
- **Combined driver/receiver source and replay tests:** make changes reproducible,
  catch regressions and reduce split-project maintenance
  (commits `670be0b` and `0439773`).
- **ARM64 numerical DSP comparisons:** detect platform-specific decoding
  differences (commit `4e7041e`).
- **WeeWX 5 configuration and package catalog docs:** simplify installation,
  upgrades and compatibility testing (commits `5d50d64` and `20579b5`).

## October 29–30: Python receiver and reliability improvements

- **Replace Go receiver with Python:** move hop scheduling, NumPy
  demodulation and ctypes/librtlsdr into WeeWX; remove separate Go
  executable and build. Added oscillator-frequency search, per-channel
  correction and burst voting
  ([commit 3148acc](https://github.com/cdavis289/weewx-rtldavis-py/commit/3148acc42876bc3015a5b4bddec62d9f1eb7e71d)).
- **Synchronous USB-read fallback:** handle all-zero blocks associated with
  affected librtlsdr/ARM installations (commit `f1cd6ec`).
- **Frame/channel attribution, USB shutdown, frequency search:** associate
  frames with the tuning at capture time; close USB readers safely; avoid
  unconfigured transmitters holding the lock; reset invalid learned
  offsets and restore frequency-error observations
  ([commit 5b741e1](https://github.com/cdavis289/weewx-rtldavis-py/commit/5b741e1ddff834cc03426fea57cdb8f8f8416e34)).
- **Portable dependency installation:** name `rtl-sdr` as the package
  providing the suitable librtlsdr library across Ubuntu/Debian variants.
  Releases: `0.22.0`, `0.22.1`, `0.22.2`.

## November: experimental gust, frame and RF diagnostics

All experimental features are disabled by default and do not alter
weather data, synchronization decisions or frame acceptance.

- **Gust anomaly capture:** detect absolute and relative gust outliers
  and save bounded windows of decoded RF frames as JSON to establish
  whether suspicious gusts originate upstream of WeeWX.
- **Capture grouping and timestamps:** avoid a file per repeated gust
  and preserve archive time separately from diagnostic detection time.
- **Accepted-frame plausibility/duplicate indicators:** observe flags
  without filtering the reported packet.
- **Burst and demodulator counters:** count accepted and suppressed
  bursts and CRC/threshold attempts. Threshold attempts are not
  independent over-the-air transmissions.
- **Periodic RF summaries:** optional five-minute counter deltas.
- **Tests:** the supplied local logs showed 60 then 69 passing tests,
  plus synthetic capture-window and grouping checks. Synthetic tests
  do not establish reliability on live hardware.

## November 7–10: observational Go/Python A/B run

In 1,146 matched five-minute intervals excluding Nov 7 16:30–17:30 PST
maintenance, archive coverage was complete. Mean reception was
99.5585% (Go) versus 99.8466% (Python); 5,713 matched CPU samples
averaged 27.15% (Go) versus 18.93% (Python), a roughly 30.27%
reduction. These are observations with different receiver hardware,
not a controlled same-dongle comparison.

Python still suffered rare synchronization losses. On Nov 10 it logged
channel 8 loss at 07:54:06 and reacquisition at 07:54:50 PST; the 07:55
archive reception was 33% versus 99% for Go. Better mean reception
did not identify why those short losses occurred.

## Next phase: instrumented dongle crossover

- **Purpose:** distinguish dongle hardware, host/USB/RF path and receiver
  implementation contributions to synchronization losses.
- **Added A/B recorder:** opt-in JSONL synchronization/loss/recovery
  events, missed prediction milestones, USB empty/dropped-block
  counters, tuning errors, frequency offset observations, periodic
  CSV deltas and a phase manifest.
- **Preserves controls:** no changes to hop prediction, tuning policy,
  missed-frame thresholds, frame handling, or reported WeeWX data.
- **Limits:** the new telemetry measures the Python receiver only.
  Compare against the Go receiver using common archive metrics and
  timestamps, not counters with different semantics.
- **Procedure:** [A/B crossover test](ab-crossover-test.md).

## Status and verification

Changes on `feature/gust-anomaly-diagnostics` are experimental until
merged, installed and independently confirmed on live dongles.
Keep documentation and the feature branch current as more evidence
is collected. The historical test outputs above were provided by the
maintainer; they should not be mistaken for CI results of later commits.
