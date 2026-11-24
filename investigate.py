"""Tra sổ quyết định của bot: vì sao một bài KHÔNG được gửi?

Cách dùng:
  1. Tải artifact "decisions-<run>" từ tab Actions (hoặc: gh run download <run_id> -n decisions-<run_id>), giải nén.
  2. python investigate.py "từ khóa trong tiêu đề hoặc link" decisions.jsonl [thư mục hoặc tệp khác ...]
  3. python investigate.py --stats decisions.jsonl     # bảng số liệu theo nguồn

Không gọi mạng, không tốn AI.
"""
import glob
import json
import os
import sys

WHY = {
    "too_old": "quá tuổi (cũ hơn giới hạn MAX_AGE_HOURS, không thuộc diện bắt bù)",
    "keyword_mismatch": "không khớp từ khóa của chat (bị chặn trước khi tới AI)",
    "ai_irrelevant": "AI cho là lạc đề",
    "ai_irrelevant_lowconf": "AI loại nhưng lưng chừng (không chắc)",
    "ai_relevant_lowconf": "AI giữ nhưng lưng chừng (không chắc)",
    "duplicate_event": "AI cho là trùng sự kiện với tin đã gửi",
    "send_error": "gửi Telegram lỗi",
    "sent": "ĐÃ GỬI",
}


def load(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*.jsonl"), recursive=True)
        else:
            files.append(p)
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def search(query, recs):
    q = query.lower()
    hits = [r for r in recs if r.get("stage") != "source_stats"
            and (q in str(r.get("title", "")).lower() or q in str(r.get("url", "")).lower() or q == r.get("tid"))]
    hits.sort(key=lambda r: r.get("ts", ""))
    return hits


def stats(recs):
    rows = {}
    for r in recs:
        if r.get("stage") == "source_stats":
            d = rows.setdefault(r["src"], {"n": 0, "ok": 0, "fail": 0, "kw": 0})
            d["n"] += r.get("n", 0)
            d["ok"] += r.get("ok", 0)
            d["fail"] += r.get("fail", 0)
            d["kw"] += r.get("kw_dropped", 0)
    return rows


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    if argv[1] == "--stats":
        for src, d in sorted(stats(load(argv[2:])).items(), key=lambda kv: kv[1]["n"]):
            print(f"{src:40} bài={d['n']:5} ok={d['ok']:4} lỗi={d['fail']:4} loại-từ-khóa={d['kw']}")
        return 0
    hits = search(argv[1], load(argv[2:]))
    if not hits:
        print("Không thấy bài nào khớp. Có thể: nguồn không đọc được (xem --stats), bài không tới được bước ghi sổ, hoặc artifact hết hạn.")
        return 1
    for r in hits:
        why = WHY.get(r.get("reason"), r.get("reason"))
        extra = f" (tuổi {r['age_h']}h, giới hạn {r['limit_h']}h)" if "age_h" in r else ""
        print(f"{r['ts']} | {r['tid']} | {r['src']} | {r['stage']} -> {r['status']}: {why}{extra}\n    {r['title']}\n    {r.get('url', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
