"""Truy MỌI quyết định của bot về một tin (từ log công khai, không cần artifact, không gọi AI).

  python trace_item.py "từ khóa trong tiêu đề | mã tin 8 ký tự | LINK ĐẦY ĐỦ của bài" [YYYY-MM-DD]   # lấy log các run đã xong của ngày (mặc định hôm nay, giờ VN) qua gh
  python trace_item.py "từ khóa" --file log.txt                                    # đọc log có sẵn

In theo từng phiên: các bước bot đã xử lý tin đó (bước/trạng thái/lý do bằng tiếng Việt), kết luận cuối, và nếu bot KHÔNG hề thấy tin
thì in nguồn cùng tên đang lỗi (gợi ý nguyên nhân A/B). Tối đa 40 dòng.
Log KHÔNG in link (quy tắc riêng tư): đưa link đầy đủ thì script tự tính mã tin = sha1(link)[:8] như bot và tra theo mã đó.
Link khác từng ký tự với link bot đọc (tham số theo dõi, http/https...) thì mã lệch: khi đó tra theo từ khóa tiêu đề.
"""
import hashlib
import re
import sys

import check_run
from investigate import WHY

MAX_LINES = 40
EXTRA_WHY = {
    "duplicate_title": "trùng tiêu đề với tin đã có (không gửi lại)",
    "no_criterion": "tag không cần AI kiểm (giữ)",
    "strong_keyword_match": "khớp đúng cụm từ khóa (giữ, khỏi hỏi AI)",
    "foreign_official_bypass": "nguồn chính thức nước ngoài (luôn giữ)",
    "hard_word_official_bypass": "nguồn chính thức có từ cốt lõi (giữ)",
    "ai_relevant": "AI cho là liên quan (giữ)",
    "ai_unavailable_strict_keep": "AI không chấm được, lọc chặt dự phòng GIỮ",
    "ai_unavailable_strict_drop": "AI không chấm được, lọc chặt dự phòng LOẠI",
    "pre_decide_keep": "quyết định sớm bằng quy tắc: giữ",
    "pre_decide_drop": "quyết định sớm bằng quy tắc: loại",
    "sent_overflow_list": "đã gửi trong danh sách gộp (🌙/tràn)",
}


def why(reason):
    return WHY.get(reason) or EXTRA_WHY.get(reason) or reason


def parse_dec(text):
    rows = []
    for ln in text.splitlines():
        m = re.search(r"DEC\|(.*)", ln)
        if m:
            f = m.group(1).split("|")
            if len(f) >= 6:
                rows.append({"tid": f[0], "stage": f[1], "status": f[2], "reason": f[3], "src": f[4], "title": "|".join(f[5:])})
    return rows


def src_fail_lines(text):
    return sorted({m.group(0).strip() for ln in text.splitlines() if (m := re.search(r"NGUỒN \|.*lỗi=[1-9].*", ln))})


def trace(query, runs):
    """runs: list of (run_id, text). Trả về danh sách dòng kết quả."""
    q = query.lower()
    qtid = hashlib.sha1(query.encode("utf-8", "ignore")).hexdigest()[:8] if query.startswith("http") else None
    out = []
    seen_any = False
    fails = []
    for rid, text in runs:
        hits = [r for r in parse_dec(text) if q in r["title"].lower() or q == r["tid"] or r["tid"] == qtid]
        if not hits:
            fails += src_fail_lines(text)
            continue
        seen_any = True
        out.append(f"▶ run {rid}")
        for r in hits:
            out.append(f"  [{r['tid']}] {r['src']} | {r['stage']}/{r['status']}: {why(r['reason'])} | {r['title']}")
        last = hits[-1]
        out.append(f"  ⇒ kết luận phiên: {last['status']} ở bước {last['stage']} ({why(last['reason'])})")
    if not seen_any:
        out.append(f"Không run nào có tin khớp «{query}». Nghĩa là bot KHÔNG hề xử lý tin này (hoặc log bị cắt ở DEC_MAX).")
        out.append("→ Nghi A (nguồn chưa có trong bot) hoặc B (nguồn lỗi/bị chặn) hoặc tin đăng ngoài khung giờ chạy. Nguồn lỗi trong các phiên:")
        for ln in sorted(set(fails))[:15]:
            out.append("  " + ln[:110])
    return out[:MAX_LINES]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    query = argv[1]
    if len(argv) > 3 and argv[2] == "--file":
        with open(argv[3], encoding="utf-8") as f:
            runs = [("file", f.read())]
    else:
        from datetime import datetime, timedelta, timezone
        day = argv[2] if len(argv) > 2 else (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d")
        runs = []
        for rid in check_run.list_day_run_ids(day):
            try:
                runs.append((rid, check_run.get_log(rid)))
            except Exception:
                pass
    print("\n".join(trace(query, runs)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
