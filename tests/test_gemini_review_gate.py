"""Tests for fail-closed Gemini review verdict selection."""
from pathlib import Path

from scripts.gemini_review_gate import parse_verdict, select_summary


def test_two_failed_gemini_steps_cannot_pass_from_stale_summary():
    summary = select_summary(
        "failure",
        "KET_LUAN: PASS",
        "failure",
        "KET_LUAN: PASS",
    )
    assert summary == ""
    assert parse_verdict(summary) == "INCONCLUSIVE"


def test_first_successful_step_is_the_only_accepted_summary():
    summary = select_summary(
        "success",
        "Review complete\nKET_LUAN: PASS",
        "skipped",
        "",
    )
    assert parse_verdict(summary) == "PASS"


def test_successful_retry_is_used_after_first_step_fails():
    summary = select_summary(
        "failure",
        "KET_LUAN: PASS",
        "success",
        "Review complete\nKET_LUAN: FAIL",
    )
    assert parse_verdict(summary) == "FAIL"


def test_successful_step_without_valid_final_marker_is_inconclusive():
    summary = select_summary("success", "No verdict was returned", "skipped", "")
    assert parse_verdict(summary) == "INCONCLUSIVE"


def test_review_workflow_covers_its_own_config_and_policy_changes():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "gemini-review.yml"
    ).read_text(encoding="utf-8")
    assert "'GEMINI.md'" in workflow
    assert "'.github/workflows/**'" in workflow
    assert "'**/*.yml'" in workflow
    assert "'**/*.yaml'" in workflow


def test_review_artifact_is_unique_per_run_attempt():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "gemini-review.yml"
    ).read_text(encoding="utf-8")
    artifact_name = "gemini-result-${{ github.run_id }}-${{ github.run_attempt }}"
    assert workflow.count(artifact_name) == 2


def test_verdict_marker_must_be_the_final_nonempty_line():
    assert parse_verdict("KET_LUAN: PASS\\nAdditional text") == "INCONCLUSIVE"
