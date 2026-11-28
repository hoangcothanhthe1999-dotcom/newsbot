"""Regression tests: AI-unavailable fallback must not auto-keep every official source."""
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


def item(title, domain, source="Official source", official=False):
    return {
        "id": "fallback-case",
        "title": title,
        "desc": "",
        "link": f"https://{domain}/story",
        "source": source,
        "domain": domain,
        "ts": 1_795_000_000,
        "gnews": False,
        "vn": False,
        "lang": "en",
        "official": official,
    }


def test_cambodian_official_routine_training_is_not_auto_kept(bot):
    story = item(
        "Ministry of Finance holds tax administration training workshop for provincial staff",
        "mef.gov.kh",
    )
    assert bot.item_tier(story) == 1
    assert bot.fallback_ok(story) is False


def test_cambodian_official_national_policy_is_kept(bot):
    story = item(
        "Royal Government approves new national budget and tax policy",
        "pressocm.gov.kh",
    )
    assert bot.fallback_ok(story) is True


def test_cambodian_official_border_and_ceasefire_statement_is_kept(bot):
    story = item(
        "MFAIC issues statement on Cambodia-Thailand border ceasefire",
        "mfaic.gov.kh",
    )
    assert bot.fallback_ok(story) is True


def test_thai_military_procurement_is_kept_without_cambodia_keyword(bot):
    story = item(
        "Royal Thai Army plans to procure new tanks and artillery",
        "www.mod.go.th",
    )
    assert bot.fallback_ok(story) is True


def test_unrelated_thai_government_economic_roadshow_is_dropped(bot):
    story = item(
        "Thailand launches digital economy roadshow for local businesses",
        "www.thailand.go.th",
    )
    assert bot.item_tier(story) == 1
    assert bot.fallback_ok(story) is False


def test_foreign_official_cambodia_sanctions_story_is_kept(bot):
    story = item(
        "Treasury sanctions Cambodia-linked transnational scam network",
        "home.treasury.gov",
    )
    assert bot.fallback_ok(story) is True


def test_unrelated_foreign_official_passport_notice_is_dropped(bot):
    story = item(
        "State Department announces routine passport renewal procedures",
        "www.state.gov",
    )
    assert bot.fallback_ok(story) is False


def test_cambodian_official_telegram_cultural_exhibition_is_dropped(bot):
    story = item(
        "Ministry hosts cultural exhibition in Phnom Penh",
        "t.me",
        source="Bộ Nội vụ Campuchia",
        official=True,
    )
    assert bot.item_tier(story) == 1
    assert bot.fallback_ok(story) is False


def test_cambodian_defence_channel_border_deployment_is_kept(bot):
    story = item(
        "Cambodian Army reports new deployment near Cambodia-Thailand border",
        "t.me",
        source="Bộ Quốc phòng Campuchia",
        official=True,
    )
    assert bot.fallback_ok(story) is True


def test_unknown_official_channel_does_not_pass_only_by_official_flag(bot):
    story = item(
        "Official channel announces staff training workshop",
        "t.me",
        source="Official Channel",
        official=True,
    )
    assert bot.fallback_ok(story) is False


def test_cambodian_mainstream_border_report_is_kept(bot):
    story = item(
        "Cambodian army reports troop deployment near border",
        "www.khmertimeskh.com",
        source="Khmer Times",
    )
    assert bot.fallback_ok(story) is True


def test_thai_military_routine_staff_training_is_dropped(bot):
    story = item(
        "Royal Thai Army holds annual staff training workshop",
        "www.mod.go.th",
    )
    assert bot.fallback_ok(story) is False


def test_thai_military_exercise_and_border_deployment_are_kept(bot):
    story = item(
        "Royal Thai Army conducts military exercise near the border",
        "www.mod.go.th",
    )
    assert bot.fallback_ok(story) is True


def test_foreign_official_small_cambodia_trade_workshop_is_dropped(bot):
    story = item(
        "U.S. Embassy hosts a small workshop on Cambodia trade promotion",
        "kh.usembassy.gov",
    )
    assert bot.fallback_ok(story) is False


def test_cambodian_foreign_minister_bilateral_border_meeting_is_kept(bot):
    story = item(
        "Foreign Minister meets ASEAN delegation for Cambodia-Thailand border talks",
        "mfaic.gov.kh",
    )
    assert bot.fallback_ok(story) is True


def test_cambodian_official_minister_at_cultural_exhibition_is_dropped(bot):
    story = item(
        "Minister attends cultural exhibition in Phnom Penh",
        "pressocm.gov.kh",
    )
    assert bot.fallback_ok(story) is False


def test_thai_military_myanmar_border_story_is_dropped_without_cambodia_link(bot):
    story = item(
        "Royal Thai Army secures Myanmar border after new clashes",
        "www.mod.go.th",
    )
    assert bot.fallback_ok(story) is False
