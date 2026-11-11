"""Tests for passive receiver wind history."""

import pytest

from user.rtldavis_wind_validation import WindHistory


def test_rolling_maxima():
    history = WindHistory()
    history.observe_wind(12, 100)
    history.observe_wind(8, 500)
    history.observe_wind(4, 750)

    result = history.snapshot(750)

    assert result["rxWindGust5"] == 8
    assert result["rxWindGust10"] == 8
    assert result["rxSampleCount10"] == 2


def test_iss_reference_and_freshness():
    history = WindHistory(iss_max_age_seconds=60)
    history.observe_iss(14, 100)

    assert history.snapshot(150)["issFresh"]
    assert not history.snapshot(161)["issFresh"]
    assert history.snapshot(161)["issWindGust10"] == 14


def test_missing_samples():
    result = WindHistory().snapshot(100)

    assert result["rxWindGust5"] is None
    assert result["rxWindGust10"] is None
    assert result["issWindGust10"] is None
    assert not result["issFresh"]


def test_clock_rollback_resets_history():
    history = WindHistory()
    history.observe_wind(20, 200)
    history.observe_iss(25, 200)
    history.observe_wind(3, 100)

    result = history.snapshot(100)

    assert result["rxWindGust10"] == 3
    assert result["issWindGust10"] is None


def test_invalid_wind_samples_are_ignored():
    history = WindHistory()
    for speed in (-1, float("nan"), float("inf"), None):
        history.observe_wind(speed, 100)

    assert history.snapshot(100)["rxSampleCount10"] == 0


def test_snapshot_does_not_change_observations():
    history = WindHistory()
    history.observe_wind(7.5, 100)
    history.observe_iss(9.0, 100)

    result = history.snapshot(100)

    assert result["rxWindGust10"] == pytest.approx(7.5)
    assert result["issWindGust10"] == pytest.approx(9.0)
