"""CRC attempt counters are diagnostic-only and do not alter decoding."""
import numpy
from user.rtldavis_dsp import _decode


def test_crc_attempts_are_counted():
    # Eight zero bytes have a valid CRC but are intentionally discarded.
    symbols = numpy.ones(80)
    counts = {"crc_failed_attempts": 0, "crc_valid_attempts": 0,
              "zero_payload_attempts": 0}
    assert _decode(symbols, [0.0], counts) is None
    assert counts["zero_payload_attempts"] == 1


def test_crc_failed_attempts_are_counted():
    symbols = numpy.ones(80)
    symbols[16] = -1
    counts = {"crc_failed_attempts": 0, "crc_valid_attempts": 0,
              "zero_payload_attempts": 0}
    assert _decode(symbols, [0.0], counts) is None
    assert counts["crc_failed_attempts"] == 1
