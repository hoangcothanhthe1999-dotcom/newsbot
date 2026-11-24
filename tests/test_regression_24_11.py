"""Hồi quy từ lỗi thật sáng 24/11/2026: dùng đầu ra AI ghi sẵn, không gọi mạng, không tốn token AI."""
import json

import bot

CRIT = "chủ đề campuchia"

# (id, tiêu đề, domain, AI ghi sẵn có cho qua không)
RECORDED = [
    ("tax1", "សេចក្តីជូនដំណឹង ស្តីពីវគ្គបណ្តុះបណ្តាលបុគ្គលិកពន្ធដារ", "tax.gov.kh", False),   # Tổng cục Thuế: đào tạo nội ngành
    ("tax2", "ប្រាក់ចំណូលពន្ធដារ e-service សេវាកម្ម", "tax.gov.kh", False),                  # link menu bị lấy nhầm
    ("bd1", "Happy Birthday to Deputy Prime Minister", "mfaic.gov.kh", False),               # chúc sinh nhật
    ("cul1", "Vietnam Culture Day celebrated in Phnom Penh", "mfaic.gov.kh", False),         # Ngày Văn hóa Việt Nam
    ("pol1", "Cambodia protests Thai military construction at border", "mfaic.gov.kh", True),
]


def _run(monkeypatch, recorded_json):
    monkeypatch.setattr(bot, "GEMINI_KEY", "x")
    monkeypatch.setattr(bot, "gemini", lambda p: recorded_json)
    monkeypatch.setattr(bot, "_relevance_cache", {})
    pairs = [({"id": i, "title": t, "desc": "", "official": True, "domain": d}, CRIT)
             for i, t, d, _ in RECORDED]
    ok, unknown = bot.ai_relevant(pairs)
    return {i for i, _ in ok}, unknown


def test_recorded_ai_output_drops_admin_birthday_culture(monkeypatch):
    rec = json.dumps([{"i": n, "ok": v} for n, (_, _, _, v) in enumerate(RECORDED, 1)])
    passed, unknown = _run(monkeypatch, rec)
    assert passed == {"pol1"}
    assert not unknown


def test_recorded_ai_output_accepts_fenced_json(monkeypatch):
    rec = "```json\n" + json.dumps([{"i": n, "ok": v} for n, (_, _, _, v) in enumerate(RECORDED, 1)]) + "\n```"
    passed, _ = _run(monkeypatch, rec)
    assert passed == {"pol1"}


def test_unparseable_ai_output_marks_unknown_not_pass_all(monkeypatch):
    _, unknown = _run(monkeypatch, "xin lỗi, tôi không thể")
    assert len(unknown) == len(RECORDED)   # AI hỏng -> rơi sang bộ lọc chặt dự phòng, không cho qua hết


def test_tax_menu_links_never_reach_ai():
    html = "".join(f'<a href="/kh/page{n}">សេវាកម្មអេឡិចត្រូនិកពន្ធដារ ជាង {n}</a>' for n in range(12))
    assert bot._page_links(html, "https://www.tax.gov.kh/") == {}
