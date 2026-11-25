"""Test offline: tập giữ riêng golden_holdout.jsonl được đọc đúng và ngưỡng n>=5 chạy đúng."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import eval_golden


def _rows(n, label="keep"):
    return [{"id": f"h{i}", "label": label, "clarity": "clear", "title": "t", "basis": "b"} for i in range(n)]


def test_load_holdout_missing_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_golden, "HOLDOUT", str(tmp_path / "none.jsonl"))
    assert eval_golden.load_holdout() == []


def test_load_holdout_reads_file(tmp_path, monkeypatch):
    p = tmp_path / "h.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in _rows(3)) + "\n\n", encoding="utf-8")
    monkeypatch.setattr(eval_golden, "HOLDOUT", str(p))
    assert [r["id"] for r in eval_golden.load_holdout()] == ["h0", "h1", "h2"]


def test_repo_holdout_not_overlapping_golden_set():
    ids = {r["id"] for r in eval_golden.load()}
    hold = eval_golden.load_holdout()
    assert len(hold) <= 10
    assert not ids & {r["id"] for r in hold}


def test_holdout_threshold_applies_only_from_n5():
    bad4 = eval_golden.score(_rows(4), set())  # sót 100%, n=4
    bad5 = eval_golden.score(_rows(5), set())  # sót 100%, n=5
    assert eval_golden.holdout_fails(bad4, 1.0, 0.9) is False
    assert eval_golden.holdout_fails(bad5, 1.0, 0.9) is True
    ok5 = eval_golden.score(_rows(5), {r["id"] for r in _rows(5)})
    assert eval_golden.holdout_fails(ok5, 1.0, 0.9) is False
    assert eval_golden.holdout_fails(None, 1.0, 0.9) is False


def test_ctutuon_clarity_scored_like_normal():
    rows = _rows(2)
    rows[0]["clarity"] = "C-tu-chon"
    res = eval_golden.score(rows, {"h1"})
    assert res["recall"] == 0.5 and [r["id"] for r in res["missed"]] == ["h0"]
