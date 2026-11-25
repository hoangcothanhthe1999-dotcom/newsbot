"""Canh gác: báo Telegram cho chủ bot khi bot im quá 4 giờ trong giờ chạy (06:00-16:15 VN).

Chạy bởi .github/workflows/watchdog.yml (mỗi giờ). Không chạm vào bot.py, không đọc/ghi state.
Chỉ báo MỘT lần cho mỗi đợt im (cửa sổ 4h-5h30 so với lần chạy gần nhất), tránh báo lặp.
Token/ID không bao giờ in ra log.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

VN = timezone(timedelta(hours=7))
START_H, END_MIN = 6, 16 * 60 + 15  # 06:00 - 16:15
SILENT_AFTER = timedelta(hours=4)
ALERT_UNTIL = timedelta(hours=5, minutes=30)
FAIL_WINDOW = timedelta(minutes=65)  # watchdog chạy mỗi giờ: chỉ báo run lỗi vừa kết thúc trong ~1 giờ qua (không báo lặp)


def decide(now: datetime, last_activity: datetime | None) -> str | None:
    """Trả về nội dung cảnh báo, hoặc None nếu không cần báo.

    last_activity = thời điểm gần nhất bot còn hoạt động (một phiên đang chạy, hoặc vừa kết thúc).
    Mốc tính im lặng không sớm hơn 06:00 hôm nay (ban đêm bot nghỉ là bình thường).
    """
    n = now.astimezone(VN)
    minutes = n.hour * 60 + n.minute
    if not (START_H * 60 <= minutes <= END_MIN):
        return None
    day_start = n.replace(hour=START_H, minute=0, second=0, microsecond=0)
    ref = day_start if last_activity is None else max(last_activity.astimezone(VN), day_start)
    gap = n - ref
    if SILENT_AFTER <= gap < ALERT_UNTIL:
        hrs = gap.total_seconds() / 3600
        when = "chưa có phiên nào hôm nay" if last_activity is None or last_activity.astimezone(VN) < day_start \
            else f"phiên gần nhất {last_activity.astimezone(VN):%H:%M}"
        return f"⚠️ Bot im khoảng {hrs:.1f} giờ trong giờ chạy ({when}). Kiểm tra máy canh/Actions."
    return None


def last_activity_from_runs(runs: list[dict]) -> datetime | None:
    best = None
    for r in runs:
        if r.get("status") != "completed":
            ts = r.get("run_started_at") or r.get("created_at")  # đang chạy/xếp hàng = còn sống
            if r.get("status") == "queued":
                continue
        else:
            if r.get("conclusion") != "success":
                continue
            ts = r.get("updated_at")
        if not ts:
            continue
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if r.get("status") != "completed":
            t = datetime.now(timezone.utc)  # phiên đang chạy: coi là hoạt động ngay bây giờ
        if best is None or t > best:
            best = t
    return best


def failed_runs_alert(now: datetime, runs: list[dict]) -> str | None:
    """Báo run vừa kết thúc với conclusion=failure (vd. bước 'Lưu trạng thái' lỗi → run sau gửi trùng tin, 25/11).

    Không phụ thuộc giờ trong ngày. Chỉ xét run kết thúc trong FAIL_WINDOW gần nhất.
    """
    lines = []
    for r in runs:
        if r.get("status") != "completed" or r.get("conclusion") != "failure" or not r.get("updated_at"):
            continue
        t = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
        if timedelta(0) <= now - t <= FAIL_WINDOW:
            lines.append(f"#{r.get('run_number', '?')} lúc {t.astimezone(VN):%H:%M}: {r.get('html_url', '')}")
    if not lines:
        return None
    return ("❌ Run bot lỗi (xem log; nếu lỗi ở bước lưu state thì run kế tiếp có thể gửi trùng tin):\n"
            + "\n".join(lines))


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main() -> int:
    repo, gh_token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    data = _get(f"https://api.github.com/repos/{repo}/actions/workflows/newsbot.yml/runs?per_page=20", gh_token)
    last = last_activity_from_runs(data.get("workflow_runs", []))
    now = datetime.now(timezone.utc)
    parts = [m for m in (decide(now, last), failed_runs_alert(now, data.get("workflow_runs", []))) if m]
    msg = "\n\n".join(parts)
    if not msg:
        print("Bot bình thường (hoặc ngoài giờ/ngoài cửa sổ báo): không gửi gì.")
        return 0
    tg = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    with open("state.json", encoding="utf-8") as f:
        owner = json.load(f).get("owner")
    if not tg or not owner:
        print("::error::Thiếu token hoặc owner, không gửi được cảnh báo.")
        return 1
    body = urllib.parse.urlencode({"chat_id": owner, "text": msg}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{tg}/sendMessage", data=body, timeout=30):
        pass
    print("Đã gửi cảnh báo bot im.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
