"""Test offline: ba nhóm khu vực (vũ khí, quân sự Thái, an ninh) cho chat đã bật chủ đề Campuchia."""
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


def test_topics_defined(bot):
    for k in ("vukhi", "quansu_thailan", "anninh_khuvuc"):
        assert k in bot.TOPICS and bot.TOPICS[k]["ai_desc"] and bot.TOPICS[k]["gnews_en"]
    assert len(bot.REGION_TAGS) == 3


def test_eff_topics_adds_without_mutating(bot):
    c = {"topics": ["campuchia"]}
    assert set(bot.eff_topics(c)) == {"campuchia", "vukhi", "quansu_thailan", "anninh_khuvuc"}
    assert c["topics"] == ["campuchia"]
    assert bot.eff_topics({"topics": []}) == []


def test_chat_urls_and_subs_include_region(bot):
    c = {"topics": ["campuchia"], "keywords": [], "scope": {"intl": True}, "langs": [], "sources": []}
    c0 = dict(c, topics=[])
    base = set(bot.topic_urls("campuchia", True))
    assert set(bot.chat_urls(c)) > base
    assert not bot.chat_urls(c0)
    subs = bot.chat_subs(c, {}, 1_000_000.0)
    assert {s[0] for s in subs} == {"t:campuchia", "t:vukhi", "t:quansu_thailan", "t:anninh_khuvuc"}


def test_strict_ok_fail_closed_for_region(bot):
    it = {"title": "x", "desc": "y"}
    for tag in bot.REGION_TAGS:
        assert bot.strict_ok(tag, it) is False
