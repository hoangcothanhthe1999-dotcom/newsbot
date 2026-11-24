"""Chạy lại quyết định của bot trên tin của lần chạy cũ bằng MÃ HIỆN TẠI, rồi so với kết quả cũ.

  python replay_dec.py LOG.txt            # LOG.txt = log Actions (có dòng DEC|...). Chỉ luật cứng pre_decide, không gọi AI.
  python replay_dec.py LOG.txt --ai       # thêm bước AI (cần khóa AI trong môi trường), chỉ cho tin luật cứng không quyết được

Chỉ xét tin bị LOẠI ở bước relevance/ai_relevance/keyword/title_dedupe/ai_dedupe (mục đích: bản sửa có cứu thêm hoặc làm mất tin nào).
Giới hạn: log cũ chỉ có tiêu đề (không có mô tả), nên kết quả là ước lượng; không gửi Telegram, không ghi repo.
Đầu ra: danh sách tin đổi quyết định (loại -> giữ, giữ -> loại) để C đối chiếu.
"""
import os
import sys

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:replay")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import trace_item

STAGES = {"relevance", "ai_relevance", "keyword", "title_dedupe", "ai_dedupe"}


def old_decisions(text):
    """Mỗi tin (tid) -> dòng DEC cuối cùng ở các bước lọc, kèm trạng thái cũ (dropped/passed)."""
    out = {}
    for r in trace_item.parse_dec(text):
        if r["stage"] in STAGES:
            out[r["tid"]] = r
    return out


def new_verdict(bot, row):
    """True=giữ, False=loại, None=cần AI. Chỉ dùng tiêu đề + nguồn (log cũ không có mô tả)."""
    it = {"title": row["title"], "desc": "", "source": row["src"], "domain": row["src"], "link": row.get("link", ""), "official": False}
    return bot.pre_decide(bot.CAMBO_TAG, it)


def compare(bot, rows):
    flips, need_ai = [], []
    for r in rows.values():
        if r["reason"] in ("keyword_mismatch", "too_old"):
            continue
        v = new_verdict(bot, r)
        was_kept = r["status"] == "passed"
        if v is None:
            need_ai.append(r)
        elif v != was_kept:
            flips.append((r, "loại→giữ" if v else "giữ→loại"))
    return flips, need_ai


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    import bot
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        rows = old_decisions(f.read())
    if not rows:
        print("Không thấy dòng DEC trong log (log cũ hơn bản có sổ quyết định?).")
        return 2
    flips, need_ai = compare(bot, rows)
    print(f"Tin xét: {len(rows)} | đổi quyết định bằng luật cứng: {len(flips)} | cần AI mới biết: {len(need_ai)}")
    for r, d in flips:
        print(f"  {d} [{r['reason']}] {r['src']}: {r['title'][:80]} {r.get('link', '')}")
    if "--ai" in argv and need_ai:
        if not (bot.GEMINI_KEY or bot.GROQ_KEY or bot.OPENROUTER_KEY or bot.CF_KEY):
            print("Thiếu khóa AI: bỏ qua bước --ai.")
            return 0
        crit = bot.tag_criterion(bot.CAMBO_TAG)
        items = [{"id": r["tid"], "title": r["title"], "desc": "", "domain": r["src"], "source": r["src"], "link": r.get("link", ""), "official": False} for r in need_ai]
        ok, unknown = bot.ai_relevant([(it, crit) for it in items])
        kept = {i for i, _ in ok}
        print(f"AI chạy lại {len(items)} tin, chưa chấm được {len(unknown)}:")
        for r in need_ai:
            was_kept = r["status"] == "passed"
            if (r["tid"] in kept) != was_kept and r["tid"] not in {u for u in unknown}:
                print(f"  {'loại→giữ' if r['tid'] in kept else 'giữ→loại'} [{r['reason']}] {r['src']}: {r['title'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
