"""Guard GitHub Actions against deprecated Node.js 20 major versions."""
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def test_workflows_do_not_use_deprecated_node20_action_majors():
    deprecated = (
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "actions/upload-artifact@v4",
        "actions/download-artifact@v4",
    )
    for workflow in WORKFLOWS.glob("*.yml"):
        content = workflow.read_text(encoding="utf-8")
        for action in deprecated:
            assert action not in content, f"{workflow} still uses {action}"


def test_workflows_use_node24_compatible_action_majors():
    expected = (
        "actions/checkout@v7",
        "actions/setup-python@v7",
        "actions/upload-artifact@v7",
        "actions/download-artifact@v7",
    )
    content = "\n".join(p.read_text(encoding="utf-8") for p in WORKFLOWS.glob("*.yml"))
    for action in expected:
        if action.split("@")[0] in content:
            assert action in content
