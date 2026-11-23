"""Test offline: cổng từ khóa của collect_keyword không chặn tin nguồn chính thức; mở rộng 'Cambodia diplomacy'."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KW = "Campuchia: chính trị – quân sự – ngoại giao – kinh tế"
KX = {"smart": True, "title": "t", "vi": ["campuchia + chính trị", "campuchia + ngoại giao"],
      "gq": [], "en": ["Cambodia politics", "Cambodia military"], "desc": "d", "lang": "vi", "native": [], "v": 2}


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    monkeypatch.setattr(mod, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod, "save_state", lambda: None)
    mod.STATE["kx"][KW] = dict(KX)
    mod.SESSION_STATS.pop("kw_gate", None)
    yield mod
    sys.path.remove(ROOT)


def item(now, title, official, source="Nguồn", domain="t.me"):
    return {"id": title[:8], "title": title, "desc": "", "link": "https://t.me/x/1", "source": source,
            "domain": domain, "ts": now - 600, "gnews": False, "vn": False, "lang": "en", "official": official}


def run(bot, items):
    now = 1_000_000.0
    its = [item(now, t, o, s) for t, o, s in items]
    return [i["title"] for i in bot.collect_keyword(KW, {"tgch:x": its}, now)]


def test_official_item_without_keyword_passes_gate(bot):
    got = run(bot, [("Samdech Hun Sen receives the Chinese Ambassador", True, "MFAIC"),
                    ("ព្រះមហាក្សត្រទទួលអ្នកតំណាង", True, "MFAIC")])
    assert len(got) == 2


def test_non_official_item_without_keyword_still_blocked_and_counted(bot):
    got = run(bot, [("Local football club wins cup", False, "Fresh News")])
    assert got == []
    assert bot.SESSION_STATS["kw_gate"] == {"Fresh News": 1}


def test_non_official_with_keyword_passes(bot):
    assert run(bot, [("Cambodia politics heat up", False, "Fresh News")]) == ["Cambodia politics heat up"]


def test_diplomacy_expansion_added_once(bot):
    en = bot.kw_expansion(KW)["en"]
    assert en.count("Cambodia diplomacy") == 1
    bot.STATE["kx"][KW]["en"].append("Cambodia diplomacy")
    assert bot.kw_expansion(KW)["en"].count("Cambodia diplomacy") == 1
