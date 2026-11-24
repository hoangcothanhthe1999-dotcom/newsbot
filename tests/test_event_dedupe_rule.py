import bot


def test_tap_tran_hai_tieu_de_khac_nhau_la_trung():
    a = "Cambodia and China to launch 15-day Golden Dragon military exercise"
    b = "Cambodia, China to Begin Joint Military Exercises on November 25"
    assert bot.same_event_rule(a, b)
    assert bot.same_event_rule(b, "Cambodia, China to Hold Golden Dragon Military Exercise in Late November")


def test_khong_nuot_tin_khac_su_kien():
    a = "Cambodia and China to launch 15-day Golden Dragon military exercise"
    assert not bot.same_event_rule(a, "Cambodia and Japan hold joint military exercise")      # nước khác
    assert not bot.same_event_rule(a, "Cambodia and China sign trade agreement")             # không phải tập trận
    assert not bot.same_event_rule(a, "Thailand army exercise near border")                  # chỉ 1 nước
    assert not bot.same_event_rule("Cambodia hosts exercise", "Cambodia hosts exercise")     # <2 nước: để AI quyết


def test_filter_new_bo_ban_den_sau(monkeypatch):
    cs = {"_id": "1", "sent": {}, "titles": [[["x"], __import__("time").time(), "Cambodia and China to launch 15-day Golden Dragon military exercise"]]}
    it = {"id": "n1", "title": "Cambodia, China to Begin Joint Military Exercises on November 25", "ts": None, "desc": "",
          "source": "Cambodianess", "link": "l", "domain": "cambodianess.com"}
    monkeypatch.setattr(bot, "drop_irrelevant", lambda e: (e, []))
    monkeypatch.setattr(bot, "ai_dedupe", lambda e, s: (e, []))
    assert bot.filter_new(cs, {}, [(it, {"t"})], __import__("time").time()) == []
    it2 = {**it, "id": "n2", "title": "Cambodia and Japan hold joint military exercise"}
    assert len(bot.filter_new(cs, {}, [(it2, {"t"})], __import__("time").time())) == 1
