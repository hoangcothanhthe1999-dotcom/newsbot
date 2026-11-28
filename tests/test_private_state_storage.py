ROOT = __file__.replace("\\", "/").rsplit("/tests/", 1)[0]


def read_project_file(path):
    with open(f"{ROOT}/{path}", encoding="utf-8") as file:
        return file.read()


def test_newsbot_workflow_reads_and_writes_state_only_in_private_repository():
    workflow = read_project_file(".github/workflows/newsbot.yml")
    assert "repository: hoangcothanhthe1999-dotcom/newsbot-ops" in workflow
    assert "secrets.NEWSBOT_STATE_TOKEN" in workflow
    assert "runtime-state/state.json" in workflow
    assert "STATE_FILE:" in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "git add state.json" not in workflow


def test_runtime_state_is_ignored_by_public_repository():
    gitignore = read_project_file(".gitignore").splitlines()
    assert "state.json" in gitignore
    assert "state.json.tmp" in gitignore


def test_public_readme_documents_private_state_token_requirement():
    readme = read_project_file("README.md")
    assert "newsbot-ops" in readme
    assert "NEWSBOT_STATE_TOKEN" in readme


def test_state_save_is_skipped_if_private_checkout_fails():
    workflow = read_project_file(".github/workflows/newsbot.yml")
    assert "id: private_state_checkout" in workflow
    assert "steps.private_state_checkout.outcome == 'success'" in workflow
