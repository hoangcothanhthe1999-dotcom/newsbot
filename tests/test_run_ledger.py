"""Test offline: dòng RUNSUM/LEDGER trong log và check_run.py."""
import importlib
import json
import logging
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN_abcDEF")
    monkeypatch.setenv("DECISIONS_FILE", str(tmp_path / "d.jsonl"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sys.path.insert(0, ROOT)
    sys.modules.pop("bot", None)
    mod = importlib.import_module("bot")
    mod.LEDGER_BUF.clear()
    mod.TRACE_COUNTS.clear()
    mod._trace_seen.clear()
    yield mod
    sys.path.remove(ROOT)


def test_ledger_skips_noise_and_has_no_url(bot, caplog):
    a = {"title": "Tin gửi | có dấu gạch", "link": "https://a.example/x?token=SECRET", "source": "A"}
    b = {"title": "Bài cũ", "link": "https://a.example/y", "source": "A"}
    bot.trace("send", "sent", "sent", a)
    bot.trace("age", "dropped", "too_old", b)
    assert len(bot.LEDGER_BUF) == 1
    with caplog.at_level(logging.INFO):
        bot.log_run_ledger()
    text = caplog.text
    assert "RUNSUM" in text and "LEDGER|" in text
    assert "SECRET" not in text and "a.example" not in text


def test_check_run_flags_flood_and_dup():
    sys.path.insert(0, ROOT)
    import check_run
    s = {"sent": 20, "ai_offtopic": 0, "ai_dup": 0, "stale": 0, "src_fail": 0, "src_total": 83, "src_fail_names": [], "ledger_cut": False}
    log = "x RUNSUM " + json.dumps(s) + "\nx LEDGER|ab12|A|send|sent|sent|t1\nx LEDGER|ab12|A|send|sent|sent|t1\n"
    out = "\n".join(check_run.analyse(log))
    assert "Gửi 20 tin" in out and "Gửi trùng" in out
    assert len(check_run.analyse(log)) <= 30
    sys.path.remove(ROOT)
