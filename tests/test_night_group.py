from datetime import datetime

import bot


def ts_vn(h, d=23):
    return datetime(2026, 11, d, h, 0, tzinfo=bot.VN_TZ).timestamp()


def test_is_night_item_bounds():
    assert bot.is_night_item({"ts": ts_vn(16)})
    assert bot.is_night_item({"ts": ts_vn(23)})
    assert bot.is_night_item({"ts": ts_vn(3, 24)})
    assert bot.is_night_item({"ts": ts_vn(5, 24)})
    assert not bot.is_night_item({"ts": ts_vn(6, 24)})
    assert not bot.is_night_item({"ts": ts_vn(15)})
    assert not bot.is_night_item({"ts": None})


def test_deliver_sends_night_header_then_day_header(monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send", lambda cid, text, *a, **k: sent.append(text) or {"message_id": 1})
    monkeypatch.setattr(bot, "fmt_item", lambda it, tags, summ: "ITEM " + it["id"])
    monkeypatch.setattr(bot, "item_kb", lambda it: None)
    monkeypatch.setattr(bot, "store_item", lambda *a, **k: None)
    monkeypatch.setattr(bot, "claim_send", lambda cs, it: True)
    monkeypatch.setattr(bot, "queue_summary", lambda *a, **k: None)
    monkeypatch.setattr(bot, "should_ring", lambda cs, it: False)
    monkeypatch.setattr(bot, "save_state", lambda: None)
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    mk = lambda i, h, d: ({"id": i, "title": i, "link": "http://x", "source": "s", "ts": ts_vn(h, d)}, ["t"])
    entries = [mk("day1", 8, 24), mk("night1", 22, 23), mk("night2", 3, 24)]
    bot.deliver("1", {"titles": [], "sent": {}}, {"summary": False, "topics": []}, entries, 0.0)
    assert sent[0].startswith("🌙") and "2 tin" in sent[0]
    assert sent[1:3] and all("night" in x for x in sent[1:3])
    assert sent[3].startswith("☀️")
    assert sent[4] == "ITEM day1"
