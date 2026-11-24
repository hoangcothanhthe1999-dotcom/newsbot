import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import replay_dec
from tests.test_trace_item import bot  # noqa: F401

LOG = (
    "DEC|t1|relevance|dropped|ai_irrelevant|K|Cambodia news A|k.example/a\n"
    "DEC|t2|relevance|passed|keep|K|Cambodia news B|k.example/b\n"
    "DEC|t3|age|dropped|too_old|K|Cu|k.example/c\n"
)


def test_old_decisions_only_filter_stages():
    rows = replay_dec.old_decisions(LOG)
    assert set(rows) == {"t1", "t2"} and rows["t1"]["link"] == "k.example/a"


def test_compare_reports_flips(bot, monkeypatch):  # noqa: F811
    monkeypatch.setattr(bot, "pre_decide", lambda tag, it: "A" in it["title"])
    flips, need_ai = replay_dec.compare(bot, replay_dec.old_decisions(LOG))
    got = {r["tid"]: d for r, d in flips}
    assert got == {"t1": "loại→giữ", "t2": "giữ→loại"} and not need_ai
