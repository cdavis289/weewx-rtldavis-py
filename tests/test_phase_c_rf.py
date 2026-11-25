"""Phase C RF candidate classification and AFC telemetry; no SDR hardware."""
from types import SimpleNamespace
from user.rtldavis_receiver import Receiver
from user.rtldavis_phase_c_diagnostics import PhaseCDiagnostics


def make_receiver():
    rx = Receiver("US", [7])
    rx.phase_c_diagnostics = PhaseCDiagnostics(clock=lambda: 0)
    rx.start(0.0)
    return rx


def candidate(transmitter=7, frequency_error=25.0, payload=None):
    return SimpleNamespace(payload=payload or bytes([0x80 | transmitter, 1, 2, 3, 4, 5, 6, 7]),
                           frequency_error=frequency_error)


def events(rx, name):
    return [item for item in rx.phase_c_diagnostics._history if item["event"] == name]


def test_accepted_candidate_records_afc_without_changing_frame():
    rx = make_receiver()
    frame = rx._accept(candidate(), 1.0, rx.channel, rx.frequency)
    assert frame is not None
    event = events(rx, "candidate_accepted")[-1]
    assert event["transmitter"] == 8
    assert event["frequency_error_hz"] == 25.0
    assert event["learned_offset_hz"] == frame.frequency_offset
    assert event["global_offset_hz"] == rx.offset
    assert event["measured_offset_hz"] == event["tuned_frequency_hz"] - rx.frequencies[frame.channel] + 25.0


def test_duplicate_candidate_rejected_and_classified():
    rx = make_receiver()
    channel, frequency = rx.channel, rx.frequency
    first = candidate()
    assert rx._accept(first, 1.0, channel, frequency) is not None
    assert rx._accept(first, 1.1, channel, frequency) is None
    assert events(rx, "candidate_rejected")[-1]["reason"] == "burst_identical"
    assert rx.diagnostic_counts["burst_suppressed"] == 1


def test_unconfigured_candidate_classified_without_acceptance():
    rx = make_receiver()
    assert rx._accept(candidate(transmitter=0), 1.0, rx.channel, rx.frequency) is None
    assert events(rx, "candidate_rejected")[-1]["reason"] == "unconfigured_transmitter"
    assert rx.diagnostic_counts["accepted"] == 0


def test_candidate_accounting_is_distinct_from_crc_attempts():
    rx = make_receiver()
    class Demod:
        sample_count = 0
        settled = 0
        diagnostic_counts = {"crc_failed_attempts": 0,
                             "crc_valid_attempts": 0, "zero_payload_attempts": 0}
        def feed(self, raw, shifts):
            self.sample_count += len(raw) // 2
            self.settled = self.sample_count
            self.diagnostic_counts["crc_failed_attempts"] += 8
            self.diagnostic_counts["crc_valid_attempts"] += 3
            return []
    rx._demodulator = Demod()
    rx.feed(b"\x00\x01", 0.01)
    event = events(rx, "demod_candidates")[-1]
    assert event["candidate_bursts"] == 0
    assert event["crc_failed_attempts"] == 8
    assert event["crc_valid_attempts"] == 3
