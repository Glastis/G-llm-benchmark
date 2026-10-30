"""The blind LLM judge (PLAN §10.31). Opus at `xhigh` grades what no formula measures: the code criteria
of GRADING.md for T1 and T4, the truth and completeness of the T2 summary. Each run is judged twice,
in two separate sessions, and the grade kept is the mean; the spread shows how steady the judge is.

Blind: the judge works on a copy of the run's final workspace under a random name, without the
transcript, the metrics or any grade, every contestant or model name and the run's own workspace path
replaced by [redacted]. It runs in the agents' sandbox, so the bench repository, where the names are,
stays out of its sight. It never sees the code metrics either (§10.29). The runs come in a seeded
random order, all the first passes before the second ones.
"""

from __future__ import annotations

import json
import os
import random
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Callable

from bench.backends import anthropic
from bench.config import ROOT, Bundle, Contestant, Task
from bench.grade import fill_sheet, finished_runs
from bench.runner import RUNS_ROOT, WS_ROOT, QuotaReached, RunPaths, _execute, _final_events, _scrub, classify, sandboxed

JUDGE = Contestant(id="judge", label="Blind judge", backend="anthropic", model="claude-opus-5-5", effort="xhigh")
JUDGE_ROOT = WS_ROOT / "judge"
PROMPTS = ROOT / "config" / "judge"
REPORT = "judge.json"
MARK = " (judge)"
TIMEOUT_S = 1800
CRITERIA = {"code": ["Readability", "Architecture", "Factoring", "Cleanliness", "Safety"],
            "summary": ["Truth", "Completeness"]}
GENERIC_NAMES = ["claude", "anthropic", "opus", "sonnet", "haiku", "strata", "qwen"]
SKIPPED = {"build", ".grade", "_judge", ".git"}
VERDICT = Path("_judge") / "judgement.json"


def grid() -> str:
    """The "The code" section of GRADING.md: the judge applies the author's own grid."""
    text = (ROOT / "GRADING.md").read_text(encoding="utf-8")
    start = text.index("## The code")
    end = text.find("\n## ", start + 1)
    return text[start:None if end == -1 else end].strip()


def prompt(kind: str) -> str:
    text = (PROMPTS / f"{kind}.md").read_text(encoding="utf-8")
    return text.replace("{grid}", grid()) if kind == "code" else text


def names(bundle: Bundle, record: dict) -> list[str]:
    """What would tell the judge whose work it grades, longest first so that a path goes before its parts."""
    words = {*bundle.contestants, *(c.model for c in bundle.contestants.values()), *GENERIC_NAMES,
             record.get("run_id", ""), record.get("workspace", "")}
    return sorted((w for w in words if w), key=len, reverse=True)


def redact(text: str, words: list[str]) -> str:
    for word in words:
        text = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", "[redacted]", text, flags=re.I)
    return text


def stage(run_dir: Path, task: Task, words: list[str], root: Path = JUDGE_ROOT) -> RunPaths:
    """The judge's workspace: the run's final workspace, build outputs left out, the agent's files
    redacted (the fixture's are kept as they are), and the statement in _judge/."""
    key = secrets.token_hex(6)
    p = RunPaths(ws=root / key, state=root / f"{key}.state", run=root / f"{key}.state")
    final, fixture = run_dir / "final", task.dir / task.fixture
    for src in sorted(final.rglob("*")):
        rel = src.relative_to(final)
        if not src.is_file() or SKIPPED & set(rel.parts):
            continue
        data = src.read_bytes()
        if not ((fixture / rel).is_file() and (fixture / rel).read_bytes() == data):
            try:
                data = redact(data.decode("utf-8"), words).encode("utf-8")
            except UnicodeDecodeError:
                pass
        dst = p.ws / redact(rel.as_posix(), words)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    (p.ws / "_judge").mkdir(parents=True, exist_ok=True)
    (p.ws / "_judge" / "STATEMENT.md").write_text(task.prompt_text(), encoding="utf-8")
    p.claude_home.mkdir(parents=True)
    return p


def parse(path: Path, kind: str) -> dict:
    """The judge's verdict, checked: every criterion with a score from 0 to 10."""
    verdict = json.loads(path.read_text(encoding="utf-8"))
    criteria = verdict.get("criteria") if isinstance(verdict, dict) else None
    if not isinstance(criteria, dict):
        raise ValueError("no criteria")
    for name in CRITERIA[kind]:
        score = (criteria.get(name) or {}).get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 10:
            raise ValueError(f"{name}: score {score!r}")
    return verdict


def judge_once(task: Task, run_dir: Path, bundle: Bundle, number: int, *, claude_bin: str = "claude",
               sandbox: bool = True, root: Path = JUDGE_ROOT) -> dict:
    """One pass of the judge on one run. Its transcript goes to the run's judge/pass<n>/."""
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    p = stage(run_dir, task, names(bundle, record), root)
    argv, env = anthropic.command(JUDGE, p.claude_home, p.state)
    argv = [claude_bin, *argv[1:]]
    if sandbox:
        argv = sandboxed(argv, p)
        argv.remove(f"--read-only={p.state / 'bin'}")
    base = {k: os.environ[k] for k in ("PATH", "HOME", "USER", "LANG", "TERM") if k in os.environ}
    out = run_dir / "judge" / f"pass{number}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    transcript, stderr = out / "transcript.jsonl", out / "stderr.log"
    t0 = time.monotonic()
    returncode, timed_out = _execute(argv, prompt(task.judge), {**base, **env}, p.ws, TIMEOUT_S, transcript, stderr)
    wall_s = round(time.monotonic() - t0, 1)
    _scrub([transcript, stderr], os.environ.get(anthropic.TOKEN_ENV))
    status = classify(returncode, timed_out, transcript, stderr)
    result = {"status": status, "wall_s": wall_s, "usd_reported": (_final_events(transcript)[0] or {}).get("total_cost_usd")}
    try:
        result["judgement"] = parse(p.ws / VERDICT, task.judge)
    except (OSError, ValueError) as e:
        result["error"] = str(e)
    shutil.move(p.claude_home, out / "claude-home")
    shutil.rmtree(p.ws, ignore_errors=True)
    shutil.rmtree(p.state, ignore_errors=True)
    if status == "quota":
        raise QuotaReached(f"subscription limit reached while judging {run_dir}")
    return result


def summarize(kind: str, passes: dict[str, dict]) -> tuple[dict, dict]:
    """The mean grade of each criterion over the passes that gave one, and the spread between them."""
    graded = [p["judgement"]["criteria"] for p in passes.values() if p.get("judgement")]
    scores, spread = {}, {}
    for name in CRITERIA[kind]:
        values = [c[name]["score"] for c in graded]
        if values:
            scores[name] = round(sum(values) / len(values), 2)
            spread[name] = max(values) - min(values)
    return scores, spread


def _load(run_dir: Path) -> dict:
    path = run_dir / REPORT
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"passes": {}}


def pending(campaign: str, tasks: dict[str, Task], contestants: set[str], passes: int = 2, seed: int = 0,
            force: bool = False, runs_root: Path = RUNS_ROOT) -> list[tuple[int, Path, Task]]:
    """The passes still to run, in order: every first pass, in a seeded random order, then every second."""
    runs = [(run_dir, task) for run_dir in finished_runs(campaign, runs_root)
            if (task := tasks.get(run_dir.parent.parent.name)) and task.judge and run_dir.parent.name in contestants]
    todo = []
    for number in range(1, passes + 1):
        order = list(runs)
        random.Random(seed * 100 + number).shuffle(order)
        for run_dir, task in order:
            done = _load(run_dir)["passes"].get(str(number), {})
            if force or not done.get("judgement"):
                todo.append((number, run_dir, task))
    return todo


def record(run_dir: Path, task: Task, number: int, result: dict, fresh: bool = False) -> dict:
    """Adds a pass to the run's judge.json, and the mean grades to its grade.md."""
    report = {"passes": {}} if fresh else _load(run_dir)
    report["judge"] = {"model": JUDGE.model, "effort": JUDGE.effort}
    report["passes"][str(number)] = result
    report["scores"], report["spread"] = summarize(task.judge, report["passes"])
    (run_dir / REPORT).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sheet = run_dir / "grade.md"
    if task.grading_sheet and sheet.is_file():
        cells = {name: [f"{score:g}"] for name, score in report["scores"].items()}
        sheet.write_text(fill_sheet(sheet.read_text(encoding="utf-8"), cells, MARK), encoding="utf-8")
    return report


def judge_campaign(todo: list[tuple[int, Path, Task]], bundle: Bundle, force: bool = False,
                   echo: Callable[[str], None] = print, **kw) -> None:
    """Runs the passes of `pending`. Stops on the subscription limit: the next launch resumes."""
    reset = set()
    for i, (number, run_dir, task) in enumerate(todo, 1):
        name = "_".join(run_dir.parts[-3:])
        echo(f"[{i}/{len(todo)}] {name} pass {number} …")
        result = judge_once(task, run_dir, bundle, number, **kw)
        report = record(run_dir, task, number, result, fresh=force and run_dir not in reset)
        reset.add(run_dir)
        grades = " · ".join(f"{k} {v:g}" for k, v in report["scores"].items())
        echo(f"    {result['status']}, {result['wall_s']:.0f} s · {grades or result.get('error', '')}")
