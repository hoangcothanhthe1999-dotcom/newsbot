import daily_alert


def test_normal_day_no_alert():
    rep = "📅 12 phiên; gửi 5 tin; đọc 900 bài\n🟡 Nguồn lỗi kéo dài: A(6/12)\nℹ AI: gemini 20/22 lượt 30s"
    assert daily_alert.build_alert(rep) is None


def test_flag_and_traceback_alert():
    rep = "📅 12 phiên; gửi 5 tin; đọc 900 bài\n🔴 2 phiên có Traceback\n🚩 Cờ: gemini_all_failed×3"
    msg = daily_alert.build_alert(rep)
    assert msg is not None and "Traceback" in msg and "gemini_all_failed" in msg


def test_zero_sent_alert():
    msg = daily_alert.build_alert("📅 10 phiên; gửi 0 tin; đọc 500 bài")
    assert msg is not None and "gửi 0 tin" in msg


def test_empty_report_alert():
    assert daily_alert.build_alert("") is not None


def test_alert_truncated():
    rep = "📅 1 phiên; gửi 3 tin; đọc 1 bài\n" + "\n".join("🔴 " + "x" * 100 for _ in range(30))
    msg = daily_alert.build_alert(rep)
    assert msg is not None and len(msg) <= daily_alert.MAX_CHARS
