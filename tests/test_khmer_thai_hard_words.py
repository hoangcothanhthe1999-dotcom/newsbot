"""Test offline: từ khóa Khmer/Thái/Hoa cho cổng chính thống (Boss duyệt 23/11/2026)."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    monkeypatch.setattr(mod, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod, "save_state", lambda: None)
    yield mod
    sys.path.remove(ROOT)


@pytest.mark.parametrize("title", [
    "ทหารเตรียมกำลังที่ชายแดนกัมพูชา",
    "ការឈប់បាញ់ ព្រំប្រទល់ថ្មី",
    "កងទ័ពបញ្ជូនកម្លាំងទៅព្រំដែន",
    "柬泰边境局势",
])
def test_native_border_words_hard_pass(bot, title):
    assert bot.hard_official({"title": title, "desc": "", "domain": "akp.gov.kh"})


def test_unrelated_official_text_still_goes_to_ai(bot):
    assert not bot.hard_official({"title": "វិញ្ញាបនបត្រសរសើរសិស្ស", "desc": "", "domain": "akp.gov.kh"})
