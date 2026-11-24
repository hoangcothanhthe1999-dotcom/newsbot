"""Test offline: bộ tin chuẩn đúng khuôn, đủ cả hai loại nhãn, và hàm chấm điểm tính đúng."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import eval_golden


def test_golden_format_and_balance():
    rows = eval_golden.load()
    assert len(rows) >= 30
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        assert r["label"] in ("keep", "drop") and r["clarity"] in ("clear", "borderline")
        assert r["title"] and r["basis"]
    assert sum(r["label"] == "keep" for r in rows) >= 10
    assert sum(r["label"] == "drop" for r in rows) >= 10


def test_score_recall_precision():
    rows = [{"id": "a", "label": "keep"}, {"id": "b", "label": "keep"}, {"id": "c", "label": "drop"}, {"id": "d", "label": "drop"}]
    res = eval_golden.score(rows, {"a", "c"})
    assert res["recall"] == 0.5 and res["precision"] == 0.5
    assert [r["id"] for r in res["missed"]] == ["b"] and [r["id"] for r in res["junk"]] == ["c"]
