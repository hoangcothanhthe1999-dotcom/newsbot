"""Test offline cho các sửa lỗi audit bảo mật 22/11/2026 (không gọi mạng thật)."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE_TOKEN = "123456:FAKE-TOKEN_abcDEF"
SENT = []   # các tin bot "gửi" trong test (send() được thay bằng hàm ghi lại)


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    monkeypatch.setattr(mod, "STATE_FILE", str(tmp_path / "state.json"))   # test không được ghi state.json thật
    monkeypatch.setattr(mod, "save_state", lambda: None)
    mod.STATE["owner"] = "111"
    mod.STATE["users"] = {}
    mod._DENIED_AT.clear()
    SENT.clear()
    monkeypatch.setattr(mod, "send", lambda cid, text, *a, **k: SENT.append((cid, text)))
    yield mod
    sys.path.remove(ROOT)


def msg(uid, text="/start", chat_type="private", cid=None):
    return {"from": {"id": uid, "first_name": "X"}, "chat": {"id": cid or uid, "type": chat_type}, "text": text}


def test_scrub_removes_token(bot):
    err = f"Max retries exceeded with url: /bot{FAKE_TOKEN}/getUpdates (Caused by ...)"
    out = bot._scrub_tg(err)
    assert FAKE_TOKEN not in out and "FAKE-TOKEN" not in out


def test_scrub_removes_unknown_token_shape(bot):
    out = bot._scrub_tg("url: /bot999999:OTHER-secret_x/sendMessage")
    assert "OTHER" not in out


def test_group_chat_ignored_even_for_owner(bot):
    bot.handle_message(msg(111, chat_type="group", cid=-100))
    assert SENT == []
    assert "-100" not in bot.STATE["chats"]


def test_stranger_gets_short_refusal_and_owner_not_messaged(bot):
    bot.handle_message(msg(222))
    assert [c for c, _ in SENT] == [222]
    assert bot.STATE["requests"] == {}


def test_stranger_refusal_rate_limited(bot):
    bot.handle_message(msg(222))
    bot.handle_message(msg(222))
    assert len(SENT) == 1


def test_owner_still_served(bot):
    bot.handle_message(msg(111, "/tat"))
    assert SENT and bot.STATE["chats"]["111"]["paused"] is True


def test_no_owner_claim_on_actions(bot, monkeypatch):
    bot.STATE["owner"] = None
    monkeypatch.setattr(bot, "IS_ACTIONS", True)
    assert bot.allowed(333) is False
    assert bot.STATE["owner"] is None


def test_owner_claim_still_works_locally(bot, monkeypatch):
    bot.STATE["owner"] = None
    monkeypatch.setattr(bot, "IS_ACTIONS", False)
    monkeypatch.setattr(bot, "ALLOWED_USERS", set())
    assert bot.allowed(333) is True
    assert bot.STATE["owner"] == "333"
