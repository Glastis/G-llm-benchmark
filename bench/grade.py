"""Automatic grading (PLAN §10.28). A task with a `grader` in task.yaml has a `grade(tree)` function.
`bench grade` stages a copy of each finished run's final workspace in `WS_ROOT/grading/`, inside the
home so that a grader can run agent code with `sandbox_exec`, and writes the report next to the run
as auto.json. Graders and their hidden data stay in the bench repository, invisible from the sandbox.

A report holds:
    {"scores": {criterion: 0 to 10}, "checks": {id: bool}, "figures": {raw numbers},
     "sheet": {row of grade.md: [cell, …]}, "attachments": [files of the tree], "details": {…}}
Scores only where a fixed formula is objective; the rest stays the author's (GRADING.md). The `sheet`
cells go into the run's grade.md, only where the author left them blank; the attachments are copied
into the run's auto/ folder.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType

from bench.config import Task
from bench.runner import FINAL, RUNS_ROOT, WS_ROOT

GRADING_ROOT = WS_ROOT / "grading"
REPORT = "auto.json"
AUTO = " (auto)"
RUN_DIR = re.compile(r"r\d+")
ATTACHMENTS = "auto"   # where a run keeps the files its grader attached (screenshots…)

# For the graders' sandbox scripts: `python3 measure.py <timeout s> <stderr file> <command…>` runs the
# command and prints "<exit code or timeout> <ms> <peak RSS in KiB> <CPU ms>".
MEASURE = """import os, subprocess, sys, threading, time
limit = float(sys.argv[1])
start = time.monotonic()
child = subprocess.Popen(sys.argv[3:], stderr=open(sys.argv[2], "w"))
killer = threading.Timer(limit, child.kill)
killer.start()
_, status, usage = os.wait4(child.pid, 0)   # the exact end and peak RSS: Popen.wait polls every 50 ms
ms = round((time.monotonic() - start) * 1000)
killer.cancel()
print("timeout" if ms >= limit * 1000 else os.waitstatus_to_exitcode(status), ms, usage.ru_maxrss,
      round((usage.ru_utime + usage.ru_stime) * 1000))
"""


def load_module(path: Path, name: str) -> ModuleType:
    """Loads a grader file. Graders import their neighbours by plain name (`oracle`, `scenarios`…),
    and two tasks may use the same names: the neighbours already loaded for another task are dropped
    first, so that each grader binds its own."""
    for neighbour in path.parent.glob("*.py"):
        sys.modules.pop(neighbour.stem, None)
    if str(path.parent) in sys.path:
        sys.path.remove(str(path.parent))
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_grader(task: Task) -> ModuleType:
    return load_module(task.dir / task.grader, f"grader_{task.id.replace('-', '_')}")


def stage(src: Path, name: str, root: Path = GRADING_ROOT) -> Path:
    """A fresh copy of `src` to grade, so that a grader never writes into runs/. A top-level build/ is
    left out: one made later in runs/, by hand, would hold a CMake cache tied to that place."""
    tree = root / name
    if tree.exists():
        shutil.rmtree(tree)
    shutil.copytree(src, tree, ignore=lambda folder, names: {"build", ".grade"} & set(names) if Path(folder) == src else set())
    return tree


def changed_files(tree: Path, fixture: Path, ignore: tuple[str, ...] = ()) -> list[str]:
    """Fixture files modified or deleted in the final tree, `ignore` excluded."""
    changed = []
    for src in fixture.rglob("*"):
        rel = src.relative_to(fixture).as_posix()
        if not src.is_file() or src.name == ".gitkeep" or rel in ignore:
            continue
        dst = tree / rel
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            changed.append(rel)
    return changed


def created_files(tree: Path, fixture: Path, allowed: tuple[str, ...] = ()) -> list[str]:
    """Files of the final tree that the fixture does not have, `allowed` excluded."""
    return sorted(rel for p in tree.rglob("*") if p.is_file()
                  and (rel := p.relative_to(tree).as_posix()) not in allowed
                  and not rel.startswith(".grade/") and not (fixture / rel).exists())


def fill_sheet(text: str, sheet: dict[str, list[str | None]], mark: str = AUTO) -> str:
    """grade.md with the grader's cells written in, after the row's label, each marked with `mark`. The
    cells an earlier pass marked the same way are cleared first; the others are only written when
    blank (or the build row's "yes / no"), so that the author's own grades always win. None leaves a
    cell alone."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        cells = line.rstrip("\n").split("|")
        if len(cells) < 4:
            continue
        cells[2:-1] = [" " if cell.strip().endswith(mark.strip()) else cell for cell in cells[2:-1]]
        for j, value in enumerate(sheet.get(cells[1].strip(), []), start=2):
            if value is not None and j < len(cells) - 1 and cells[j].strip() in ("", "yes / no"):
                cells[j] = f" {value.removesuffix(mark)}{mark} "
        lines[i] = "|".join(cells) + ("\n" if line.endswith("\n") else "")
    return "".join(lines)


def grade_run(task: Task, run_dir: Path, force: bool = False) -> dict:
    """The run's report: auto.json when it exists, unless `force`. Fills grade.md either way."""
    out = run_dir / REPORT
    if out.is_file() and not force:
        report = json.loads(out.read_text(encoding="utf-8"))
    elif not (run_dir / "final").is_dir():
        report = {"error": "no final workspace"}
    else:
        tree = stage(run_dir / "final", "_".join(run_dir.parts[-4:]))
        try:
            report = load_grader(task).grade(tree)
            attached = run_dir / ATTACHMENTS
            shutil.rmtree(attached, ignore_errors=True)
            for rel in report.get("attachments", []):
                if (tree / rel).is_file():
                    attached.mkdir(exist_ok=True)
                    shutil.copy2(tree / rel, attached / Path(rel).name)
        finally:
            shutil.rmtree(tree, ignore_errors=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sheet = run_dir / "grade.md"   # refreshed even from a cached report
    if report.get("sheet") and sheet.is_file():
        sheet.write_text(fill_sheet(sheet.read_text(encoding="utf-8"), report["sheet"]), encoding="utf-8")
    return report


def finished_runs(campaign: str, runs_root: Path = RUNS_ROOT) -> list[Path]:
    """The finished runs of a campaign, set-aside attempts excluded."""
    runs = []
    for record in sorted((runs_root / campaign).glob("*/*/r*/run.json")):
        status = json.loads(record.read_text(encoding="utf-8")).get("status")
        if RUN_DIR.fullmatch(record.parent.name) and status in FINAL:
            runs.append(record.parent)
    return runs


def grade_campaign(campaign: str, tasks: dict[str, Task], contestants: set[str],
                   force: bool = False, runs_root: Path = RUNS_ROOT, echo=print) -> list[tuple[Path, dict]]:
    graded = []
    for run_dir in finished_runs(campaign, runs_root):
        task = tasks.get(run_dir.parent.parent.name)
        if not task or not task.grader or run_dir.parent.name not in contestants:
            continue
        report = grade_run(task, run_dir, force)
        graded.append((run_dir, report))
        echo(f"{'_'.join(run_dir.parts[-3:]):<40} {summary(report)}")
    return graded


def summary(report: dict) -> str:
    if "error" in report:
        return f"error: {report['error']}"
    scores = [f"{k} {v:g}" for k, v in report.get("scores", {}).items() if v is not None]
    failed = [f"✗ {k}" for k, ok in report.get("checks", {}).items() if not ok]
    return " · ".join(scores + failed) or "graded"
