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


def test_deliver_groups_night_items_into_one_list(monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send", lambda cid, text, *a, **k: sent.append(text) or {"message_id": 1})
    monkeypatch.setattr(bot, "fmt_item", lambda it, tags, summ: "ITEM " + it["id"])
    monkeypatch.setattr(bot, "item_kb", lambda it: None)
    monkeypatch.setattr(bot, "store_item", lambda *a, **k: None)
    monkeypatch.setattr(bot, "remember_sent", lambda *a, **k: None)
    monkeypatch.setattr(bot, "claim_send", lambda cs, it: True)
    monkeypatch.setattr(bot, "queue_summary", lambda *a, **k: None)
    monkeypatch.setattr(bot, "should_ring", lambda cs, it: False)
    monkeypatch.setattr(bot, "save_state", lambda: None)
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    mk = lambda i, h, d: ({"id": i, "title": i, "link": "http://x/" + i, "source": "s", "ts": ts_vn(h, d)}, ["t"])
    entries = [mk("day1", 8, 24), mk("night1", 22, 23), mk("night2", 3, 24)]
    bot.deliver("1", {"titles": [], "sent": {}}, {"summary": False, "topics": []}, entries, 0.0)
    assert len(sent) == 2
    lst = sent[0]
    assert lst.startswith("🌙") and "2 tin" in lst
    assert lst.count("🌙 ") == 3 and lst.index("night1") < lst.index("night2")
    assert "day1" not in lst
    assert sent[1] == "ITEM day1"


def test_night_items_are_traced(monkeypatch):
    traced = []
    monkeypatch.setattr(bot, "send", lambda *a, **k: {"message_id": 1})
    monkeypatch.setattr(bot, "trace", lambda stage, status, reason, it, **kw: traced.append((stage, status, reason, it["id"])))
    monkeypatch.setattr(bot, "store_item", lambda *a, **k: None)
    monkeypatch.setattr(bot, "remember_sent", lambda *a, **k: None)
    monkeypatch.setattr(bot, "save_state", lambda: None)
    it = {"id": "n1", "title": "n1", "link": "http://x/n1", "source": "s", "ts": ts_vn(22, 23)}
    bot.deliver("1", {"titles": [], "sent": {}}, {"summary": False, "topics": []}, [(it, ["t"])], 0.0)
    assert ("send", "sent", "sent_night_list", "n1") in traced


def test_night_send_failure_not_marked_sent(monkeypatch):
    marked = []
    monkeypatch.setattr(bot, "send", lambda *a, **k: None)
    monkeypatch.setattr(bot, "trace", lambda *a, **k: None)
    monkeypatch.setattr(bot, "store_item", lambda *a, **k: marked.append("store"))
    monkeypatch.setattr(bot, "remember_sent", lambda *a, **k: marked.append("remember"))
    monkeypatch.setattr(bot, "save_state", lambda: None)
    it = {"id": "n2", "title": "n2", "link": "http://x/n2", "source": "s", "ts": ts_vn(22, 23)}
    bot.deliver("1", {"titles": [], "sent": {}}, {"summary": False, "topics": []}, [(it, ["t"])], 0.0)
    assert marked == []


def test_ledger_records_all_paths(monkeypatch):
    traced = []
    monkeypatch.setattr(bot, "trace", lambda stage, status, reason, it, **kw: traced.append((stage, status, reason, it["id"], kw)))
    monkeypatch.setattr(bot, "send", lambda *a, **k: {"message_id": 7})
    monkeypatch.setattr(bot, "store_item", lambda *a, **k: None)
    monkeypatch.setattr(bot, "remember_sent", lambda *a, **k: None)
    monkeypatch.setattr(bot, "save_state", lambda: None)
    monkeypatch.setattr(bot, "claim_send", lambda cs, it: True)
    monkeypatch.setattr(bot, "queue_summary", lambda *a, **k: None)
    monkeypatch.setattr(bot, "should_ring", lambda cs, it: False)
    monkeypatch.setattr(bot, "fmt_item", lambda *a: "x")
    monkeypatch.setattr(bot, "item_kb", lambda it: None)
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    mk = lambda i, h, d: ({"id": i, "title": i, "link": "http://x/" + i, "source": "s", "ts": ts_vn(h, d)}, ["t"])
    bot.deliver("1", {"titles": [], "sent": {}}, {"summary": False, "topics": []}, [mk("d", 8, 24), mk("n", 22, 23)], 0.0)
    night = next(t for t in traced if t[2] == "sent_night_list")
    assert night[4]["pos"] == 1 and night[4]["of"] == 1 and night[4]["pub"] == "23/11 22:00"
    day = next(t for t in traced if t[2] == "sent")
    assert day[4]["msg"] == 7


def test_title_dup_is_traced(monkeypatch):
    traced = []
    monkeypatch.setattr(bot, "trace", lambda stage, status, reason, it, **kw: traced.append((stage, reason)))
    it = {"id": "a", "title": "Cambodia border talks resume today", "desc": "", "ts": 1.0, "source": "s", "domain": "d"}
    cs = {"titles": [[sorted(bot.title_tokens(it["title"])), 1.0, it["title"]]], "sent": {}, "_id": "1"}
    bot.filter_new(cs, {"topics": []}, [(it, ["x"])], 10.0)
    assert ("title_dedupe", "duplicate_title") in traced
