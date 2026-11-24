"""Test offline: Boss không quan tâm biên giới Việt Nam–Campuchia (23/11/2026)."""
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


def _it(title):
    return {"title": title, "desc": "", "domain": "akp.gov.kh"}


def test_vietnam_word_no_longer_hard_pass(bot):
    assert not bot.hard_official(_it("Cambodia Vietnam hold talks on trade"))


def test_thai_border_still_hard_pass(bot):
    assert bot.hard_official(_it("Cambodia Thailand border talks resume"))


def test_ai_desc_excludes_vn_border(bot):
    d = bot.TOPICS["campuchia"]["ai_desc"]
    assert "(Việt Nam–Campuchia và" not in d
    assert "Boss không quan tâm" in d


def test_bilateral_topic_drops_vietnam():
    from sources import TOPICS
    t = TOPICS["doingoai_songphuong"]
    assert "Việt Nam" not in t["name"]
    assert not any("Vietnam" in q for q in t["gnews_en"])
    head, _, loai = t["ai_desc"].partition("LOẠI:")
    assert "Việt Nam" not in head
    assert "Việt Nam – Campuchia" in loai
