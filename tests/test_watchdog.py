from datetime import datetime, timedelta, timezone

import watchdog

VN = timezone(timedelta(hours=7))


def t(h, m=0):
    return datetime(2026, 11, 24, h, m, tzinfo=VN)


def test_quiet_overnight_and_after_end():
    assert watchdog.decide(t(3), None) is None
    assert watchdog.decide(t(17), t(9)) is None


def test_no_alert_when_recent():
    assert watchdog.decide(t(12), t(10, 30)) is None


def test_alert_after_4h_once_window():
    assert watchdog.decide(t(14, 10), t(10, 0)) is not None
    assert watchdog.decide(t(15, 40), t(10, 0)) is None  # quá cửa sổ: không báo lặp


def test_morning_reference_is_6am_not_last_night():
    assert watchdog.decide(t(8), t(23, 0) - timedelta(days=1)) is None
    assert watchdog.decide(t(10, 10), t(23, 0) - timedelta(days=1)) is not None


def test_runs_parse():
    runs = [{"status": "completed", "conclusion": "failure", "updated_at": "2026-11-24T05:00:00Z"},
            {"status": "completed", "conclusion": "success", "updated_at": "2026-11-24T03:00:00Z"}]
    assert watchdog.last_activity_from_runs(runs).hour == 3
