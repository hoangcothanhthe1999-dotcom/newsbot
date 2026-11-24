"""Test offline: DEC trong log (mọi quyết định) và trace_item.py."""
import importlib
import logging
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import trace_item


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.setenv("DECISIONS_FILE", str(tmp_path / "d.jsonl"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    mod.LEDGER_BUF.clear()
    mod.DEC_BUF.clear()
    mod.TRACE_COUNTS.clear()
    mod._trace_seen.clear()
    yield mod


def test_dec_logs_every_decision_without_query_string(bot, caplog):
    a = {"title": "Tin cũ | gạch", "link": "https://a.example/news/1?token=SECRET", "source": "A"}
    bot.trace("age", "dropped", "too_old", a)
    bot.trace("keyword", "dropped", "keyword_mismatch", {"title": "Bài khác", "link": "https://b.example/x", "source": "B"})
    assert len(bot.LEDGER_BUF) == 0 and len(bot.DEC_BUF) == 2
    with caplog.at_level(logging.INFO):
        bot.log_run_ledger()
    assert "DEC|" in caplog.text and "SECRET" not in caplog.text


def test_trace_item_finds_item_and_explains(bot, caplog):
    it = {"title": "Thailand plans to buy rocket", "link": "https://k.example/n/9", "source": "K"}
    bot.trace("age", "dropped", "too_old", it)
    with caplog.at_level(logging.INFO):
        bot.log_run_ledger()
    out = trace_item.trace("rocket", [(1, caplog.text)])
    text = "\n".join(out)
    assert "quá tuổi" in text and "kết luận phiên" in text


def test_trace_item_unseen_points_to_sources():
    log = "NGUỒN | rss | Khmer Times | bài=0 | ok=0 lỗi=3 HTTP 403\nDEC|t1|age|dropped|too_old|S|Tin khác\n"
    out = "\n".join(trace_item.trace("nikkei", [(7, log)]))
    assert "KHÔNG hề xử lý" in out and "Khmer Times" in out


def test_trace_item_by_full_link(bot, caplog):
    link = "https://k.example/n/77"
    bot.trace("keyword", "dropped", "keyword_mismatch", {"title": "Bài lạ", "link": link, "source": "K"})
    with caplog.at_level(logging.INFO):
        bot.log_run_ledger()
    assert "k.example/n/77" in caplog.text  # Boss duyệt 24/11: DEC có link (đã bỏ tham số truy vấn)
    out = "\n".join(trace_item.trace(link, [(1, caplog.text)]))
    assert "không khớp từ khóa" in out


def test_trace_item_unseen_link_unknown_source_is_A():
    out = "\n".join(trace_item.trace("https://nikkei-unknown-site.example/a/1", [(1, "DEC|t1|age|dropped|too_old|S|Tin khác\n")]))
    assert "KHÔNG có trong" in out and "KẾT LUẬN: A" in out


def test_trace_item_unseen_link_failing_source_is_B(tmp_path):
    (tmp_path / "sources.py").write_text("FEEDS = ['https://khmertimeskh.com/feed']", encoding="utf-8")
    has, _ = trace_item.source_coverage("khmertimeskh.com", str(tmp_path))
    assert has
    log = "NGUỒN | rss | khmertimeskh | bài=0 | ok=0 lỗi=3 HTTP 403\n"
    out = "\n".join(trace_item.trace("https://khmertimeskh.com/a/2", [(1, log)]))
    assert "KẾT LUẬN: B" in out


def test_need_hints_uses_golden_and_vn_rule():
    out = "\n".join(trace_item.need_hints("Thailand plans to buy rocket systems", "https://vnexpress.net/a"))
    assert "Nguồn Việt Nam" in out and "gần giống" in out and "hỏi Boss" in out


def test_dec_has_full_title_and_link_and_parses(bot, caplog):
    t = "Tiêu đề rất dài " * 8
    it = {"title": t, "link": "https://k.example/n/7?x=SECRET", "source": "K"}
    bot.trace("age", "dropped", "too_old", it)
    with caplog.at_level(logging.INFO):
        bot.log_run_ledger()
    import trace_item
    rows = trace_item.parse_dec(caplog.text)
    assert rows and rows[0]["title"].startswith(t.strip()[:100]) and len(rows[0]["title"]) > 60
    assert rows[0]["link"] == "k.example/n/7" and "SECRET" not in caplog.text


def test_claim_send_refusals_are_traced(bot):
    cs = {"_id": "c1", "sent": {}, "titles": []}
    it = {"id": "x1", "title": "Cambodia border clash news today", "link": "https://z.example/1", "source": "Z"}
    assert bot.claim_send(cs, it) is True
    assert bot.claim_send(cs, it) is False
    assert any("claim_send|dropped|already_sent" in d for d in bot.DEC_BUF)
