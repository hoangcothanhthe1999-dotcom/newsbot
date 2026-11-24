import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_run


def test_find_dup_sent_flags_near_identical_titles():
    p = check_run.find_dup_sent(["Cambodia seizes 5 tonnes of drugs at port", "Cambodia seizes 5 tonnes of drugs at the port", "Thai army moves troops"])
    assert len(p) == 1


def test_drop_rate_counts_unique_items():
    log = "".join(f"DEC|t{i}|ai_relevance|dropped|ai_irrelevant|S|x|l\n" for i in range(25)) + "DEC|t99|relevance|passed|keep|S|y|l\n"
    assert check_run.drop_rate([(1, log)]) == (26, 25)


def test_summarize_day_reports_dup_and_overfilter():
    ledger = "".join(f"LEDGER|a{i}|S|send|sent|sent|Cambodia seizes drugs at port number {i % 2}\n" for i in range(2))
    dec = "".join(f"DEC|t{i}|ai_relevance|dropped|ai_irrelevant|S|x|l\n" for i in range(30))
    sums = 'RUNSUM {"sent": 2, "fetched": 40, "flags": [], "src_fail_names": [], "ai": {}}\n'
    out = "\n".join(check_run.summarize_day([(1, sums + ledger + dec)]))
    assert "🔴" in out and "🟡 Bộ lọc loại 30/30" in out
