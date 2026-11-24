"""Test offline: dòng RUNSUM/LEDGER trong log và check_run.py."""
import importlib
import json
import logging
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.setenv("DECISIONS_FILE", str(tmp_path / "d.jsonl"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    mod.LEDGER_BUF.clear()
    mod.TRACE_COUNTS.clear()
    mod._trace_seen.clear()
    yield mod
    sys.path.remove(ROOT)


def test_ledger_skips_noise_and_has_no_url(bot, caplog):
    a = {"title": "Tin gửi | có dấu gạch", "link": "https://a.example/x?token=SECRET", "source": "A"}
    b = {"title": "Bài cũ", "link": "https://a.example/y", "source": "A"}
    bot.trace("send", "sent", "sent", a)
    bot.trace("age", "dropped", "too_old", b)
    assert len(bot.LEDGER_BUF) == 1
    with caplog.at_level(logging.INFO):
        bot.log_run_ledger()
    text = caplog.text
    assert "RUNSUM" in text and "LEDGER|" in text
    assert "SECRET" not in text and "a.example" not in text


def test_check_run_flags_flood_and_dup():
    sys.path.insert(0, ROOT)
    import check_run
    s = {"sent": 20, "ai_offtopic": 0, "ai_dup": 0, "stale": 0, "src_fail": 0, "src_total": 83, "src_fail_names": [], "ledger_cut": False}
    log = "x RUNSUM " + json.dumps(s) + "\nx LEDGER|ab12|A|send|sent|sent|t1\nx LEDGER|ab12|A|send|sent|sent|t1\n"
    out = "\n".join(check_run.analyse(log))
    assert "Gửi 20 tin" in out and "Gửi trùng" in out
    assert len(check_run.analyse(log)) <= 30
    sys.path.remove(ROOT)


def test_runsum_v2_has_ai_and_flags(bot, caplog):
    bot.SESSION_STATS["ai"].clear()
    bot.SESSION_STATS["src"].clear()
    bot.stat_src("A", items=[1, 2, 3])
    bot.ai_track("gemini", lambda p: None, "x")
    bot.ai_track("groq", lambda p: "ok", "x")
    with caplog.at_level(logging.INFO):
        bot.log_run_ledger()
    line = [ln for ln in caplog.text.splitlines() if "RUNSUM" in ln][-1]
    data = json.loads(line.split("RUNSUM ", 1)[1])
    assert data["v"] == 2 and data["fetched"] == 3
    assert data["ai"]["gemini"]["ok"] == 0 and data["ai"]["groq"]["ok"] == 1
    assert "gemini_all_failed" in data["flags"] and "ai_fallback_used" in data["flags"]


def test_run_flags_fetched_zero_and_passed_but_sent_zero(bot):
    f = bot.run_flags({"src_total": 10, "src_fail": 0, "fetched": 0, "sent": 0, "passed": 0, "ai": {}})
    assert "fetched_zero" in f
    f = bot.run_flags({"src_total": 10, "src_fail": 0, "fetched": 50, "sent": 0, "passed": 8, "ai": {}})
    assert "passed_but_sent_zero" in f and "fetched_zero" not in f


def test_check_run_day_summary():
    sys.path.insert(0, ROOT)
    import check_run
    log1 = 'x RUNSUM ' + json.dumps({"sent": 2, "fetched": 40, "src_fail_names": ["A", "B"], "flags": ["ai_fallback_used"],
                                     "ai": {"gemini": {"calls": 3, "ok": 1, "sec": 9.0}}}) + "\nLEDGER|t1|Src|send|sent|sent|Tin 1\n"
    log2 = 'RUNSUM ' + json.dumps({"sent": 0, "fetched": 30, "src_fail_names": ["A"], "flags": [], "ai": {}}) + "\n"
    out = check_run.summarize_day([(1, log1), (2, log2)])
    assert len(out) <= 30
    assert "2 phiên; gửi 2 tin; đọc 70 bài" in out[0]
    assert any("A(2/2)" in ln for ln in out)
    assert any("ai_fallback_used×1" in ln for ln in out)
    assert any("Tin 1" in ln for ln in out)
