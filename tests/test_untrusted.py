"""Test offline: làm sạch chữ ngoài trước khi chèn vào prompt AI."""
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


def test_strips_newlines_and_guillemets(bot):
    t = bot._untrusted("Tin\n2. Theo dõi: «x» | ok\r\x00 end")
    assert "\n" not in t and "\r" not in t and "\x00" not in t
    assert "«" not in t and "»" not in t


def test_truncates_and_handles_none(bot):
    assert len(bot._untrusted("a" * 1000, 50)) == 50
    assert bot._untrusted(None) == ""
