import logging
from user import rtldavis as rtl
from user import rtldavis_receiver

def test_disabled(monkeypatch):
    monkeypatch.setattr(rtldavis_receiver.Radio, "start", lambda self: None)
    d = rtl.RtldavisDriver(None, {"Rtldavis": {"wind_validation_enabled": "false"}})
    assert d._wind_summary_next is None
    d._maybe_log_wind_summary()

def test_periodic_summary(monkeypatch, caplog):
    clock = [100.0]
    monkeypatch.setattr(rtl.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(rtldavis_receiver.Radio, "start", lambda self: None)
    d = rtl.RtldavisDriver(None, {"Rtldavis": {"wind_validation_enabled": "true", "wind_validation_summary_seconds": "60"}})
    d._wind_history.observe_wind(8, 100)
    d._wind_history.observe_iss(11, 100)
    with caplog.at_level(logging.INFO):
        clock[0] = 159
        d._maybe_log_wind_summary()
        assert not any("Wind validation rx5=" in r.message for r in caplog.records)
        clock[0] = 160
        d._maybe_log_wind_summary()
        messages = [r.message for r in caplog.records if "Wind validation rx5=" in r.message]
        assert len(messages) == 1
        assert "rx5=8.0 mph" in messages[0]
        assert "tx10=11.0 mph" in messages[0]
        d._maybe_log_wind_summary()
        assert len([r for r in caplog.records if "Wind validation rx5=" in r.message]) == 1
