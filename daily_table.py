"""Bảng nhật ký ngày của bot (cửa sổ 24 giờ 16:15 hôm trước đến 16:15 hôm nay, giờ VN), dựng từ log các run, KHÔNG gọi AI.

  python daily_table.py [YYYY-MM-DD]                    # bảng tin + bảng nguồn của cửa sổ kết thúc 16:15 ngày đó (mặc định hôm nay)
  python daily_table.py [YYYY-MM-DD] --match ds.txt      # thêm kết quả khớp: mỗi dòng ds.txt là LINK đầy đủ hoặc từ khóa tiêu đề
  python daily_table.py --file log1.txt [log2.txt ...]   # dựng từ log có sẵn (không cần gh)

Mỗi tin một dòng: mã | nguồn | trạng thái | bước | lý do | tiêu đề | link (đã bỏ tham số truy vấn).
Trạng thái: CHỌN-GỬI (đã gửi), CHỌN-LỖI-GỬI (qua lọc nhưng gửi lỗi), QUA-LỌC-CHƯA-GỬI, LOẠI, THẤY-CHƯA-XÉT.
Bảng chỉ nằm trong bộ nhớ/tệp tạm của phiên chạy lệnh: không ghi vào repo, nên không có nhật ký nào tồn tại quá một ngày ngoài log run của GitHub.
Không in khóa, nội dung bài hay phản hồi AI. Giờ đăng/giờ thấy không có trong log DEC nên không có cột giờ.
"""
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import check_run
import trace_item

WINDOW_END = (16, 15)   # 16:15 giờ VN, trùng END_TIME_VN của newsbot.yml
VN = timezone(timedelta(hours=7))
# ưu tiên khi một tin có nhiều quyết định: bước cuối cùng quyết định số phận
SENT, SEND_ERR, PASSED, DROPPED, SEEN = "CHỌN-GỬI", "CHỌN-LỖI-GỬI", "QUA-LỌC-CHƯA-GỬI", "LOẠI", "THẤY-CHƯA-XÉT"
DEC_STATUS_ORDER = {SENT: 0, SEND_ERR: 1, DROPPED: 2, PASSED: 3, SEEN: 4}


def window(day):
    """(bắt đầu, kết thúc) của cửa sổ kết thúc 16:15 ngày `day` (YYYY-MM-DD, giờ VN), dạng datetime có múi giờ."""
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=VN)
    end = d.replace(hour=WINDOW_END[0], minute=WINDOW_END[1])
    return end - timedelta(days=1), end


def list_window_run_ids(day):
    """Run đã xong có created_at trong cửa sổ của `day`, theo thứ tự thời gian."""
    start, end = window(day)
    raw = subprocess.run(["gh", "api", f"repos/{check_run.REPO}/actions/runs?per_page=100&status=completed"],
                         capture_output=True, check=True).stdout
    found = []
    for r in json.loads(raw).get("workflow_runs", []):
        created = datetime.strptime(r["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(VN)
        if start <= created < end:
            found.append((created, r["id"]))
    return [rid for _, rid in sorted(found)]


def _status_of(rows):
    """Trạng thái cuối cùng của một tin từ các dòng DEC của nó (mọi phiên trong cửa sổ)."""
    sts = {(r["stage"], r["status"]) for r in rows}
    if ("send", "sent") in sts:
        return SENT
    if ("send", "error") in sts:
        return SEND_ERR
    if any(s == "dropped" for _, s in sts):
        return DROPPED
    if any(s == "passed" for _, s in sts):
        return PASSED
    return SEEN


def build_items(logs):
    """logs = [log_text, ...]. Trả về danh sách tin (dict), mỗi tin một dòng, sắp theo trạng thái rồi nguồn."""
    by_tid = {}
    for text in logs:
        for r in trace_item.parse_dec(text):
            by_tid.setdefault(r["tid"], []).append(r)
    items = []
    for tid, rows in by_tid.items():
        status = _status_of(rows)
        pick = rows[-1]
        if status == SENT:
            pick = next(r for r in rows if (r["stage"], r["status"]) == ("send", "sent"))
        elif status == SEND_ERR:
            pick = next(r for r in rows if (r["stage"], r["status"]) == ("send", "error"))
        elif status == DROPPED:
            pick = next(r for r in reversed(rows) if r["status"] == "dropped")
        items.append({"tid": tid, "src": pick["src"], "status": status, "stage": pick["stage"], "reason": pick["reason"],
                      "title": pick["title"], "link": pick["link"]})
    items.sort(key=lambda x: (DEC_STATUS_ORDER[x["status"]], x["src"], x["title"]))
    return items


def build_sources(logs):
    """Gộp các dòng `NGUỒN | tag | tên | bài=N | ok=A lỗi=B ...` của mọi phiên: mỗi nguồn một dòng (tốt nhất của cả cửa sổ)."""
    rank = {"ĐỌC ĐƯỢC": 0, "TRANG TRỐNG": 1, "LỖI": 2}
    out = {}
    pat = re.compile(r"NGUỒN \| (ĐỌC ĐƯỢC|TRANG TRỐNG|LỖI) \| (.*?) \| bài=(\d+) \| ok=(\d+) lỗi=(\d+)\s*(.*)")
    for text in logs:
        for ln in text.splitlines():
            m = pat.search(ln)
            if not m:
                continue
            tag, name, n, ok, fail, err = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)), m.group(6).strip()
            cur = out.get(name)
            if cur is None:
                cur = out[name] = {"name": name, "tag": tag, "n": 0, "ok": 0, "fail": 0, "err": "",
                                   "runs": 0, "runs_err": 0}
            elif rank[tag] < rank[cur["tag"]]:
                cur["tag"] = tag
            cur["n"] += n
            cur["ok"] += ok
            cur["fail"] += fail
            cur["runs"] += 1
            if tag == "LỖI":
                cur["runs_err"] += 1
            if err:
                cur["err"] = err   # lỗi gần nhất
    return sorted(out.values(), key=lambda s: (rank[s["tag"]] == 0, s["name"]), reverse=False)


def match(items, query):
    """Khớp một dòng của danh sách đối chiếu (LINK đầy đủ hoặc từ khóa tiêu đề) với bảng. Trả về danh sách tin khớp."""
    q = query.strip()
    if not q:
        return []
    if q.startswith("http"):
        tid = hashlib.sha1(q.encode("utf-8", "ignore")).hexdigest()[:8]
        hit = [i for i in items if i["tid"] == tid]
        if hit:
            return hit
        dom = trace_item.domain_of(q)
        key = q.rstrip("/").rsplit("/", 1)[-1].lower()
        return [i for i in items if dom and dom in i["link"] and key and key in i["link"].lower()]
    ql = q.lower()
    return [i for i in items if ql in i["title"].lower() or i["tid"] == ql]


def counts(items):
    """Số tin theo trạng thái và số lần theo (bước/lý do) của tin bị loại: để ghi dòng ngày (bảng chỉ tồn tại trong ngày)."""
    by_status, by_reason = {}, {}
    for i in items:
        by_status[i["status"]] = by_status.get(i["status"], 0) + 1
        if i["status"] == DROPPED:
            k = f'{i["stage"]}/{i["reason"]}'
            by_reason[k] = by_reason.get(k, 0) + 1
    return by_status, dict(sorted(by_reason.items(), key=lambda kv: -kv[1]))


def render(items, sources, matches=None):
    by_status, by_reason = counts(items)
    out = ["# TIN (mã | nguồn | trạng thái | bước | lý do | tiêu đề | link)"]
    for i in items:
        out.append(" | ".join([i["tid"], i["src"], i["status"], i["stage"], i["reason"], i["title"], i["link"]]))
    out.append("# NGUỒN (tên | tình trạng | bài | ok | lỗi | ghi chú)")
    for s in sources:
        out.append(" | ".join([s["name"], s["tag"], str(s["n"]), str(s["ok"]), str(s["fail"]), s["err"]]))
    bad = sorted((x for x in sources if x.get("runs_err")), key=lambda x: (-x["runs_err"] / x["runs"], x["name"]))
    out.append("# NGUỒN LỖI TRONG NGÀY (tên | run lỗi/tổng run | lỗi gần nhất)")
    if not bad:
        out.append("(không có)")
    for x in bad:
        out.append(f"{x['name']} | {x['runs_err']}/{x['runs']} | {x['err']}")
    out.append("# ĐẾM THEO TRẠNG THÁI: " + "; ".join(f"{k}={v}" for k, v in sorted(by_status.items())))
    out.append("# ĐẾM LOẠI THEO BƯỚC/LÝ DO: " + "; ".join(f"{k}={v}" for k, v in by_reason.items()))
    if matches is not None:
        out.append("# KHỚP DANH SÁCH ĐỐI CHIẾU (dòng | kết quả)")
        for q, hit in matches:
            if hit:
                h = hit[0]
                out.append(f"{q[:80]} | {h['status']} | {h['stage']}/{h['reason']} | {h['src']}")
            else:
                out.append(f"{q[:80]} | KHÔNG DẤU VẾT (bot không thấy: nguồn chưa tích hợp hoặc nguồn lỗi, xem bảng NGUỒN)")
    return "\n".join(out)


def main(argv):
    args = argv[1:]
    match_file = None
    if "--match" in args:
        i = args.index("--match")
        match_file = args[i + 1]
        del args[i:i + 2]
    if args and args[0] == "--file":
        logs = []
        for p in args[1:]:
            with open(p, encoding="utf-8") as f:
                logs.append(f.read())
    else:
        day = args[0] if args else datetime.now(timezone.utc).astimezone(VN).strftime("%Y-%m-%d")
        logs = []
        for rid in list_window_run_ids(day):
            try:
                logs.append(check_run.get_log(rid))
            except Exception:
                pass
        if not logs:
            print("Không lấy được log run nào trong cửa sổ (gh chưa đăng nhập, hết quyền hoặc không có run).")
            return 1
    items = build_items(logs)
    matches = None
    if match_file:
        with open(match_file, encoding="utf-8") as f:
            matches = [(q.strip(), match(items, q)) for q in f if q.strip()]
    print(render(items, build_sources(logs), matches))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
