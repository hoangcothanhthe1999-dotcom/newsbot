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


@pytest.mark.parametrize("title", [
    "Police seize ketamine as Cambodia announces a new policy to regulate its use",
    "Police seize methamphetamine as government expands addiction treatment services",
])
def test_drug_policy_and_treatment_mentions_are_not_routine_busts(bot, title):
    assert not bot.is_routine_drug_enforcement(_item(title))


def test_explicit_drug_seizure_requires_action_and_substance(bot):
    assert bot.is_routine_drug_enforcement(
        _item("Police seized 40kg of methamphetamine in provincial raid")
    )


@pytest.mark.parametrize("title", [
    "Police seize drugs under a new policy to prevent routine drug busts",
    "Police seize drugs while procedures for reporting drug cases are announced",
])
def test_drug_policy_or_procedure_noun_phrases_are_not_enforcement_actions(bot, title):
    assert not bot.is_routine_drug_enforcement(_item(title))


def test_drug_bust_headline_with_net_action_is_excluded(bot):
    assert bot.is_routine_drug_enforcement(
        _item("Drug bust nets 100kg of ketamine in provincial raid")
    )


@pytest.mark.parametrize("title", [
    "Government reviews online drug sales through the internet network",
    "Cambodia publishes a report on drug networks and internet access",
])
def test_internet_and_network_substrings_are_not_enforcement_actions(bot, title):
    assert not bot.is_routine_drug_enforcement(_item(title))


@pytest.mark.parametrize("title", [
    "Government proposes new regulations on drug arrests",
    "Cambodia reviews rules governing drug raids",
    "Police seize narcotics as new guidelines on enforcement are announced",
])
def test_drug_law_and_procedure_articles_are_not_routine_busts(bot, title):
    assert not bot.is_routine_drug_enforcement(_item(title))


def test_law_enforcement_phrase_does_not_exempt_a_routine_drug_bust(bot):
    story = _item("Police seize 20kg of ketamine in routine operation")
    story["desc"] = "Law enforcement officers said the operation followed existing law."
    assert bot.is_routine_drug_enforcement(story)


@pytest.mark.parametrize("title", [
    "Government proposes new regulations on drug arrests",
    "Cambodia reviews rules governing drug raids",
    "Police seize narcotics as new guidelines on enforcement are announced",
])
def test_contextual_law_and_policy_phrases_are_preserved(bot, title):
    assert not bot.is_routine_drug_enforcement(_item(title))


def test_khmer_policy_exception_is_preserved(bot):
    story = _item("Police seize ketamine in a routine operation")
    story["desc"] = "គោលនយោបាយថ្មីស្តីពីការគ្រប់គ្រងគ្រឿងញៀន"
    assert not bot.is_routine_drug_enforcement(story)


def test_thai_drug_policy_exception_is_preserved(bot):
    story = _item("Police seize methamphetamine in a routine operation")
    story["desc"] = "นโยบายยาเสพติดและการบำบัดยาเสพติด"
    assert not bot.is_routine_drug_enforcement(story)


def test_chinese_drug_policy_exception_is_preserved(bot):
    story = _item("Police seize ketamine in a routine operation")
    story["desc"] = "禁毒政策和药物治疗"
    assert not bot.is_routine_drug_enforcement(story)
