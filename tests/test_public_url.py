"""Test offline: chặn tải link bài tới địa chỉ không công khai (SSRF)."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    yield mod
    sys.path.remove(ROOT)


@pytest.mark.parametrize("u", ["http://127.0.0.1/x", "http://169.254.169.254/latest", "http://10.0.0.5/",
                               "http://[::1]/", "file:///etc/passwd", "ftp://example.com/", "https://u:p@93.184.216.34/"])
def test_blocks_non_public(bot, u):
    assert bot.public_url_ok(u) is False


def test_allows_public_ip(bot):
    assert bot.public_url_ok("https://93.184.216.34/a") is True


def test_redirect_to_private_is_refused(bot, monkeypatch):
    r302 = type("R", (), {"status_code": 302, "headers": {"Location": "http://169.254.169.254/"}})()
    monkeypatch.setattr(bot.HTTP, "get", lambda *a, **k: r302)
    with pytest.raises(RuntimeError):
        bot.safe_get("https://93.184.216.34/a")
