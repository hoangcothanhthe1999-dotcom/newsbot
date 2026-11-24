"""Kiểm nhanh 1 run của bot: in tối đa 30 dòng, chỉ phần bất thường. Không gọi AI.

Cách dùng:
  python check_run.py RUN_ID            # lấy log qua gh (cần gh đã đăng nhập), repo mặc định hoangcothanhthe1999-dotcom/newsbot
  python check_run.py --file log.txt    # đọc log đã có sẵn
  Thêm --all để in cả các dòng LEDGER của bài đã gửi.
"""
import io
import json
import re
import subprocess
import sys
import zipfile

REPO = "hoangcothanhthe1999-dotcom/newsbot"
SENT_FLOOD = 15      # gửi nhiều hơn ngưỡng này trong 1 phiên là đáng ngờ
SRC_FAIL_WARN = 15   # số nguồn không đọc được
MAX_LINES = 30


def get_log(run_id):
    jobs = subprocess.run(["gh", "api", f"repos/{REPO}/actions/runs/{run_id}/logs"], capture_output=True, check=True).stdout
    with zipfile.ZipFile(io.BytesIO(jobs)) as z:
        return "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith(".txt"))


def analyse(text, show_all=False):
    out = []
    sums = []
    ledger = []
    for ln in text.splitlines():
        m = re.search(r"RUNSUM (\{.*\})", ln)
        if m:
            try:
                sums.append(json.loads(m.group(1)))
            except ValueError:
                pass
        m = re.search(r"LEDGER\|(.*)", ln)
        if m:
            ledger.append(m.group(1).split("|"))
    if "Traceback" in text:
        out.append("🔴 Có Traceback trong log")
    if not sums:
        out.append("🟡 Không thấy dòng RUNSUM (run cũ hơn bản có sổ trong log, hoặc phiên thoát sớm)")
    for s in sums[-1:]:
        out.append(f"ℹ gửi={s['sent']} AI-loại-lạc-đề={s['ai_offtopic']} AI-trùng={s['ai_dup']} quá-tuổi={s['stale']} nguồn-lỗi={s['src_fail']}/{s['src_total']}")
        if s["sent"] > SENT_FLOOD:
            out.append(f"🔴 Gửi {s['sent']} tin trong 1 phiên (ngưỡng {SENT_FLOOD}): nghi lọt bộ lọc")
        if s["src_fail"] >= SRC_FAIL_WARN:
            out.append(f"🟡 {s['src_fail']} nguồn không đọc được: {', '.join(s['src_fail_names'])}")
        if s.get("ledger_cut"):
            out.append("🟡 Sổ LEDGER bị cắt ở giới hạn, có thể thiếu dòng")
    seen = {}
    for r in ledger:
        if len(r) >= 6 and r[4] == "sent":
            seen[r[0]] = seen.get(r[0], 0) + 1
    dup = [t for t, n in seen.items() if n > 1]
    if dup:
        out.append(f"🔴 Gửi trùng cùng tid: {', '.join(dup[:5])}")
    errs = [r for r in ledger if len(r) >= 6 and r[4] == "send_error"]
    for r in errs[:5]:
        out.append(f"🟡 gửi lỗi: {r[1]} | {r[5]}")
    if show_all:
        for r in ledger:
            if len(r) >= 6 and r[4] == "sent":
                out.append(f"  gửi: {r[1]} | {r[5]}")
    return out[:MAX_LINES]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    show_all = "--all" in argv
    args = [a for a in argv[1:] if a != "--all"]
    if args[0] == "--file":
        with open(args[1], encoding="utf-8") as f:
            text = f.read()
    else:
        text = get_log(args[0])
    print("\n".join(analyse(text, show_all)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
