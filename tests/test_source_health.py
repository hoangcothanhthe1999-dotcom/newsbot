"""Regression tests for source health reporting; no live network or Telegram calls."""
import importlib
import os
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_test")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    monkeypatch.setattr(mod, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod, "save_state", lambda: None)
    mod.SESSION_STATS.clear()
    mod.SESSION_STATS.update({"src": {}, "sent": 0, "ai_offtopic": 0, "ai_dup": 0, "ai": {}})
    yield mod
    sys.path.remove(ROOT)


def test_robots_block_is_not_recorded_as_success(bot, monkeypatch):
    home = "https://blocked.example/"
    monkeypatch.setattr(bot, "resolve_source", lambda *_a, **_k: {
        "type": "page", "url": home, "name": "Blocked"
    })
    monkeypatch.setattr(bot, "robots_allows", lambda _url: False)

    assert bot.fetch_source(home, "Blocked") == []

    health = bot.STATE["health"]["src:" + home]
    assert health["fail"] == 1
    assert health["ok"] == 0
    assert health["skip_until"] > bot.time.time()
    stats = bot.SESSION_STATS["src"]["src:" + home]
    assert stats["fail"] == 1
    assert stats["ok"] == 0


def test_telegram_channel_is_in_session_source_stats(bot, monkeypatch):
    username = "sample_channel"
    bot.STATE["channels"] = [{"u": username, "title": "Sample", "official": True}]
    reader = SimpleNamespace(fetch=lambda _username, _limit: [
        {"text": "Important policy update", "id": 123, "ts": 1_795_000_000,
         "channel": "Sample", "photo": None}
    ])
    monkeypatch.setattr(bot, "tg_reader", SimpleNamespace(get_reader=lambda: reader))
    monkeypatch.setattr(bot, "web_reader", None)

    items = bot.fetch_channel(username)

    assert len(items) == 1
    stats = bot.SESSION_STATS["src"]["tgch:" + username]
    assert stats["ok"] == 1
    assert stats["fail"] == 0
    assert stats["n"] == 1


def test_telegram_channel_failure_is_counted(bot, monkeypatch):
    username = "broken_channel"
    bot.STATE["channels"] = [{"u": username, "title": "Broken", "official": True}]

    def fail(_username, _limit):
        raise RuntimeError("reader unavailable")

    monkeypatch.setattr(bot, "tg_reader", SimpleNamespace(get_reader=lambda: SimpleNamespace(fetch=fail)))
    monkeypatch.setattr(bot, "web_reader", None)

    assert bot.fetch_channel(username) == []
    stats = bot.SESSION_STATS["src"]["tgch:" + username]
    assert stats["fail"] == 1
    assert stats["ok"] == 0
