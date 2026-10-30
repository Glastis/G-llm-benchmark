"""Regenerates fixture/pr/changes.diff, the diff of the pull request: build/base (main) → fixture
(the branch), without the files that only exist for the review (pr/, review.schema.json).

    python tasks/T3-pr-review/build/build_pr.py
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

TASK = Path(__file__).resolve().parent.parent
REVIEW_ONLY = ("pr", "review.schema.json")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        shutil.copytree(TASK / "build" / "base", a, ignore=shutil.ignore_patterns("build"))
        shutil.copytree(TASK / "fixture", b, ignore=shutil.ignore_patterns("build", *REVIEW_ONLY))
        diff = subprocess.run(["git", "diff", "--no-index", "--no-prefix", "a", "b"], cwd=tmp,
                              capture_output=True, text=True).stdout
    # Run from tmp with --no-prefix, the folders a/ and b/ give the usual a/<file> and b/<file> paths.
    (TASK / "fixture" / "pr" / "changes.diff").write_text(diff)


if __name__ == "__main__":
    main()
