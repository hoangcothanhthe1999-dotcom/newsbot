"""Test offline: bảng nhật ký ngày dựng từ log (daily_table.py)."""
import hashlib
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import daily_table as dt


def _tid(link):
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:8]


LINK_SENT = "https://a.example/news/1"
LINK_DROP = "https://b.example/news/2"
LINK_PASS = "https://c.example/news/3"
LOG1 = "\n".join([
    f"2026-11-25 DEC|{_tid(LINK_SENT)}|relevance|passed|ai_relevant|A|Tin gửi đi|a.example/news/1",
    f"2026-11-25 DEC|{_tid(LINK_SENT)}|send|sent|sent|A|Tin gửi đi|a.example/news/1",
    f"2026-11-25 DEC|{_tid(LINK_DROP)}|keyword|dropped|keyword_mismatch|B|Tin bị loại từ khóa|b.example/news/2",
    f"2026-11-25 DEC|{_tid(LINK_PASS)}|relevance|passed|ai_relevant|C|Qua lọc chưa gửi|c.example/news/3",
    "2026-11-25 NGUỒN | LỖI | Kiripost | bài=0 | ok=0 lỗi=3 HTTP 403",
    "2026-11-25 NGUỒN | ĐỌC ĐƯỢC | Khmer Times | bài=12 | ok=2 lỗi=0 ",
])
LOG2 = "\n".join([
    f"DEC|{_tid(LINK_DROP)}|ai_relevance|dropped|ai_irrelevant|B|Tin bị loại từ khóa|b.example/news/2",
    "NGUỒN | ĐỌC ĐƯỢC | Kiripost | bài=4 | ok=1 lỗi=0 ",
])


def test_window_is_24h_ending_1615_vn():
    s, e = dt.window("2026-11-25")
    assert e.strftime("%d/%m %H:%M") == "25/11 16:15" and s.strftime("%d/%m %H:%M") == "24/11 16:15"
    assert isinstance(s, datetime)


def test_items_final_status_per_item():
    items = {i["tid"]: i for i in dt.build_items([LOG1, LOG2])}
    assert items[_tid(LINK_SENT)]["status"] == dt.SENT
    assert items[_tid(LINK_DROP)]["status"] == dt.DROPPED
    assert items[_tid(LINK_DROP)]["stage"] == "ai_relevance" and items[_tid(LINK_DROP)]["reason"] == "ai_irrelevant"
    assert items[_tid(LINK_PASS)]["status"] == dt.PASSED


def test_send_error_status():
    t = _tid("https://d.example/x")
    items = dt.build_items([f"DEC|{t}|relevance|passed|ai_relevant|D|Lỗi gửi|d.example/x\nDEC|{t}|send|error|send_error|D|Lỗi gửi|d.example/x"])
    assert items[0]["status"] == dt.SEND_ERR


def test_sources_best_of_window_and_failed_source_visible():
    srcs = {s["name"]: s for s in dt.build_sources([LOG1, LOG2])}
    assert srcs["Kiripost"]["tag"] == "ĐỌC ĐƯỢC"      # lỗi ở phiên 1 nhưng đọc được ở phiên 2
    only_fail = {s["name"]: s for s in dt.build_sources([LOG1])}
    assert only_fail["Kiripost"]["tag"] == "LỖI"


def test_match_by_full_link_by_keyword_and_no_trace():
    items = dt.build_items([LOG1, LOG2])
    assert dt.match(items, LINK_SENT)[0]["status"] == dt.SENT
    assert dt.match(items, "bị loại từ khóa")[0]["status"] == dt.DROPPED
    assert dt.match(items, "https://khong.co/bai-chua-tung-thay") == []


def test_counts_and_render_include_no_trace_line():
    items = dt.build_items([LOG1, LOG2])
    by_status, by_reason = dt.counts(items)
    assert by_status[dt.SENT] == 1 and by_reason == {"ai_relevance/ai_irrelevant": 1}
    out = dt.render(items, dt.build_sources([LOG1, LOG2]), [("https://khong.co/x", [])])
    assert "KHÔNG DẤU VẾT" in out and "# NGUỒN" in out


def test_nguon_loi_trong_ngay_dem_moi_run():
    logs = ["NGUỒN | LỖI | Nation | bài=0 | ok=0 lỗi=2 HTTP 403",
            "NGUỒN | ĐỌC ĐƯỢC | Nation | bài=3 | ok=1 lỗi=0",
            "NGUỒN | LỖI | Nation | bài=0 | ok=0 lỗi=1 timeout",
            "NGUỒN | ĐỌC ĐƯỢC | Khmer | bài=2 | ok=1 lỗi=0"]
    src = dt.build_sources(logs)
    nation = next(x for x in src if x["name"] == "Nation")
    assert (nation["runs"], nation["runs_err"], nation["fail"], nation["n"]) == (3, 2, 3, 3)
    out = dt.render([], src)
    assert "Nation | 2/3 | timeout" in out
    assert "Khmer | 0/" not in out


def test_nguon_moi_ngoai_bang_nguon():
    g = "news.google.com/rss/articles/x"
    items = [{"src": "Khmer Times", "status": dt.SENT, "link": g}, {"src": "Cambodianess", "status": dt.SENT, "link": g},
             {"src": "Cambodianess", "status": dt.DROPPED, "link": g}, {"src": "?", "status": dt.SEEN, "link": g},
             {"src": "Senate", "status": dt.SENT, "link": "senate.gov.kh/a"}]
    sources = [{"name": "Khmer Times"}]
    assert dt.new_sources(items, sources) == [("Cambodianess", 2, 1, 1)]
