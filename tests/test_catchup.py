"""Test offline: bắt bù bài nguồn chính thức đăng lúc bot nghỉ (fresh())."""
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


H = 3600


def test_official_posted_while_bot_off_is_caught(bot):
    now = 1_000_000.0
    bot.STATE["last_end"] = now - 14 * H            # phiên trước kết thúc 14 giờ trước
    it = {"ts": now - 9 * H, "official": True}      # đăng 9 giờ trước, sau khi phiên trước kết thúc
    assert bot.fresh(it, now, 6) is True


def test_not_official_is_not_caught(bot):
    now = 1_000_000.0
    bot.STATE["last_end"] = now - 14 * H
    assert bot.fresh({"ts": now - 9 * H, "official": False}, now, 6) is False


def test_posted_before_last_end_is_not_caught(bot):
    now = 1_000_000.0
    bot.STATE["last_end"] = now - 3 * H             # bot vừa chạy; bài cũ hơn 6 giờ là bài cũ thật
    assert bot.fresh({"ts": now - 9 * H, "official": True}, now, 6) is False


def test_catchup_is_capped(bot):
    now = 1_000_000.0
    bot.STATE["last_end"] = now - 40 * H
    assert bot.fresh({"ts": now - (bot.CATCHUP_MAX_HOURS + 1) * H, "official": True}, now, 6) is False


def test_no_last_end_disables_catchup(bot):
    now = 1_000_000.0
    bot.STATE["last_end"] = 0
    assert bot.fresh({"ts": now - 9 * H, "official": True}, now, 6) is False


def test_normal_window_and_future_unchanged(bot):
    now = 1_000_000.0
    bot.STATE["last_end"] = 0
    assert bot.fresh({"ts": now - 2 * H, "official": False}, now, 6) is True
    assert bot.fresh({"ts": now + 3 * H, "official": True}, now, 6) is False
    assert bot.fresh({"ts": None}, now, 6) is True
