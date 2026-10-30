"""Targeted phase-1 smoke tests (ARCHITECTURE §9).

Each check names the runs it needs (task from tasks/smoke/, contestant or contestant variant, repetitions)
and turns their results into a verdict: PASS, FAIL, or REVIEW when the numbers are for the author to
assess. Runs go to the `s02` campaign and are never repeated once finished, so `bench smoke --report`
can recompute every verdict without launching anything. The "hello" runs of `s01` are reused by the
blank-config check.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from bench.backends import strata
from bench.campaign import RunSpec
from bench.collect import collect
from bench.config import ROOT, Bundle, Contestant, load_tasks
from bench.runner import FINAL, RUNS_ROOT, WS_ROOT, QuotaReached, paths_for, run_one, sandbox_exec, status_of, strata_side

SMOKE_DIR = ROOT / "tasks" / "smoke"
CAMPAIGN = "s02"
HELLO_CAMPAIGN = "s01"
REASONING_ANSWER = "4001"
# Agents Claude Code ships with: any other agent in a run's init event comes from a user config.
BUILTIN_AGENTS = {"claude", "Explore", "general-purpose", "Plan", "statusline-setup"}


@dataclass(frozen=True)
class Verdict:
    status: str          # PASS, FAIL or REVIEW
    lines: list[str]


@dataclass(frozen=True)
class Check:
    id: str
    number: int          # row of ARCHITECTURE §9
    title: str
    runs: tuple[tuple[str, str, int], ...]   # (task, contestant, repetitions)
    verdict: Callable[["Results"], Verdict]


def variants(b: Bundle) -> dict[str, Contestant]:
    """Contestant variants used only by the smoke tests."""
    c = b.contestants

    def v(base: str, suffix: str, **update) -> Contestant:
        return c[base].model_copy(update={"id": f"{base}@{suffix}", "label": f"{c[base].label} ({suffix})", **update})

    return {
        "haiku@low": v("haiku", "low", effort="low"),
        "haiku@xhigh": v("haiku", "xhigh", effort="xhigh"),
        "strata@low": v("strata", "low", effort="low"),
        "strata@4096": v("strata", "4096", max_output_tokens=4096),
        "strata@16384": v("strata", "16384", max_output_tokens=16384),
    }


def smoke_bundle(b: Bundle) -> Bundle:
    return replace(b, contestants={**b.contestants, **variants(b)}, tasks=load_tasks(SMOKE_DIR))


class Results:
    """The finished runs of the smoke campaigns, with their metrics."""

    def __init__(self, b: Bundle, runs_root: Path = RUNS_ROOT, ws_root: Path = WS_ROOT):
        self.b, self.runs_root, self.ws_root = b, runs_root, ws_root

    def run_dir(self, task: str, contestant: str, rep: int = 1, campaign: str = CAMPAIGN) -> Path:
        return paths_for(RunSpec(campaign, task, contestant, rep, False), self.ws_root, self.runs_root).run

    def metrics(self, task: str, contestant: str, rep: int = 1) -> dict | None:
        path = self.run_dir(task, contestant, rep) / "metrics.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def deliverable(self, task: str, contestant: str, name: str, rep: int = 1) -> Path:
        return self.run_dir(task, contestant, rep) / "deliverables" / name


def _output(m: dict) -> int:
    return sum(row["output"] for row in m["by_model"].values())


def _thinking(m: dict, model: str) -> int | None:
    usage = (m["reported"].get("model_usage") or {}).get(model) or {}
    return usage.get("thinkingTokens")


def _answer(r: Results, contestant: str) -> str:
    path = r.deliverable("reasoning", contestant, "answer.txt")
    return path.read_text().strip() if path.is_file() else "(missing)"


def verdict_effort(r: Results) -> Verdict:
    lines, ok = [], True
    for low, high in (("haiku@low", "haiku@xhigh"), ("strata@low", "strata")):
        ml, mh = r.metrics("reasoning", low), r.metrics("reasoning", high)
        if not ml or not mh:
            return Verdict("REVIEW", [f"missing run: {low if not ml else high}"])
        line = f"{low}: {_output(ml)} output tokens, answer {_answer(r, low)} · {high}: {_output(mh)} output tokens, answer {_answer(r, high)}"
        if (ml.get("strata_server") or {}).get("thinking_tokens") is not None:
            line += (f" · Strata thinking {ml['strata_server']['thinking_tokens']} vs "
                     f"{(mh.get('strata_server') or {}).get('thinking_tokens')}")
        lines.append(line)
        ok &= _output(mh) > _output(ml)
    return Verdict("PASS" if ok else "REVIEW", lines + ([] if ok else ["higher effort did not produce more output"]))


def verdict_subagent_effort(r: Results) -> Verdict:
    orch, medium, xhigh = (r.metrics("reasoning", c) for c in ("opus-haiku", "haiku", "haiku@xhigh"))
    if not orch or not medium or not xhigh:
        return Verdict("REVIEW", ["missing run among opus-haiku, haiku, haiku@xhigh"])
    if not orch.get("subagent_calls"):
        return Verdict("REVIEW", ["Opus did not delegate: inconclusive, run it again"])
    model = "claude-haiku-5-5"
    sub = orch["by_model"].get(model, {}).get("output", 0)
    figures = {"subagent": (sub, _thinking(orch, model)),
               "haiku medium": (_output(medium), _thinking(medium, model)),
               "haiku xhigh": (_output(xhigh), _thinking(xhigh, model))}
    closest = min(("haiku medium", "haiku xhigh"), key=lambda k: abs(figures[k][0] - sub))
    lines = [f"{name}: {out} output tokens, {think} thinking tokens" for name, (out, think) in figures.items()]
    return Verdict("REVIEW", lines + [f"the subagent's output is closest to {closest} (one sample each: a hint, not a proof)"])


def check_cpp(sim: Path, scratch: Path) -> tuple[bool, str]:
    """Builds and runs an agent-written C++ file inside the sandbox."""
    if not sim.is_file():
        return False, "sim.cpp missing"
    lines = len(sim.read_text(errors="replace").splitlines())
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    shutil.copy2(sim, scratch / "sim.cpp")
    try:
        out = sandbox_exec("g++ -std=c++20 -Wall -Wextra sim.cpp -o sim && timeout 20 ./sim", scratch, timeout_s=180)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    passed = out.returncode == 0 and out.stdout.strip() == "ALL OK"
    return passed and lines >= 500, f"{lines} lines, {'ALL OK' if passed else 'build or self-tests failed'}"


def verdict_strata_cap(r: Results) -> Verdict:
    lines = []
    for variant in ("strata@4096", "strata@16384"):
        for rep in (1, 2, 3):
            m = r.metrics("big-file", variant, rep)
            if not m:
                lines.append(f"{variant} r{rep}: missing run")
                continue
            ok, detail = check_cpp(r.deliverable("big-file", variant, "sim.cpp", rep),
                                   r.ws_root / f"{CAMPAIGN}_big-file_{variant}_r{rep}.check")
            server = m.get("strata_server") or {}
            lines.append(f"{variant} r{rep}: {m['status']}, {'success' if ok else 'failure'} ({detail}), "
                         f"{m['wall_s']:.0f} s, {m['truncated_responses']} truncated responses, "
                         f"thinking share {server.get('thinking_share')}, finish reasons {server.get('finish_reasons')}")
    return Verdict("REVIEW", lines + ["choose the cap on these numbers (PLAN §10.15)"])


def _init_event(transcript: Path) -> dict | None:
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            return event
    return None


def verdict_blank_config(r: Results) -> Verdict:
    transcripts = sorted(r.runs_root.glob(f"{HELLO_CAMPAIGN}/*/*/r*/transcript.jsonl")) \
        + sorted(r.runs_root.glob(f"{CAMPAIGN}/*/*/r*/transcript.jsonl"))
    if not transcripts:
        return Verdict("REVIEW", ["no run to inspect yet"])
    problems = []
    for t in transcripts:
        init = _init_event(t)
        name = "/".join(t.parts[-5:-1])
        if not init:
            problems.append(f"{name}: no init event")
            continue
        contestant = t.parts[-3]
        allowed = BUILTIN_AGENTS | ({"worker"} if contestant.startswith(("opus-haiku", "sonnet-haiku")) else set())
        if init.get("mcp_servers"):
            problems.append(f"{name}: MCP servers {init['mcp_servers']}")
        if extra := [p.get("name") for p in init.get("plugins") or [] if p.get("path") != "builtin"]:
            problems.append(f"{name}: user plugins {extra}")
        if extra := sorted(set(init.get("agents") or []) - allowed):
            problems.append(f"{name}: unexpected agents {extra}")
        if any(".state/claude-home" not in str(p) for p in (init.get("memory_paths") or {}).values()):
            problems.append(f"{name}: memory outside the run's blank config {init['memory_paths']}")
    lines = [f"{len(transcripts)} runs inspected: no MCP server, built-in plugins and agents only, memory in the run's own config"]
    return Verdict("FAIL", problems) if problems else Verdict("PASS", lines)


def verdict_sandbox(r: Results) -> Verdict:
    path = r.deliverable("sandbox-audit", "haiku", "audit.txt")
    if not path.is_file():
        return Verdict("FAIL" if r.metrics("sandbox-audit", "haiku") else "REVIEW", ["audit.txt missing"])
    audit = path.read_text(errors="replace")
    sections = {s.split("\n", 1)[0].strip(): s for s in audit.split("== ")[1:]}
    problems = []
    if str(ROOT) in audit or "/tasks/" in audit:
        problems.append("the bench repository is visible")
    for name in ("ssh", "run user"):
        body = sections.get(name)
        if body is None:
            problems.append(f"section '{name}' missing from audit.txt")
        elif not any(marker in body for marker in ("No such file", "Permission denied", "cannot")):
            problems.append(f"'{name}' is visible: {body.splitlines()[1:3]}")
    # Claude Code may create an empty ~/.claude inside the sandbox; the user's own must not show.
    if any(name in sections.get("claude config", "") for name in ("CLAUDE.md", "settings.json", "skills", "plugins")):
        problems.append("the user's ~/.claude content is visible")
    # The home folder that holds the bench repository is private too, whatever its name.
    private = [".ssh", ".gnupg"] + ([ROOT.relative_to(Path.home()).parts[0]] if ROOT.is_relative_to(Path.home()) else [])
    if any(f"/{name}" in sections.get("home tree", "") for name in private):
        problems.append("private folders appear in the home tree")
    return Verdict("FAIL", problems) if problems else Verdict("PASS", ["the bench repository, ~/.ssh, ~/.claude and the session sockets are invisible"])


CHECKS = [
    Check("effort", 2, "Effort is actually applied (Claude and Strata)",
          (("reasoning", "haiku@low", 1), ("reasoning", "haiku", 1), ("reasoning", "haiku@xhigh", 1),
           ("reasoning", "strata@low", 1), ("reasoning", "strata", 1)), verdict_effort),
    Check("subagent-effort", 4, "Effort of the Haiku subagents",
          (("reasoning", "opus-haiku", 1), ("reasoning", "haiku", 1), ("reasoning", "haiku@xhigh", 1)),
          verdict_subagent_effort),
    Check("strata-cap", 5, "Strata output cap: 4,096 versus 16,384",
          (("big-file", "strata@4096", 3), ("big-file", "strata@16384", 3)), verdict_strata_cap),
    Check("blank-config", 7, "The configuration is blank", (), verdict_blank_config),
    Check("sandbox", 8, "The sandbox is tight", (("sandbox-audit", "haiku", 1),), verdict_sandbox),
]
BY_ID = {c.id: c for c in CHECKS}


def plan(check_ids: list[str], b: Bundle) -> list[RunSpec]:
    """The runs the selected checks need, deduplicated, Strata runs last (single model load)."""
    specs = {}
    for cid in check_ids:
        for task, contestant, reps in BY_ID[cid].runs:
            exclusive = b.contestants[contestant].exclusive
            for rep in range(1, reps + 1):
                spec = RunSpec(CAMPAIGN, task, contestant, rep, exclusive)
                specs[spec.run_id] = spec
    return sorted(specs.values(), key=lambda s: s.exclusive)


def run(check_ids: list[str], b: Bundle, echo: Callable[[str], None] = print, **kw) -> None:
    """Launches the missing runs of the selected checks, then collects them. Stops on the
    subscription limit or when Strata is not serving."""
    roots = {k: kw[k] for k in ("ws_root", "runs_root") if k in kw}
    specs = [s for s in plan(check_ids, b) if status_of(paths_for(s, **roots)) not in FINAL]
    for i, spec in enumerate(specs, 1):
        side = strata_side(b.contestants[spec.contestant], b)
        health = strata.ensure_ready(side) if side else None
        echo(f"[{i}/{len(specs)}] {spec.run_id} …")
        status = run_one(spec, b, health, **kw)
        echo(f"[{i}/{len(specs)}] {spec.run_id} → {status}")
        if status == "quota":
            raise QuotaReached(f"subscription limit reached on {spec.run_id}: launch again later")
    collect(CAMPAIGN, b, kw.get("runs_root", RUNS_ROOT))


def report(check_ids: list[str], b: Bundle, runs_root: Path = RUNS_ROOT, ws_root: Path = WS_ROOT) -> dict[str, Verdict]:
    r = Results(b, runs_root, ws_root)
    verdicts = {cid: BY_ID[cid].verdict(r) for cid in check_ids}
    out = runs_root / CAMPAIGN / "smoke-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({cid: {"status": v.status, "lines": v.lines} for cid, v in verdicts.items()},
                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return verdicts
