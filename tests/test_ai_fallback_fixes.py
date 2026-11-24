"""Test offline cho sửa lỗi audit 24/11/2026: Groq/Cloudflare dự phòng (không gọi mạng thật)."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_SET_CALLS = []   # các lần ai_set(ok, msg) trong test


class FakeResp:
    def __init__(self, status, data=None, text="", headers=None):
        self.status_code = status
        self._data = data
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    monkeypatch.setattr(mod, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod, "save_state", lambda: None)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(mod, "GROQ_KEY", "fake-groq")
    monkeypatch.setattr(mod, "CF_KEY", "fake-cf")
    monkeypatch.setattr(mod, "CF_ACCOUNT", "acc-SECRET-ID")
    mod._groq.update(off_until=0.0, last=0.0)
    mod._cf.update(off_until=0.0, last=0.0)
    AI_SET_CALLS.clear()
    monkeypatch.setattr(mod, "ai_set", lambda ok, msg: AI_SET_CALLS.append((ok, msg)))
    yield mod
    sys.path.remove(ROOT)


def test_cf_sends_max_tokens(bot, monkeypatch):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["body"] = json
        return FakeResp(200, {"result": {"response": '{"ok": 1}'}})
    monkeypatch.setattr(bot.requests, "post", fake_post)
    assert bot._cf_call("p") == '{"ok": 1}'
    assert sent["body"]["max_tokens"] >= 1024
    assert AI_SET_CALLS and AI_SET_CALLS[-1][0] is True


def test_cf_network_error_does_not_log_account(bot, monkeypatch, caplog):
    def boom(*a, **k):
        raise bot.requests.ConnectionError("Max retries for url /client/v4/accounts/acc-SECRET-ID/ai/run")
    monkeypatch.setattr(bot.requests, "post", boom)
    with caplog.at_level("WARNING"):
        assert bot._cf_call("p") is None
    assert "acc-SECRET-ID" not in caplog.text


def test_cf_empty_response_not_reported_ok(bot, monkeypatch):
    monkeypatch.setattr(bot.requests, "post", lambda *a, **k: FakeResp(200, {"result": {"response": ""}}))
    assert bot._cf_call("p") is None
    assert not AI_SET_CALLS


def test_groq_bad_json_not_reported_ok(bot, monkeypatch):
    monkeypatch.setattr(bot.requests, "post", lambda *a, **k: FakeResp(200, {"choices": []}))
    assert bot._groq_call("p") is None
    assert not AI_SET_CALLS


def test_groq_null_content_not_reported_ok(bot, monkeypatch):
    monkeypatch.setattr(bot.requests, "post",
                        lambda *a, **k: FakeResp(200, {"choices": [{"message": {"content": None}}]}))
    assert bot._groq_call("p") is None
    assert not AI_SET_CALLS


def test_groq_ok(bot, monkeypatch):
    monkeypatch.setattr(bot.requests, "post",
                        lambda *a, **k: FakeResp(200, {"choices": [{"message": {"content": "[1]"}}]}))
    assert bot._groq_call("p") == "[1]"
    assert AI_SET_CALLS[-1][0] is True


@pytest.mark.parametrize("code,min_off", [(413, 500), (500, 60), (503, 60)])
def test_groq_pauses_on_413_and_5xx(bot, monkeypatch, code, min_off):
    monkeypatch.setattr(bot.requests, "post", lambda *a, **k: FakeResp(code, text="err"))
    t0 = bot.time.time()
    assert bot._groq_call("p") is None
    assert bot._groq["off_until"] >= t0 + min_off


def test_groq_400_no_pause(bot, monkeypatch):
    monkeypatch.setattr(bot.requests, "post", lambda *a, **k: FakeResp(400, text="bad"))
    assert bot._groq_call("p") is None
    assert bot._groq["off_until"] == 0.0
