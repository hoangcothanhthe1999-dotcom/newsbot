"""Regression checks for private runtime-state storage."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_newsbot_workflow_reads_and_writes_state_only_in_private_repository():
    workflow = (ROOT / ".github" / "workflows" / "newsbot.yml").read_text(encoding="utf-8")
    assert "repository: hoangcothanhthe1999-dotcom/newsbot-ops" in workflow
    assert "secrets.NEWSBOT_STATE_TOKEN" in workflow
    assert "STATE_FILE: ${{ github.workspace }}/.newsbot-state/runtime-state/state.json" in workflow
    assert "git -C .newsbot-state add -- runtime-state/state.json" in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "git add state.json" not in workflow


def test_public_repository_does_not_track_runtime_state():
    assert not (ROOT / "state.json").exists()
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "state.json" in gitignore
    assert "state.json.tmp" in gitignore


def test_private_state_access_check_is_read_only_and_uses_scoped_secret():
    workflow = (ROOT / ".github" / "workflows" / "private-state-access-check.yml").read_text(
        encoding="utf-8"
    )
    assert "secrets.NEWSBOT_STATE_TOKEN" in workflow
    assert "persist-credentials: false" in workflow
    assert "Private state access and structural validation: PASS." in workflow
