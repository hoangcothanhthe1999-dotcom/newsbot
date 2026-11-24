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


def _fake_sock(ip):
    class S:
        closed = False

        def getpeername(self):
            return (ip, 443)

        def close(self):
            self.closed = True

    return S()


@pytest.mark.parametrize("ip,ok", [("93.184.216.34", True), ("127.0.0.1", False), ("169.254.169.254", False),
                                   ("10.1.2.3", False), ("::1", False)])
def test_pin_guard_checks_connected_ip(bot, ip, ok):
    sock = _fake_sock(ip)

    class Base:
        def _new_conn(self):
            return sock

    class G(bot._PinGuard, Base):
        pass

    if ok:
        assert G()._new_conn() is sock
        assert sock.closed is False
    else:
        with pytest.raises(OSError):
            G()._new_conn()
        assert sock.closed is True


def test_adapter_installs_guarded_pools(bot):
    pm = bot.HTTP.get_adapter("https://example.com/").poolmanager
    assert issubclass(pm.pool_classes_by_scheme["https"].ConnectionCls, bot._PinGuard)
    assert issubclass(pm.pool_classes_by_scheme["http"].ConnectionCls, bot._PinGuard)
