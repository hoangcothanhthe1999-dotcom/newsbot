"""Đo độ chính xác của bộ lọc AI (ai_relevant) trên bộ tin chuẩn golden/golden_set.jsonl.

Cần ít nhất một khóa AI trong môi trường (GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY). Không dùng khóa thì thoát mã 2.
  python eval_golden.py            # in độ chính xác, độ sót, các ca sai
  (đọc thêm golden/golden_holdout.jsonl nếu có; in riêng dòng HOLDOUT, mã thoát bit 4 khi holdout n>=5 dưới ngưỡng)
  python eval_golden.py --min-recall 0.95 --min-precision 0.85   # thoát mã 1 nếu dưới ngưỡng
"Độ sót" = tin cần GIỮ mà AI loại (nghiêm trọng hơn). "Độ chính xác" = trong số tin AI giữ, bao nhiêu % đúng là tin cần giữ.
Chỉ gọi AI cho bộ tin chuẩn (vài chục dòng, 2 lượt gọi), không gửi Telegram.
"""
import json
import os
import sys

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:eval")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
GOLDEN = os.path.join(ROOT, "golden", "golden_set.jsonl")
HOLDOUT = os.path.join(ROOT, "golden", "golden_holdout.jsonl")  # tập giữ riêng: dòng có basis là lời Boss, không dùng để chỉnh lời nhắc
HOLDOUT_MIN_N = 5  # n dưới mức này chỉ in, không làm đỏ


def load(path=None):
    path = path or GOLDEN
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def load_holdout():
    """Đọc golden_holdout.jsonl; không có tệp thì trả danh sách rỗng."""
    return load(HOLDOUT)


def holdout_fails(res, min_recall, min_precision, min_n=HOLDOUT_MIN_N):
    """True khi holdout dưới ngưỡng. Chỉ áp khi n >= min_n; n nhỏ hơn chỉ in, không làm đỏ."""
    if not res or res["n"] < min_n:
        return False
    return res["recall"] < min_recall or res["precision"] < min_precision


def score(rows, kept_ids):
    """Trả về dict số liệu từ danh sách nhãn và tập id mà AI giữ."""
    tp = sum(1 for r in rows if r["label"] == "keep" and r["id"] in kept_ids)
    fn = [r for r in rows if r["label"] == "keep" and r["id"] not in kept_ids]
    fp = [r for r in rows if r["label"] == "drop" and r["id"] in kept_ids]
    kept = tp + len(fp)
    pos = tp + len(fn)
    return {"n": len(rows), "recall": tp / pos if pos else 1.0, "precision": tp / kept if kept else 1.0, "missed": fn, "junk": fp}


def main(argv):
    import bot
    if not (bot.GEMINI_KEY or bot.GROQ_KEY or bot.OPENROUTER_KEY or bot.CF_KEY):
        print("Thiếu khóa AI trong môi trường: không chạy được.")
        return 2
    main_rows = load()
    hold_rows = load_holdout()
    rows = main_rows + hold_rows
    crit = bot.tag_criterion(bot.CAMBO_TAG)
    items = [{"id": r["id"], "title": r["title"], "desc": r["desc"], "domain": r["domain"], "official": r["official"]} for r in rows]
    pre = {it["id"]: bot.pre_decide(bot.CAMBO_TAG, {**it, "source": it["domain"], "link": ""}) for it in items}  # như bot thật: luật chặn cứng chạy trước AI
    to_ai = [it for it in items if pre[it["id"]] is None]
    ok, unknown = bot.ai_relevant([(it, crit) for it in to_ai])
    kept = {i for i, _ in ok} | {i for i, v in pre.items() if v}
    if unknown:
        print(f"⚠ AI chưa chấm được {len(unknown)} tin; kết quả không đáng tin, chạy lại sau.")
    res = score(main_rows, kept)
    hres = score(hold_rows, kept) if hold_rows else None
    print(f"Bộ chuẩn {res['n']} tin | độ sót: {1 - res['recall']:.0%} | độ chính xác: {res['precision']:.0%}")
    for r in res["missed"]:
        print(f"  SÓT [{r['clarity']}] {r['title'][:70]}  ({r['basis'][:50]})")
    for r in res["junk"]:
        print(f"  RÁC [{r['clarity']}] {r['title'][:70]}  ({r['basis'][:50]})")
    mr = float(argv[argv.index("--min-recall") + 1]) if "--min-recall" in argv else 0.0
    mp = float(argv[argv.index("--min-precision") + 1]) if "--min-precision" in argv else 0.0
    if hres is not None:
        print(f"HOLDOUT: sót {1 - hres['recall']:.0%} chính xác {hres['precision']:.0%} (n={hres['n']})")
        for r in hres["missed"]:
            print(f"  HOLDOUT SÓT [{r['clarity']}] {r['title'][:70]}")
        for r in hres["junk"]:
            print(f"  HOLDOUT RÁC [{r['clarity']}] {r['title'][:70]}")
        if hres["n"] < HOLDOUT_MIN_N:
            print(f"  (n<{HOLDOUT_MIN_N}: chỉ in, không áp ngưỡng)")
    else:
        print("HOLDOUT: sót 0% chính xác 100% (n=0)")
    code = 1 if (res["recall"] < mr or res["precision"] < mp or unknown) and (mr or mp) else 0
    if (mr or mp) and holdout_fails(hres, mr, mp):
        code |= 4  # bit 4: holdout không đạt (workflow đếm riêng)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
