"""Test offline: fresh() đếm và ghi log bài chính thức bị bỏ vì quá tuổi."""
import importlib
import logging
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


def test_stale_official_logged(bot, caplog):
    now = 1_000_000_000
    old = {"ts": now - 40 * 3600, "official": True, "source": "MFAIC", "title": "Bài cũ"}
    with caplog.at_level(logging.INFO, logger="newsbot"):
        assert bot.fresh(old, now) is False
    assert bot.STALE_DROPPED["n"] == 1
    assert "quá tuổi" in caplog.text and "MFAIC" in caplog.text


def test_fresh_item_not_counted(bot):
    now = 1_000_000_000
    assert bot.fresh({"ts": now - 3600}, now) is True
    assert bot.STALE_DROPPED["n"] == 0
