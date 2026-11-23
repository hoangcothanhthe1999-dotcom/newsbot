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


def _st(channels, meta=None):
    return {"channels": [dict(c) for c in channels], "meta": dict(meta or {})}


def test_first_run_marks_current_defaults_without_change(bot, monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_CHANNELS", [{"u": "A"}, {"u": "B"}])
    st = _st([{"u": "A"}], {"seed_channels": 1})
    assert bot.merge_default_channels(st) == []
    assert [c["u"] for c in st["channels"]] == ["A"]  # B đã bị gỡ trước đó, không tự quay lại
    assert st["meta"]["seeded_ch"] == ["a", "b"]


def test_new_default_channel_is_added_once(bot, monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_CHANNELS", [{"u": "A"}, {"u": "New", "official": True}])
    st = _st([{"u": "A"}], {"seeded_ch": ["a"]})
    assert bot.merge_default_channels(st) == ["New"]
    assert [c["u"] for c in st["channels"]] == ["A", "New"]
    st["channels"] = [c for c in st["channels"] if c["u"] != "New"]  # chủ bot gỡ kênh
    assert bot.merge_default_channels(st) == []
    assert [c["u"] for c in st["channels"]] == ["A"]


def test_no_duplicate_when_already_present_case_insensitive(bot, monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_CHANNELS", [{"u": "A"}, {"u": "NEW"}])
    st = _st([{"u": "A"}, {"u": "new"}], {"seeded_ch": ["a"]})
    assert bot.merge_default_channels(st) == []
    assert len(st["channels"]) == 2
    assert st["meta"]["seeded_ch"] == ["a", "new"]


def test_empty_defaults_is_noop(bot, monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_CHANNELS", [])
    st = _st([])
    assert bot.merge_default_channels(st) == []
