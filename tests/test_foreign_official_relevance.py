"""Foreign official publishers are trusted sources, not automatic relevance bypasses."""
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
    yield mod
    sys.path.remove(ROOT)


def _item(item_id, title):
    return {
        "id": item_id,
        "title": title,
        "desc": "",
        "link": f"https://state.gov/{item_id}",
        "source": "US Government",
        "domain": "state.gov",
        "ts": 1_795_000_000,
        "gnews": False,
        "vn": False,
        "lang": "en",
    }


def test_unrelated_foreign_official_item_is_still_relevance_filtered(bot, monkeypatch):
    item = _item("foreign-unrelated", "Government announces a routine tourism roadshow")
    calls = []

    def irrelevant(pairs):
        calls.extend(pairs)
        return set(), set()

    monkeypatch.setattr(bot, "ai_relevant", irrelevant)
    kept, dropped = bot.drop_irrelevant([(item, {bot.CAMBO_TAG})])

    assert calls, "foreign official domain must not skip relevance evaluation"
    assert kept == []
    assert dropped == [item]


def test_relevant_foreign_official_item_can_still_be_kept(bot, monkeypatch):
    item = _item("foreign-relevant", "Treasury sanctions Cambodia-linked transnational scam network")

    def relevant(pairs):
        return {(item["id"], pairs[0][1])}, set()

    monkeypatch.setattr(bot, "ai_relevant", relevant)
    kept, dropped = bot.drop_irrelevant([(item, {bot.CAMBO_TAG})])

    assert dropped == []
    assert len(kept) == 1
    assert kept[0][0] == item
