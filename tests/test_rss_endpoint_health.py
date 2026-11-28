"""Regression tests for RSS endpoint health propagation."""
import importlib
import os
import sys

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


def test_rss_endpoint_failure_is_not_hidden_by_homepage_success(bot, monkeypatch):
    home = "https://rss-failure.example/"
    feed = "https://rss-failure.example/feed.xml"
    monkeypatch.setattr(bot, "resolve_source", lambda *_a, **_k: {
        "type": "rss", "url": feed, "name": "RSS Failure"
    })

    def failed_feed(url):
        assert url == feed
        bot.mark_fail(url, "HTTP 502")
        return [{"id": "stale", "title": "Cached headline"}]

    monkeypatch.setattr(bot, "fetch_feed", failed_feed)
    items = bot.fetch_source(home, "RSS Failure")

    assert items and items[0]["id"] == "stale"
    assert bot.STATE["health"][feed]["fail"] == 1
    assert bot.STATE["health"]["src:" + home]["fail"] == 1
    assert bot.STATE["health"]["src:" + home]["ok"] == 0
    assert bot.SESSION_STATS["src"]["rss:" + feed]["fail"] == 1
    assert bot.SESSION_STATS["src"]["src:" + home]["fail"] == 1


def test_valid_empty_rss_is_not_misclassified_as_failure(bot, monkeypatch):
    home = "https://empty-feed.example/"
    feed = "https://empty-feed.example/feed.xml"
    monkeypatch.setattr(bot, "resolve_source", lambda *_a, **_k: {
        "type": "rss", "url": feed, "name": "Empty Feed"
    })
    monkeypatch.setattr(bot, "fetch_feed", lambda _url: [])

    assert bot.fetch_source(home, "Empty Feed") == []
    assert bot.STATE["health"]["src:" + home]["ok"] == 1
    assert bot.STATE["health"]["src:" + home]["fail"] == 0
    assert bot.SESSION_STATS["src"]["rss:" + feed]["ok"] == 1
