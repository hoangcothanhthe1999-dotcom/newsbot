"""Test offline: sổ quyết định JSONL và investigate.py."""
import importlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.setenv("DECISIONS_FILE", str(tmp_path / "d.jsonl"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    monkeypatch.setattr(mod, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod, "save_state", lambda: None)
    yield mod
    sys.path.remove(ROOT)


def _read(bot):
    with open(bot.DECISIONS_FILE, encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def test_trace_writes_one_line_and_dedupes(bot):
    it = {"title": "Bài thử", "link": "https://a.example/x?utm=1&token=SECRET", "source": "A"}
    bot.trace("age", "dropped", "too_old", it, age_h=8.4)
    bot.trace("age", "dropped", "too_old", it, age_h=8.4)
    recs = _read(bot)
    assert len(recs) == 1
    assert recs[0]["reason"] == "too_old" and recs[0]["age_h"] == 8.4
    assert "SECRET" not in json.dumps(recs[0]) and "utm" not in recs[0]["url"]


def test_stale_item_is_traced(bot):
    import time
    now = time.time()
    it = {"ts": now - 20 * 3600, "title": "Cũ", "link": "https://b.example/y", "source": "B"}
    assert not bot.fresh(it, now)
    assert _read(bot)[0]["reason"] == "too_old"


def test_trace_never_raises(bot, monkeypatch):
    monkeypatch.setattr(bot, "DECISIONS_FILE", "/nonexistent-dir/x.jsonl")
    bot.trace("age", "dropped", "too_old", {"title": "x"})


def test_investigate_finds_by_title(bot):
    sys.path.insert(0, ROOT)
    import investigate
    bot.trace("keyword", "dropped", "keyword_mismatch", {"title": "Cambodia border talks", "link": "https://c.example/z", "source": "C"})
    hits = investigate.search("border", list(investigate.load([bot.DECISIONS_FILE])))
    assert hits and hits[0]["reason"] == "keyword_mismatch"
