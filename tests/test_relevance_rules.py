"""Hồi quy quy tắc loại tin bắt giữ ma túy đơn lẻ theo chỉ đạo Boss."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bot


def test_relevance_prompt_excludes_routine_drug_bust_even_if_large_or_senior_officer(monkeypatch):
    prompts = []
    monkeypatch.setattr(bot, "GEMINI_KEY", "test-key")
    monkeypatch.setattr(bot, "gemini", lambda prompt: prompts.append(prompt) or "stub")
    monkeypatch.setattr(bot, "ai_json", lambda _raw: [{"i": 1, "ok": False, "c": "hi"}])

    item = {
        "id": "test-drug-bust-rule",
        "title": "Senior police chief seizes 874kg of ketamine in largest drug bust",
        "desc": "",
        "domain": "phnompenhpost.com",
        "official": False,
    }
    key = (item["id"], "chủ đề Campuchia")
    bot._relevance_cache.pop(key, None)
    try:
        kept, unknown = bot.ai_relevant([(item, key[1])])
        assert not kept
        assert not unknown
        assert len(prompts) == 1
        assert "bắt giữ / đột kích / thu giữ ma túy" in prompts[0]
        assert "kể cả số lượng lớn" in prompts[0]
        assert "không suy diễn chỉ từ số lượng ma túy hay chức vụ người phát biểu" in prompts[0]
    finally:
        bot._relevance_cache.pop(key, None)
