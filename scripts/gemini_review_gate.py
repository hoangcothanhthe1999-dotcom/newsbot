"""Fail-closed verdict selection for the Gemini PR review workflow."""
from __future__ import annotations

import os
import re
from pathlib import Path


_VERDICT_RE = re.compile(r"^KET_LUAN: (PASS|FAIL|INCONCLUSIVE)\s*$", re.MULTILINE)


def select_summary(first_outcome: str, first_summary: str, second_outcome: str, second_summary: str) -> str:
    """Only accept output from an action step that completed successfully."""
    if first_outcome == "success":
        return first_summary
    if second_outcome == "success":
        return second_summary
    return ""


def parse_verdict(summary: str) -> str:
    matches = _VERDICT_RE.findall(summary)
    return matches[-1] if matches else "INCONCLUSIVE"


def main() -> None:
    first_outcome = os.environ.get("GEMINI1_OUTCOME", "")
    second_outcome = os.environ.get("GEMINI2_OUTCOME", "")
    summary = select_summary(
        first_outcome,
        os.environ.get("GEMINI1_SUMMARY", ""),
        second_outcome,
        os.environ.get("GEMINI2_SUMMARY", ""),
    )
    verdict = parse_verdict(summary)

    result_dir = Path(".gemini-review")
    result_dir.mkdir(parents=True, exist_ok=True)
    if summary.strip():
        (result_dir / "result.md").write_text(summary, encoding="utf-8")
    else:
        (result_dir / "result.md").write_text(
            "Gemini không trả kết quả hợp lệ từ một bước chạy thành công. "
            "Coi là INCONCLUSIVE: không merge.\n",
            encoding="utf-8",
        )

    errors = os.environ.get("GEMINI_ERRORS", "")
    (result_dir / "err.txt").write_text(
        f"bước Gemini: {first_outcome}/{second_outcome}\n{errors[:2000]}",
        encoding="utf-8",
    )

    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise RuntimeError("GITHUB_OUTPUT is not set")
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"verdict={verdict}\n")
    print(f"Kết luận: {verdict}")


if __name__ == "__main__":
    main()
