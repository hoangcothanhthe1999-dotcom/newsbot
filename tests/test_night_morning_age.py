"""Tin đêm (16h hôm trước – 06h): phiên sáng (<08h VN) nhận mọi nguồn tới 16 giờ tuổi; phiên ban ngày giữ giới hạn cũ."""
import importlib
import os
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.setenv("DECISIONS_FILE", str(tmp_path / "d.jsonl"))
    monkeypatch.setenv("MAX_AGE_HOURS", "6")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    mod.STATE["last_end"] = 0
    yield mod
    sys.path.remove(ROOT)


def ts(bot, day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=bot.VN_TZ).timestamp()


def test_morning_session_accepts_old_night_item(bot):
    now = ts(bot, 25, 6, 5)
    assert bot.fresh({"ts": ts(bot, 24, 20, 0), "title": "t", "link": "l"}, now)      # 10h tuổi, đăng 20:00
    assert bot.fresh({"ts": ts(bot, 24, 16, 30), "title": "t", "link": "l"}, now)     # ~13.5h, đăng 16:30


def test_morning_session_still_rejects_daytime_and_too_old(bot):
    now = ts(bot, 25, 6, 5)
    assert not bot.fresh({"ts": ts(bot, 24, 15, 0), "title": "t", "link": "l"}, now)  # đăng ban ngày (không phải đêm), 15h
    assert not bot.fresh({"ts": ts(bot, 24, 13, 0), "title": "t", "link": "l"}, now)  # quá 16h
    assert not bot.fresh({"ts": ts(bot, 23, 22, 0), "title": "t", "link": "l"}, now)  # 32h


def test_daytime_session_keeps_old_limit(bot):
    now = ts(bot, 25, 10, 5)
    assert not bot.fresh({"ts": ts(bot, 24, 20, 0), "title": "t", "link": "l"}, now)  # đêm qua, 14h, phiên 10h: giữ giới hạn 6h
    assert bot.fresh({"ts": ts(bot, 25, 7, 0), "title": "t", "link": "l"}, now)
