"""Nguồn chính thức (OFFICIAL_SITES) lỗi liên tục phải có đường bù Google News `site:<tên miền>`,
giống các nguồn nằm trong `feeds` của chủ đề. Trước đây topic_gnews chỉ duyệt t["feeds"] nên MEF / Nội vụ /
Bộ Công chính… (403, timeout 2/2 run mỗi ngày) không bao giờ có đường bù."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEF = "src:https://mef.gov.kh/"


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.setenv("DECISIONS_FILE", str(tmp_path / "d.jsonl"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    mod.STATE["health"].pop(MEF, None)
    yield mod
    mod.STATE["health"].pop(MEF, None)
    sys.path.remove(ROOT)


def _site_queries(urls, domain):
    return [u for u in urls if f"site%3A{domain}" in u]


def test_nguon_chinh_thuc_loi_co_truy_van_site(bot):
    assert MEF in bot.official_urls()   # tiên quyết: MEF là nguồn chính thức của chủ đề Campuchia
    bot.mark_fail(MEF, "HTTP 403 (bị từ chối)")
    bot.mark_fail(MEF, "HTTP 403 (bị từ chối)")
    assert bot.is_unhealthy(MEF)
    assert _site_queries(bot.topic_gnews("campuchia"), "mef.gov.kh")


def test_nguon_chinh_thuc_khoe_khong_them_truy_van(bot):
    assert not _site_queries(bot.topic_gnews("campuchia"), "mef.gov.kh")


def test_nguon_chinh_thuc_loi_mot_lan_chua_them(bot):
    bot.mark_fail(MEF, "HTTP 403 (bị từ chối)")
    assert not bot.is_unhealthy(MEF)
    assert not _site_queries(bot.topic_gnews("campuchia"), "mef.gov.kh")
