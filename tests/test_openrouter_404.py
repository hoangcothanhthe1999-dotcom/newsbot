import bot


class _R:
    status_code = 404
    text = "unavailable for free"

    def __init__(self):
        self.headers = {}


def test_404_tat_openrouter_mot_gio(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "OPENROUTER_KEY", "k")
    monkeypatch.setitem(bot._orr, "off_until", 0.0)
    monkeypatch.setitem(bot._orr, "last", 0.0)
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    monkeypatch.setattr(bot.requests, "post", lambda *a, **k: calls.append(1) or _R())
    assert bot._openrouter_call("x") is None
    assert bot._openrouter_call("x") is None
    assert len(calls) == 1
