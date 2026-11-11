"""Driver integration tests for optional passive wind validation."""

from types import SimpleNamespace

import pytest

from user import rtldavis as rtl
from user import rtldavis_receiver


def make_driver(monkeypatch, enabled=False):
    monkeypatch.setattr(
        rtldavis_receiver.Radio, 'start', lambda self: None
    )
    return rtl.RtldavisDriver(None, {
        'Rtldavis': {
            'wind_validation_enabled': str(enabled).lower()
        }
    })


def make_frame(message, speed, timestamp, channel=1, gust=0):
    payload = bytearray(8)
    payload[0] = (message << 4) | (channel - 1)
    payload[1] = speed
    payload[2] = 128
    if message == 9:
        payload[3] = gust
        payload[5] = 0x10

    return SimpleNamespace(
        payload=bytes(payload),
        time=timestamp,
        counts=(1, 1, 1, 1),
        transmitter=channel - 1,
        channel=1,
        frequency_offset=0,
    )


def test_disabled_by_default(monkeypatch):
    driver = make_driver(monkeypatch)
    assert driver._wind_history is None


def test_wind_history_records_decoded_speed(monkeypatch):
    driver = make_driver(monkeypatch, enabled=True)

    frame = make_frame(8, 7, 100)
    packet = driver._frame_to_packet(frame)
    result = driver._wind_history.snapshot(100)

    assert result["rxSampleCount10"] == 1
    assert result["rxWindGust10"] == pytest.approx(
        packet["windSpeed"] / rtl.MPH_TO_MPS
    )


def test_iss_gust_recorded_without_packet_changes(monkeypatch):
    driver = make_driver(monkeypatch, enabled=True)

    frame = make_frame(9, 3, 100, gust=11)
    packet = driver._frame_to_packet(frame)
    result = driver._wind_history.snapshot(100)

    assert result["issWindGust10"] == 11
    assert result["rxSampleCount10"] == 1
    assert packet["windGust"] == pytest.approx(
        11 * rtl.MPH_TO_MPS
    )


def test_separate_anemometer_channel(monkeypatch):
    driver = make_driver(monkeypatch, enabled=True)
    driver.channels["anemometer"] = 2
    driver.channels["wind_channel"] = 2

    driver._frame_to_packet(make_frame(8, 30, 100, channel=1))
    result = driver._wind_history.snapshot(100)
    assert result["rxSampleCount10"] == 0

    driver._frame_to_packet(make_frame(8, 5, 101, channel=2))
    result = driver._wind_history.snapshot(101)
    assert result["rxSampleCount10"] == 1


def test_disabled_and_enabled_packets_match(monkeypatch):
    disabled = make_driver(monkeypatch)
    enabled = make_driver(monkeypatch, enabled=True)

    frame = make_frame(9, 3, 100, gust=11)

    assert disabled._frame_to_packet(frame) == enabled._frame_to_packet(frame)
