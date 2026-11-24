"""Kiểm nhanh 1 run của bot: in tối đa 30 dòng, chỉ phần bất thường. Không gọi AI.

Cách dùng:
  python check_run.py RUN_ID            # lấy log qua gh (cần gh đã đăng nhập), repo mặc định hoangcothanhthe1999-dotcom/newsbot
  python check_run.py --file log.txt    # đọc log đã có sẵn
  Thêm --all để in cả các dòng LEDGER của bài đã gửi.
  python check_run.py --day [YYYY-MM-DD]  # gom MỌI phiên đã xong của ngày (giờ VN, mặc định hôm nay) thành ~30 dòng
"""
import io
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone

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
        if s.get("flags"):
            out.append("🚩 Cờ: " + ", ".join(s["flags"]))
        if s.get("ai"):
            out.append("ℹ AI: " + "; ".join(f"{k} {v['ok']}/{v['calls']} lượt, {v['sec']}s" for k, v in s["ai"].items()))
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


def parse_runs(text):
    """Trả về (danh sách RUNSUM, danh sách dòng LEDGER) của 1 log."""
    sums, ledger = [], []
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
    return sums, ledger


def summarize_day(day_runs):
    """day_runs: list of (run_id, text). Gom cả ngày thành tối đa MAX_LINES dòng. Không gọi AI."""
    out = []
    n_runs = len(day_runs)
    sent_titles, flags, src_fail_runs, ai_tot, lowconf = [], {}, {}, {}, {}
    no_sum, tb = 0, 0
    sent_total = fetched_total = 0
    for rid, text in day_runs:
        sums, ledger = parse_runs(text)
        if "Traceback" in text:
            tb += 1
        if not sums:
            no_sum += 1
            continue
        s = sums[-1]
        sent_total += s.get("sent", 0)
        fetched_total += s.get("fetched", 0)
        for f in s.get("flags", []):
            flags[f] = flags.get(f, 0) + 1
        for n in s.get("src_fail_names", []):
            src_fail_runs[n] = src_fail_runs.get(n, 0) + 1
        for k, v in (s.get("ai") or {}).items():
            t = ai_tot.setdefault(k, [0, 0, 0.0])
            t[0] += v["calls"]
            t[1] += v["ok"]
            t[2] += v["sec"]
        for r in ledger:
            if len(r) >= 6 and r[4] == "sent":
                sent_titles.append(f"{r[1]} | {r[5]}")
            if len(r) >= 6 and r[4].endswith("_lowconf"):
                lowconf[r[0]] = ("loại" if r[3] == "dropped" else "giữ", r[1], r[5])
    out.append(f"📅 {n_runs} phiên; gửi {sent_total} tin; đọc {fetched_total} bài" + (f"; {no_sum} phiên thiếu RUNSUM" if no_sum else ""))
    if tb:
        out.append(f"🔴 {tb} phiên có Traceback")
    if flags:
        out.append("🚩 Cờ: " + ", ".join(f"{k}×{v}" for k, v in sorted(flags.items(), key=lambda kv: -kv[1])))
    chronic = sorted(((n, c) for n, c in src_fail_runs.items() if c >= max(2, n_runs // 2)), key=lambda x: -x[1])
    if chronic:
        out.append("🟡 Nguồn lỗi kéo dài: " + ", ".join(f"{n}({c}/{n_runs})" for n, c in chronic[:10]))
    if ai_tot:
        out.append("ℹ AI: " + "; ".join(f"{k} {v[1]}/{v[0]} lượt {round(v[2])}s" for k, v in ai_tot.items()))
    if lowconf:
        out.append(f"❓ {len(lowconf)} quyết định lưng chừng (Boss chấm đúng/sai):")
        for tid, (act, src, title) in list(lowconf.items())[:10]:
            out.append(f"  [{tid}] AI {act}: {src} | {title}")
    for t in sent_titles[:12]:
        out.append("  gửi: " + t)
    if len(sent_titles) > 12:
        out.append(f"  … và {len(sent_titles) - 12} tin nữa")
    return out[:MAX_LINES]


def list_day_run_ids(day):
    """Run đã xong của ngày `day` (YYYY-MM-DD, giờ VN) theo created_at UTC."""
    raw = subprocess.run(["gh", "api", f"repos/{REPO}/actions/runs?per_page=100&status=completed"], capture_output=True, check=True).stdout
    ids = []
    for r in json.loads(raw).get("workflow_runs", []):
        created = datetime.strptime(r["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + timedelta(hours=7)
        if created.strftime("%Y-%m-%d") == day:
            ids.append(r["id"])
    return sorted(ids)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "--day":
        day = argv[2] if len(argv) > 2 else (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d")
        runs = []
        for rid in list_day_run_ids(day):
            try:
                runs.append((rid, get_log(rid)))
            except Exception:
                pass
        print("\n".join(summarize_day(runs)))
        return 0
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
