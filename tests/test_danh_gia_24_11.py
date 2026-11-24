"""Test offline cho các lỗi của đánh giá độc lập 24/11/2026 (L1 gửi lỗi, L2 OpenRouter rỗng, L3 trần Gemini,
L4 ai_dedupe ghi "trùng với", L5 thiếu "ok", L7 JSON web app lạ). Không gọi mạng thật."""
from datetime import datetime

import pytest

import bot


class FakeResp:
    def __init__(self, status, data=None, text="", headers=None):
        self.status_code = status
        self._data = data
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


def ts_vn(h, d=24):
    return datetime(2026, 11, d, h, 0, tzinfo=bot.VN_TZ).timestamp()


@pytest.fixture()
def quiet(monkeypatch):
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    monkeypatch.setattr(bot, "save_state", lambda: None)
    monkeypatch.setattr(bot, "trace", lambda *a, **k: None)
    bot._send_fail.clear()


def _deliver_env(monkeypatch, send):
    monkeypatch.setattr(bot, "send", send)
    monkeypatch.setattr(bot, "fmt_item", lambda it, tags, summ: "ITEM " + it["id"])
    monkeypatch.setattr(bot, "item_kb", lambda it: None)
    monkeypatch.setattr(bot, "queue_summary", lambda *a, **k: None)
    monkeypatch.setattr(bot, "should_ring", lambda cs, it: False)
    stored = []
    monkeypatch.setattr(bot, "store_item", lambda it, *a, **k: stored.append(it["id"]))
    return stored


# ---- L1: tin gửi lỗi không bị đánh dấu "đã gửi"
def test_send_failure_unclaims_item(monkeypatch, quiet):
    stored = _deliver_env(monkeypatch, lambda *a, **k: None)
    cs = {"_id": "1", "titles": [], "sent": {}}
    it = {"id": "d1", "title": "Cambodia border talks resume", "link": "http://x/d1", "source": "s", "ts": ts_vn(9)}
    bot.deliver("1", cs, {"summary": False, "topics": []}, [(it, ["t"])], 0.0)
    assert "d1" not in cs["sent"]
    assert cs["titles"] == []
    assert stored == []


def test_send_failure_gives_up_after_max(monkeypatch, quiet):
    _deliver_env(monkeypatch, lambda *a, **k: None)
    cs = {"_id": "1", "titles": [], "sent": {}}
    it = {"id": "d2", "title": "Hun Manet meets envoy", "link": "http://x/d2", "source": "s", "ts": ts_vn(9)}
    for _ in range(bot.SEND_MAX_FAILS):
        bot.deliver("1", cs, {"summary": False, "topics": []}, [(it, ["t"])], 0.0)
    assert "d2" in cs["sent"]      # quá số lần thì giữ dấu, không thử mãi


def test_send_success_marks_and_stores(monkeypatch, quiet):
    stored = _deliver_env(monkeypatch, lambda *a, **k: {"message_id": 5})
    cs = {"_id": "1", "titles": [], "sent": {}}
    it = {"id": "d3", "title": "Senate session opens", "link": "http://x/d3", "source": "s", "ts": ts_vn(9)}
    bot.deliver("1", cs, {"summary": False, "topics": []}, [(it, ["t"])], 0.0)
    assert "d3" in cs["sent"] and stored == ["d3"]


def test_overflow_failure_not_marked(monkeypatch, quiet):
    def send(cid, text, *a, **k):
        return None if text.startswith("📚") else {"message_id": 1}
    _deliver_env(monkeypatch, send)
    monkeypatch.setattr(bot, "MAX_PER_CYCLE", 1)
    cs = {"_id": "1", "titles": [], "sent": {}}
    a = {"id": "o1", "title": "Alpha topic one", "link": "http://x/o1", "source": "s", "ts": ts_vn(9)}
    b = {"id": "o2", "title": "Beta subject two", "link": "http://x/o2", "source": "s", "ts": ts_vn(10)}
    bot.deliver("1", cs, {"summary": False, "topics": []}, [(a, ["t"]), (b, ["t"])], 0.0)
    assert len(cs["sent"]) == 1     # chỉ tin gửi riêng thành công; tin trong danh sách lỗi chưa đánh dấu


# ---- L2: OpenRouter trả rỗng phải rơi xuống Cloudflare
def test_openrouter_empty_falls_through_to_cf(monkeypatch, quiet):
    monkeypatch.setattr(bot, "GEMINI_KEY", "")
    monkeypatch.setattr(bot, "GROQ_KEY", "")
    monkeypatch.setattr(bot, "OPENROUTER_KEY", "k")
    monkeypatch.setattr(bot, "CF_KEY", "t")
    bot._orr.update(off_until=0.0, last=0.0)
    bot._cf.update(off_until=0.0, last=0.0)
    calls = []

    def post(url, **kw):
        calls.append(url.split("/")[2])
        if "openrouter" in url:
            return FakeResp(200, {"choices": [{"message": {"content": ""}}]})
        return FakeResp(200, {"result": {"response": '[{"i": 1, "ok": true}]'}})
    monkeypatch.setattr(bot.requests, "post", post)
    out = bot.gemini("x")
    assert out == '[{"i": 1, "ok": true}]'
    assert calls == ["openrouter.ai", "api.cloudflare.com"]
    assert "Cloudflare" in bot.AI["status"]


def test_all_empty_returns_none(monkeypatch, quiet):
    monkeypatch.setattr(bot, "GEMINI_KEY", "")
    monkeypatch.setattr(bot, "GROQ_KEY", "")
    monkeypatch.setattr(bot, "OPENROUTER_KEY", "k")
    monkeypatch.setattr(bot, "CF_KEY", "")
    bot._orr.update(off_until=0.0, last=0.0)
    monkeypatch.setattr(bot.requests, "post", lambda url, **kw: FakeResp(200, {"choices": [{"message": {"content": None}}]}))
    assert bot.gemini("x") is None


# ---- L3: phần Gemini không vượt trần thời gian, lỗi mạng không thử hết 6 model
def test_gemini_network_error_stops_early(monkeypatch, quiet):
    monkeypatch.setattr(bot, "GEMINI_KEY", "g")
    calls = []

    def post(url, **kw):
        calls.append(url)
        raise bot.requests.exceptions.ConnectTimeout("timeout")
    monkeypatch.setattr(bot.requests, "post", post)
    assert bot._gemini_call("x") is None
    assert len(calls) == 2           # 1 lần thử lại, không đổi sang 5 model khác


def test_gemini_budget_exhausted(monkeypatch, quiet):
    monkeypatch.setattr(bot, "GEMINI_KEY", "g")
    monkeypatch.setattr(bot, "GEMINI_BUDGET", 0.0)
    calls = []
    monkeypatch.setattr(bot.requests, "post", lambda url, **kw: calls.append(url) or FakeResp(429))
    assert bot._gemini_call("x") is None
    assert calls == []


# ---- L4: ai_dedupe ghi tin bị trùng với tin nào; chạy được khi chỉ có khóa dự phòng
def test_ai_dedupe_records_dup_of_and_runs_without_gemini(monkeypatch, quiet):
    monkeypatch.setattr(bot, "GEMINI_KEY", "")
    monkeypatch.setattr(bot, "GROQ_KEY", "k")
    traced = []
    monkeypatch.setattr(bot, "trace", lambda stage, status, reason, it, **kw: traced.append((stage, reason, it["id"], kw)))
    monkeypatch.setattr(bot, "note_dropped", lambda *a, **k: None)
    monkeypatch.setattr(bot, "gemini", lambda p: '[{"i": 1, "dup": true, "of": "A1"}, {"i": 2, "dup": false}]')
    e1 = ({"id": "x1", "title": "PM Hun Manet visits Tokyo again", "source": "s"}, ["t"])
    e2 = ({"id": "x2", "title": "New tariff rule announced", "source": "s"}, ["t"])
    kept, dropped = bot.ai_dedupe([e1, e2], ["Hun Manet arrives in Japan"])
    assert [it["id"] for it in dropped] == ["x1"]
    assert [it["id"] for it, _ in kept] == ["x2"]
    assert ("ai_dedupe", "duplicate_event", "x1", {"of": "Hun Manet arrives in Japan"}) in traced


# ---- L5: AI trả thiếu "ok" → chưa chấm (lọc chặt dự phòng), không mặc định loại
def test_ai_relevant_missing_ok_is_unknown(monkeypatch, quiet):
    monkeypatch.setattr(bot, "GROQ_KEY", "k")
    monkeypatch.setattr(bot, "gemini", lambda p: '[{"i": 1, "c": "hi"}, {"i": 2, "ok": false}]')
    bot._relevance_cache.clear()
    it1 = {"id": "r1", "title": "a", "desc": "", "domain": "x.com"}
    it2 = {"id": "r2", "title": "b", "desc": "", "domain": "x.com"}
    ok, unknown = bot.ai_relevant([(it1, "kw"), (it2, "kw")])
    assert ("r1", "kw") in unknown
    assert ("r2", "kw") not in ok and ("r2", "kw") not in unknown


# ---- L7: phần tử không phải dict trong JSON web app không làm hỏng cả nguồn
def test_fetch_proxy_ignores_non_dict(monkeypatch, quiet, tmp_path):
    monkeypatch.setattr(bot, "APPS_PROXY_URL", "https://script.google.com/macros/s/X/exec")
    monkeypatch.setattr(bot, "_proxy_fetch", lambda u: FakeResp(200, ["rác", {"source": "MFAIC", "title": "Cambodia statement", "link": "https://mfaic.gov.kh/a"}]))
    monkeypatch.setattr(bot, "mark_ok", lambda u: None)
    monkeypatch.setattr(bot, "stat_src", lambda *a, **k: None)
    bot._feed_cache.pop("px:test", None)
    bot.STATE["health"].pop("px:test", None)
    items = bot.fetch_proxy("px:test")
    assert [i["title"] for i in items] == ["Cambodia statement"]
