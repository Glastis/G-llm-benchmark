"""Rebuilds the T2 fixture: the private ComputerCraft repository at commit aa65141, as `git archive`
gives it (tracked files only, so neither .idea/ nor the untracked folders of the working copy).

    CC_REPO=<path to the ComputerCraft clone> python tasks/T2-archi-summary/make_fixture.py
"""

import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

COMMIT = "aa65141"
FIXTURE = Path(__file__).resolve().parent / "fixture"


def main() -> int:
    repo = os.environ.get("CC_REPO")
    if not repo:
        print("set CC_REPO to the ComputerCraft clone", file=sys.stderr)
        return 2
    archive = subprocess.run(["git", "-C", repo, "archive", COMMIT], capture_output=True, check=True).stdout
    for child in FIXTURE.iterdir():
        if child.name != ".gitkeep":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(FIXTURE, filter="data")
    print(f"{sum(1 for p in FIXTURE.rglob('*') if p.is_file()) - 1} files from {COMMIT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
