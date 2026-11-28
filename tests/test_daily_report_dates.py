import json
import subprocess
from datetime import datetime
from unittest.mock import patch

import check_run
import daily_alert


def test_list_day_run_ids_only_includes_newsbot_and_skips_incomplete_records():
    runs = [
        {"id": 3, "name": "NewsBot", "created_at": "2026-11-28T10:00:00Z"},
        {"id": 1, "name": "DailyReport", "created_at": "2026-11-28T10:00:00Z"},
        {"id": 2, "name": "CI", "created_at": "2026-11-28T10:00:00Z"},
        {"id": 4, "name": "Watchdog", "created_at": "2026-11-28T10:00:00Z"},
        {"name": "NewsBot", "created_at": "2026-11-28T10:00:00Z"},
        {"id": 5, "name": "NewsBot"},
    ]
    result = type("Result", (), {"stdout": json.dumps({"workflow_runs": runs}).encode()})()
    with patch.object(check_run.subprocess, "run", return_value=result):
        assert check_run.list_day_run_ids("2026-11-28") == [3]


def test_report_day_cutoff_vietnam_time():
    assert daily_alert.report_day(datetime(2026, 11, 28, 2, 14, tzinfo=daily_alert.VN_TZ)) == "2026-11-27"
    assert daily_alert.report_day(datetime(2026, 11, 28, 16, 14, tzinfo=daily_alert.VN_TZ)) == "2026-11-27"
    assert daily_alert.report_day(datetime(2026, 11, 28, 16, 15, tzinfo=daily_alert.VN_TZ)) == "2026-11-28"
    assert daily_alert.report_day(datetime(2026, 11, 28, 23, 0, tzinfo=daily_alert.VN_TZ)) == "2026-11-28"


def test_report_day_converts_aware_datetime_to_vietnam():
    utc_now = datetime(2026, 11, 28, 9, 15, tzinfo=daily_alert.timezone.utc)
    assert daily_alert.report_day(utc_now) == "2026-11-28"


def test_main_passes_explicit_report_day_without_sending_telegram():
    result = subprocess.CompletedProcess([], 0, stdout="normal report\n", stderr="")
    with patch.object(daily_alert, "report_day", return_value="2026-11-27"), \
            patch.object(daily_alert.subprocess, "run", return_value=result) as run, \
            patch.object(daily_alert.urllib.request, "urlopen") as urlopen:
        assert daily_alert.main() == 0
    assert run.call_args.args[0][-2:] == ["--day", "2026-11-27"]
    urlopen.assert_not_called()


def test_report_day_naive_datetime_uses_vietnam_wall_time():
    assert daily_alert.report_day(datetime(2026, 11, 28, 16, 14)) == "2026-11-27"
    assert daily_alert.report_day(datetime(2026, 11, 28, 16, 15)) == "2026-11-28"


def test_list_day_run_ids_skips_non_dict_and_invalid_payload_records():
    runs = [
        None,
        "not-a-run",
        {"id": 6, "name": "NewsBot", "created_at": 123},
        {"id": None, "name": "NewsBot", "created_at": "2026-11-28T10:00:00Z"},
        {"id": 7, "name": "NewsBot", "created_at": "2026-11-28T10:00:00Z"},
    ]
    result = type("Result", (), {"stdout": json.dumps({"workflow_runs": runs}).encode()})()
    with patch.object(check_run.subprocess, "run", return_value=result):
        assert check_run.list_day_run_ids("2026-11-28") == [7]


def test_list_day_run_ids_returns_empty_for_non_list_workflow_runs():
    result = type("Result", (), {"stdout": json.dumps({"workflow_runs": None}).encode()})()
    with patch.object(check_run.subprocess, "run", return_value=result):
        assert check_run.list_day_run_ids("2026-11-28") == []
