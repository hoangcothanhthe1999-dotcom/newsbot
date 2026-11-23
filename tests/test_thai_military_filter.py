"""Test offline: câu lệnh lọc lạc đề phải coi tin quân sự Thái Lan là liên quan."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    monkeypatch.setattr(mod, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod, "save_state", lambda: None)
    yield mod
    sys.path.remove(ROOT)


def test_prompt_has_thai_military_rule(bot, monkeypatch):
    seen = []
    monkeypatch.setattr(bot, "GEMINI_KEY", "x")
    monkeypatch.setattr(bot, "gemini", lambda p, *a, **k: seen.append(p) or "[]")
    monkeypatch.setattr(bot, "ai_json", lambda raw: [])
    bot._relevance_cache.clear()
    it = {"id": "t1", "title": "Thailand plans to buy US made rocket", "desc": ""}
    bot.ai_relevant([(it, "chủ đề quân sự Campuchia")])
    assert seen, "ai_relevant không gọi AI"
    assert "quân sự Thái Lan" in seen[0] and "kể cả khi tiêu đề không nhắc tên Campuchia" in seen[0]
