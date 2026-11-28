"""Regression tests for the approved exclusion of routine drug-enforcement reports."""
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


def _item(title):
    return {"id": "drug-case", "title": title, "desc": "", "link": "https://example.org/story",
            "source": "Phnom Penh Post", "domain": "phnompenhpost.com", "ts": 1_795_000_000,
            "gnews": False, "vn": False, "lang": "en"}


def test_holdout_senior_police_chief_drug_bust_is_excluded(bot):
    item = _item("Senior police chief seizes 874kg of ketamine in largest drug bust")
    assert bot.is_routine_drug_enforcement(item)
    assert bot.pre_decide(bot.CAMBO_TAG, item) is False


@pytest.mark.parametrize("title", [
    "Cambodia-linked cross-border drug trafficking network dismantled",
    "Transnational drug syndicate operating across Cambodia and Thailand exposed",
    "Cambodia launches nationwide campaign against drug trafficking networks",
])
def test_cross_border_or_national_campaign_drug_news_is_not_auto_excluded(bot, title):
    assert not bot.is_routine_drug_enforcement(_item(title))


@pytest.mark.parametrize("title", [
    "Customs police seizes illegal weapons and smuggled electronics at border checkpoint",
    "Forest rangers seized illegal timber and wildlife products in protected zone",
])
def test_non_drug_seizures_are_not_classified_as_drug_enforcement(bot, title):
    assert not bot.is_routine_drug_enforcement(_item(title))


def test_routine_drug_bust_is_excluded_even_when_ai_fallback_would_keep_tier_one(bot, monkeypatch):
    item = _item("Senior police chief seizes 874kg of ketamine in largest drug bust")
    monkeypatch.setattr(bot, "item_tier", lambda _item: 1)
    assert bot.fallback_ok(item) is False
