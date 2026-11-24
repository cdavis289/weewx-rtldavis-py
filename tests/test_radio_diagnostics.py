"""Standalone radio health diagnostics without RTL-SDR hardware."""

import logging
import time

from user.rtldavis_receiver import Receiver, Radio
from user.rtldavis import RtldavisDriver


def test_radio_counters_without_ab():
    radio = Radio(Receiver("US", [7]))

    assert radio.ab_diagnostics is None
    assert radio.diagnostic_counts == {
        "usb_dropped_blocks": 0,
        "usb_zero_blocks": 0,
        "usb_stream_restarts": 0,
        "usb_tune_errors": 0,
        "max_queue_depth": 0,
    }


def test_zero_blocks_and_stream_restart_without_ab():
    receiver = Receiver("US", [7])
    radio = Radio(receiver)

    class FakeDongle:
        def configure(self, gain):
            pass

        def tune(self, frequency):
            pass

        def cancel(self):
            pass

        def close(self):
            pass

        def stream(self, receive, synchronous):
            if not synchronous:
                for _ in range(radio.EMPTY_BLOCKS):
                    receive(b"\x00" * 16, time.monotonic())
            return 0

    radio._run_dongle(FakeDongle())

    assert radio.diagnostic_counts["usb_zero_blocks"] == radio.EMPTY_BLOCKS
    assert radio.diagnostic_counts["usb_stream_restarts"] == 1
    assert radio._synchronous


def test_radio_summary_reports_deltas_and_high_water_mark(caplog):
    receiver = Receiver("US", [7])
    radio = Radio(receiver)

    driver = RtldavisDriver.__new__(RtldavisDriver)
    driver._radio = radio
    driver._frame_diagnostics = None
    driver._diagnostic_summary_seconds = 300
    driver._diagnostic_summary_next = 0
    driver._diagnostic_summary_previous = {}

    radio.diagnostic_counts["usb_dropped_blocks"] = 4
    radio.diagnostic_counts["max_queue_depth"] = 12

    with caplog.at_level(logging.INFO):
        driver._maybe_log_diagnostic_summary()

    assert "'usb_dropped_blocks': 4" in caplog.text
    assert "max_queue_depth=12" in caplog.text
    assert "max_queue_depth" not in (
        driver._diagnostic_summary_previous["radio"]
    )

    caplog.clear()
    driver._diagnostic_summary_next = 0
    radio.diagnostic_counts["usb_dropped_blocks"] = 7

    with caplog.at_level(logging.INFO):
        driver._maybe_log_diagnostic_summary()

    assert "'usb_dropped_blocks': 3" in caplog.text
    assert "max_queue_depth=12" in caplog.text
