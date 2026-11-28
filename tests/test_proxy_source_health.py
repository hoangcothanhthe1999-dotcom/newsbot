"""Regression tests for per-source health inside the Apps Script proxy response."""
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
    mod.SESSION_STATS["src"].clear()
    yield mod
    sys.path.remove(ROOT)


def test_proxy_tracks_each_upstream_source_health(bot, monkeypatch):
    monkeypatch.setattr(bot, "APPS_PROXY_URL", "https://script.google.com/macros/s/fake/exec")
    payload = [
        {"source": "ADB", "error": "HTTP 502"},
        {"source": "ASEAN", "title": "Cambodia policy statement", "link": "https://asean.org/story"},
    ]
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr(bot, "_proxy_fetch", lambda _url: response)

    items = bot.fetch_proxy("px:docho")

    assert len(items) == 1
    assert bot.STATE["health"]["px:ADB"]["fail"] == 1
    assert bot.STATE["health"]["px:ADB"]["ok"] == 0
    assert bot.STATE["health"]["px:ASEAN"]["ok"] == 1
    assert bot.STATE["health"]["px:ASEAN"]["fail"] == 0
    assert bot.SESSION_STATS["src"]["px:ADB"]["fail"] == 1
    assert bot.SESSION_STATS["src"]["px:ASEAN"]["ok"] == 1


def test_proxy_empty_relevance_result_still_marks_source_fetch_ok(bot, monkeypatch):
    monkeypatch.setattr(bot, "APPS_PROXY_URL", "https://script.google.com/macros/s/fake/exec")
    payload = [{"source": "ASEAN", "title": "Routine local event", "link": "https://asean.org/story"}]
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr(bot, "_proxy_fetch", lambda _url: response)

    assert bot.fetch_proxy("px:docho") == []
    assert bot.STATE["health"]["px:ASEAN"]["ok"] == 1
    assert bot.STATE["health"]["px:ASEAN"]["fail"] == 0
