"""Truy MỌI quyết định của bot về một tin (từ log công khai, không cần artifact, không gọi AI).

  python trace_item.py "từ khóa trong tiêu đề | mã tin 8 ký tự | LINK ĐẦY ĐỦ của bài" [YYYY-MM-DD]   # lấy log các run đã xong của ngày (mặc định hôm nay, giờ VN) qua gh
  python trace_item.py "từ khóa" --file log.txt                                    # đọc log có sẵn

In theo từng phiên: các bước bot đã xử lý tin đó (bước/trạng thái/lý do bằng tiếng Việt), kết luận cuối, và nếu bot KHÔNG hề thấy tin
thì in nguồn cùng tên đang lỗi (gợi ý nguyên nhân A/B). Tối đa 40 dòng, rồi mục CÂU 2 (gợi ý tin chuẩn gần nhất để C chốt cần/không cần).
Log KHÔNG in link (quy tắc riêng tư): đưa link đầy đủ thì script tự tính mã tin = sha1(link)[:8] như bot và tra theo mã đó.
Link khác từng ký tự với link bot đọc (tham số theo dõi, http/https...) thì mã lệch: khi đó tra theo từ khóa tiêu đề.
"""
import hashlib
import os
import re
import sys
from urllib.parse import urlparse

import check_run
from investigate import WHY

MAX_LINES = 40
EXTRA_WHY = {
    "duplicate_title": "trùng tiêu đề với tin đã có (không gửi lại)",
    "no_criterion": "tag không cần AI kiểm (giữ)",
    "strong_keyword_match": "khớp đúng cụm từ khóa (giữ, khỏi hỏi AI)",
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
                link = f[-1] if len(f) >= 7 else ""  # định dạng mới: trường cuối là link (đã bỏ tham số truy vấn)
                title = "|".join(f[5:-1] if len(f) >= 7 else f[5:])
                rows.append({"tid": f[0], "stage": f[1], "status": f[2], "reason": f[3], "src": f[4], "title": title, "link": link})
    return rows


def src_fail_lines(text):
    return sorted({m.group(0).strip() for ln in text.splitlines() if (m := re.search(r"NGUỒN \|.*lỗi=[1-9].*", ln))})


def domain_of(query):
    """Máy chủ của link (bỏ www.), hoặc "" nếu query không phải link."""
    if not query.startswith("http"):
        return ""
    return (urlparse(query).netloc or "").lower().removeprefix("www.")


def source_coverage(domain, root=None):
    """Nguồn của link có nằm trong cấu hình bot không (sources.py, bot.py)? Trả về (có_không, ghi_chú)."""
    root = root or os.path.dirname(os.path.abspath(__file__))
    for name in ("sources.py", "bot.py"):
        try:
            with open(os.path.join(root, name), encoding="utf-8") as f:
                if domain and domain in f.read().lower():
                    return True, f"«{domain}» CÓ trong {name}"
        except OSError:
            continue
    return False, f"«{domain}» KHÔNG có trong sources.py/bot.py"


def need_hints(title, query="", k=3):
    """Gợi ý trả lời câu 2 "tin này có CẦN cho Boss không": tin chuẩn gần nhất trong bộ golden (theo từ chung) kèm nhãn và cơ sở.
    Chỉ là căn cứ cho C phán đoán, KHÔNG phải kết luận; ca không chắc thì hỏi Boss."""
    import eval_golden
    dom = domain_of(query)
    lines = []
    if dom.endswith(".vn") or dom in ("vnexpress.net", "baomoi.com", "soha.vn"):
        lines.append("⇒ Nguồn Việt Nam: Boss KHÔNG cần (chỉ lấy nguồn Campuchia/nước ngoài).")
    words = {w for w in re.findall(r"\w{4,}", title.lower())}
    if not words:
        return lines
    scored = []
    for r in eval_golden.load():
        common = words & set(re.findall(r"\w{4,}", (r["title"] + " " + r["desc"]).lower()))
        if common:
            scored.append((len(common), r))
    for _, r in sorted(scored, key=lambda x: -x[0])[:k]:
        lines.append(f"  gần giống [{r['label']}/{r['clarity']}] {r['title'][:55]} — {r['basis'][:70]}")
    lines.append("→ Đối chiếu quy tắc Boss (CURRENT_STATUS) để chốt CẦN/KHÔNG CẦN; không chắc thì hỏi Boss.")
    return lines


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
        dom = domain_of(query)
        has = None
        if dom:
            has, note = source_coverage(dom)
            out.append("→ " + note)
            if not has:
                out.append("⇒ KẾT LUẬN: A (nguồn chưa có trong bot) → cần thêm nguồn, nếu tin đáng gửi theo mục đích Boss.")
        if has is not False:
            out.append("→ Nghi B (nguồn lỗi/bị chặn), tin đăng ngoài khung giờ chạy, hoặc bot đã thấy ở phiên trước (tra ngày khác). Nguồn lỗi trong các phiên:")
            matched = [ln for ln in sorted(set(fails)) if dom and dom.split(".")[0] in ln.lower()]
            for ln in (matched or sorted(set(fails)))[:15]:
                out.append("  " + ln[:110])
            if dom and matched:
                out.append("⇒ KẾT LUẬN: B (nguồn đang lỗi/bị chặn) → xem nguồn trên, sửa cách đọc hoặc bỏ.")
            elif dom:
                out.append("⇒ Nguồn có trong bot, không báo lỗi, nhưng không thấy tin: nghi RSS thiếu bài hoặc bài đăng ngoài khung (G nếu chưa rõ) → đọc trực tiếp trang nguồn để kiểm.")
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
    title = next((r["title"] for _, tx in runs for r in parse_dec(tx) if query.lower() in r["title"].lower()), "") if not query.startswith("http") else ""
    print("--- CÂU 2: tin này có CẦN cho Boss không? ---")
    print("\n".join(need_hints(title or query, query)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
