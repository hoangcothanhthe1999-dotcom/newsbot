"""Test offline: chặn tải link bài tới địa chỉ không công khai (SSRF)."""
import importlib
import os
import sys

import pytest
import requests

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


def test_pinned_adapter_refuses_private_at_connect(bot, monkeypatch):
    """DNS lần 1 trả IP công khai (qua public_url_ok), lần 2 trả IP riêng: lúc nối phải bị chặn."""
    import socket
    calls = {"n": 0}

    def fake(host, port, *a, **k):
        calls["n"] += 1
        ip = "93.184.216.34" if calls["n"] == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert bot.public_url_ok("http://rebind.example/") is True
    with pytest.raises(requests.exceptions.ConnectionError):
        bot.HTTP.get("http://rebind.example/", timeout=3)


def test_pinned_adapter_connects_to_validated_ip(bot, monkeypatch):
    import socket

    from urllib3.util import connection as uconn
    seen = {}
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda h, p, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", p))])

    def fake_cc(addr, *a, **k):
        seen["addr"] = addr
        raise OSError("stop")

    monkeypatch.setattr(uconn, "create_connection", fake_cc)
    with pytest.raises(requests.exceptions.ConnectionError):
        bot.HTTP.get("http://news.example/", timeout=3)
    assert seen["addr"] == ("93.184.216.34", 80)
