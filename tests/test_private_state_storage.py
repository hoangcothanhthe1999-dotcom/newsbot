from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_newsbot_workflow_reads_and_writes_state_only_in_private_repository():
    workflow = (ROOT / ".github" / "workflows" / "newsbot.yml").read_text(
        encoding="utf-8"
    )
    assert "repository: hoangcothanhthe1999-dotcom/newsbot-ops" in workflow
    assert "secrets.NEWSBOT_STATE_TOKEN" in workflow
    assert "runtime-state/state.json" in workflow
    assert "STATE_FILE:" in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "git add state.json" not in workflow


def test_runtime_state_is_ignored_by_public_repository():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "state.json" in gitignore
    assert "state.json.tmp" in gitignore


def test_public_readme_documents_private_state_token_requirement():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "newsbot-ops" in readme
    assert "NEWSBOT_STATE_TOKEN" in readme
