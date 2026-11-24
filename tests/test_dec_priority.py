"""Sổ lỗi #10: buffer DEC đầy không được làm mất quyết định quan trọng và phải bật cờ dec_cut."""
import importlib
import json
import logging
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


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
    mod.DEC_DROPPED.update(n=0, low=0)
    yield mod


def test_low_priority_flood_keeps_room_for_important(bot, caplog):
    for i in range(bot.DEC_LOW_MAX + 50):
        bot.trace("age", "dropped", "too_old", {"title": f"cũ {i}", "link": f"https://a.example/{i}", "source": "A"})
    assert len(bot.DEC_BUF) == bot.DEC_LOW_MAX
    assert bot.DEC_DROPPED["n"] == 50 and bot.DEC_DROPPED["low"] == 50
    bot.trace("relevance", "dropped", "ai_relevance", {"title": "What Nikkei Asia missed", "link": "https://k.example/n", "source": "K"})
    assert any("ai_relevance" in d and "Nikkei" in d for d in bot.DEC_BUF)
    with caplog.at_level(logging.INFO):
        bot.log_run_ledger()
    line = next(m for m in caplog.messages if m.startswith("RUNSUM "))
    rs = json.loads(line[len("RUNSUM "):])
    assert rs["dec_cut"] is True and rs["dec_dropped"] == 50
    assert "dec_cut" in rs["flags"]


def test_no_cut_no_flag(bot):
    bot.trace("age", "dropped", "too_old", {"title": "x", "link": "https://a.example/1", "source": "A"})
    assert bot.DEC_DROPPED["n"] == 0
    assert "dec_cut" not in bot.run_flags({"dec_cut": False})
