"""Báo cáo cuối ngày tự động (không gọi AI): chạy check_run.py --day, chỉ gửi Telegram khi có điều bất thường.

Chạy bởi .github/workflows/daily-report.yml. Token/ID không bao giờ in ra log.
Bất thường = dòng 🔴 (Traceback, gửi trùng, gửi quá nhiều), dòng 🚩 (cờ RUNSUM), hoặc ngày gửi 0 tin.
Nguồn lỗi kéo dài (🟡) KHÔNG gửi Telegram: chỉ nằm trong báo cáo để C xử lý, tránh ồn.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MAX_CHARS = 900
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def report_day(now: datetime | None = None) -> str:
    """Report date in Vietnam time; naive datetimes are interpreted as VN wall time."""
    if now is None:
        now = datetime.now(timezone.utc)
    local_now = now.replace(tzinfo=VN_TZ) if now.tzinfo is None else now.astimezone(VN_TZ)
    if (local_now.hour, local_now.minute) < (16, 15):
        local_now -= timedelta(days=1)
    return local_now.date().isoformat()


def build_alert(report: str) -> str | None:
    """Từ bản tóm tắt ngày, trả về nội dung cảnh báo (hoặc None nếu ngày bình thường)."""
    lines = [ln for ln in report.splitlines() if ln.strip()]
    if not lines:
        return "⚠️ Báo cáo cuối ngày trống: không có phiên nào hoặc không đọc được log."
    bad = [ln for ln in lines if ln.lstrip().startswith(("🔴", "🚩"))]
    m = re.search(r"gửi (\d+) tin", lines[0])
    if m and int(m.group(1)) == 0:
        bad.insert(0, lines[0])
    if not bad:
        return None
    return ("⚠️ Cuối ngày: có bất thường\n" + "\n".join(bad))[:MAX_CHARS]


def main() -> int:
    day = report_day()
    out = subprocess.run([sys.executable, "check_run.py", "--day", day], capture_output=True, text=True, timeout=600, check=False)
    report = out.stdout.strip()
    print(report or "(báo cáo trống)")
    if out.returncode != 0:
        print(f"::warning::check_run.py thoát mã {out.returncode}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("```\n" + report + "\n```\n")
    msg = build_alert(report)
    if not msg:
        print("Ngày bình thường: không gửi Telegram.")
        return 0
    tg = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    try:
        with open("state.json", encoding="utf-8") as f:
            owner = json.load(f).get("owner")
    except (OSError, ValueError):
        owner = None
    if not tg or not owner:
        print("::error::Thiếu token hoặc owner, không gửi được cảnh báo.")
        return 1
    body = urllib.parse.urlencode({"chat_id": owner, "text": msg}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{tg}/sendMessage", data=body, timeout=30):
        pass
    print("Đã gửi cảnh báo cuối ngày.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
