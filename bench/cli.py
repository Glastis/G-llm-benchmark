"""`bench` entry point (ARCHITECTURE §12). `run`, `smoke` and `judge` are the only commands that launch
agents, and they ask for confirmation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import typer

from bench.backends.anthropic import NotLoggedIn
from bench.backends.strata import NotServing
from bench.campaign import plan_runs
from bench import grade as grade_lib
from bench import judge as judge_lib
from bench import report as report_lib
from bench import smoke as smoke_lib
from bench.collect import collect as collect_metrics
from bench.config import ROOT, load_all, load_contestants, load_tasks
from bench.runner import FINAL, QuotaReached, RunError, paths_for, run_campaign, status_of

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _accepted(load) -> str:
    """The accepted values, for the help."""
    try:
        return ": " + ", ".join(load())
    except Exception:   # a broken config must not stop the CLI: `bench validate` reports it
        return ""


TASKS_DIR = typer.Option(ROOT / "tasks", "--tasks-dir", help="Tasks folder (tasks/smoke for the smoke tests).")
ONLY = typer.Option(None, help=f"Tasks, comma-separated{_accepted(load_tasks)}.")
CONTESTANTS = typer.Option(None, help=f"Contestants, comma-separated{_accepted(load_contestants)}.")
THREADS = typer.Option(1, "--thread", min=1, help="Agents running at once (PLAN §10.35).")


def _select(items: dict, only: str | None, what: str) -> dict:
    if not only:
        return items
    keys = only.split(",")
    if unknown := [k for k in keys if k not in items]:
        raise typer.BadParameter(f"unknown {what}: {', '.join(unknown)} (known: {', '.join(items)})")
    return {k: items[k] for k in keys}


@app.command()
def validate(tasks_dir: Path = TASKS_DIR) -> None:
    """Checks the configs, the prices and the tasks."""
    b = load_all(tasks_dir)
    typer.echo(f"{len(b.contestants)} contestants, {len(b.tasks)} tasks, prices as of {b.pricing.as_of}")
    for w in b.warnings:
        typer.echo(f"  warning: {w}")
    for e in b.errors:
        typer.echo(f"  error: {e}", err=True)
    if b.errors:
        raise typer.Exit(1)


@app.command()
def plan(
    campaign: str = typer.Argument(..., help="Campaign name, for example c01."),
    reps: int = typer.Option(3, help="Repetitions per (contestant, task) pair."),
    only: str | None = ONLY,
    contestants: str | None = CONTESTANTS,
    seed: int = typer.Option(0, help="Seed of the run order."),
    tasks_dir: Path = TASKS_DIR,
) -> None:
    """Lists the planned runs, in order, without launching anything."""
    b = load_all(tasks_dir)
    runs = plan_runs(campaign, _select(b.contestants, contestants, "contestants"),
                     _select(b.tasks, only, "tasks"), reps, seed)
    for i, r in enumerate(runs, 1):
        st = status_of(paths_for(r))
        typer.echo(f"{i:>3}  {r.run_id}{'  [exclusive]' if r.exclusive else ''}{f'  ({st})' if st else ''}")


@app.command()
def smoke(
    checks: list[str] | None = typer.Argument(None, help="Checks to run (ids from the list, or 'all'). None: list them."),
    report_only: bool = typer.Option(False, "--report", help="Only recompute the verdicts, launch nothing."),
    yes: bool = typer.Option(False, "--yes", help="Do not ask for confirmation."),
) -> None:
    """Targeted phase-1 smoke tests (ARCHITECTURE §9). Without arguments, lists them and launches nothing."""
    b = smoke_lib.smoke_bundle(load_all())
    if not checks:
        for check in smoke_lib.CHECKS:
            specs = smoke_lib.plan([check.id], b)
            done = sum(status_of(paths_for(s)) in FINAL for s in specs)
            runs = f"{done}/{len(specs)} runs done" if specs else "no run, reads existing transcripts"
            typer.echo(f"#{check.number}  {check.id:<16} {check.title}  ({runs})")
        typer.echo("\nbench smoke <id>… launches the missing runs; bench smoke all --report only recomputes the verdicts.")
        return
    ids = [c.id for c in smoke_lib.CHECKS] if checks == ["all"] else checks
    if unknown := [c for c in ids if c not in smoke_lib.BY_ID]:
        raise typer.BadParameter(f"unknown checks: {', '.join(unknown)}")
    if not report_only:
        todo = [s for s in smoke_lib.plan(ids, b) if status_of(paths_for(s)) not in FINAL]
        if todo:
            typer.echo(f"{len(todo)} run(s) to launch, that is real agents on the subscription or on Strata:")
            for s in todo:
                typer.echo(f"  {s.run_id}")
            if not yes and not typer.confirm("Launch?", default=False):
                raise typer.Exit(1)
            try:
                smoke_lib.run(ids, b, echo=typer.echo)
            except (QuotaReached, NotLoggedIn, NotServing, RunError) as e:
                typer.echo(f"stopped: {e}", err=True)
                raise typer.Exit(3)
    for cid, verdict in smoke_lib.report(ids, b).items():
        check = smoke_lib.BY_ID[cid]
        typer.echo(f"\n#{check.number} {check.title}: {verdict.status}")
        for line in verdict.lines:
            typer.echo(f"  {line}")


@app.command()
def run(
    campaign: str = typer.Argument(..., help="Campaign name."),
    reps: int = typer.Option(3, help="Repetitions per (contestant, task) pair."),
    only: str | None = ONLY,
    contestants: str | None = CONTESTANTS,
    seed: int = typer.Option(0, help="Seed of the run order."),
    tasks_dir: Path = TASKS_DIR,
    threads: int = THREADS,
    yes: bool = typer.Option(False, "--yes", help="Do not ask for confirmation."),
) -> None:
    """Launches the unfinished runs, then collects. Launches real agents. With --thread, the Strata
    runs go one at a time, back to back, beside the others."""
    b = load_all(tasks_dir)
    if b.errors:
        raise typer.BadParameter("invalid configuration: run `bench validate`")
    chosen, tasks = _select(b.contestants, contestants, "contestants"), _select(b.tasks, only, "tasks")
    todo = [r for r in plan_runs(campaign, chosen, tasks, reps, seed) if status_of(paths_for(r)) not in FINAL]
    if not todo:
        typer.echo("nothing to launch: every run of this plan is finished")
        return
    typer.echo(f"{len(todo)} run(s) to launch, that is real agents on the subscription or on Strata:")
    for r in todo[:10]:
        typer.echo(f"  {r.run_id}")
    if len(todo) > 10:
        typer.echo(f"  … and {len(todo) - 10} more")
    if not yes and not typer.confirm("Launch?", default=False):
        raise typer.Exit(1)
    try:
        run_campaign(campaign, b, reps, seed, threads=threads, contestants=chosen, tasks=tasks, echo=typer.echo)
    except (QuotaReached, NotLoggedIn, NotServing, RunError) as e:
        typer.echo(f"stopped: {e}", err=True)
        raise typer.Exit(3)
    finally:   # even after a stop, the finished runs get their metrics and grading sheets
        typer.echo("\nbench collect:")
        collect(campaign, tasks_dir)


@app.command()
def collect(campaign: str, tasks_dir: Path = TASKS_DIR) -> None:
    """Transcripts → metrics.json, with the cost alert."""
    b = load_all(tasks_dir)
    for m in collect_metrics(campaign, b):
        usd = "?" if m["usd_total"] is None else f"{m['usd_total']:.4f} $"
        flags = (["COST ALERT"] if m["cost_alert"] else []) + m["warnings"]
        typer.echo(f"{m['run_id']:<48} {m['status']:<8} {usd:>11}  {m['wall_s']:>7.1f} s  {' · '.join(flags)}")


@app.command()
def grade(
    campaign: str,
    only: str | None = ONLY,
    contestants: str | None = CONTESTANTS,
    force: bool = typer.Option(False, "--force", help="Grade again the runs that already have an auto.json."),
    tasks_dir: Path = TASKS_DIR,
) -> None:
    """Runs the task graders on the finished runs: auto.json in each run, the objective figures in
    grade.md. Builds and runs agent code in the sandbox, but launches no agent."""
    b = load_all(tasks_dir)
    grade_lib.grade_campaign(campaign, _select(b.tasks, only, "tasks"),
                             set(_select(b.contestants, contestants, "contestants")), force, echo=typer.echo)


@app.command()
def judge(
    campaign: str,
    only: str | None = ONLY,
    contestants: str | None = CONTESTANTS,
    passes: int = typer.Option(2, help="Independent passes per run; the grade kept is their mean."),
    seed: int = typer.Option(0, help="Seed of the judging order."),
    force: bool = typer.Option(False, "--force", help="Judge again the runs that already have a judge.json."),
    threads: int = THREADS,
    yes: bool = typer.Option(False, "--yes", help="Do not ask for confirmation."),
) -> None:
    """The blind judge (Opus, xhigh) on the finished runs: judge.json in each run, the code grades in
    grade.md. Launches real agents."""
    b = load_all()
    todo = judge_lib.pending(campaign, _select(b.tasks, only, "tasks"), set(_select(b.contestants, contestants, "contestants")),
                             passes, seed, force)
    if not todo:
        typer.echo("nothing to judge: every run of this campaign has its passes")
        return
    typer.echo(f"{len(todo)} judgement(s) to launch, that is real agents on the subscription:")
    for number, run_dir, _ in todo[:10]:
        typer.echo(f"  {'_'.join(run_dir.parts[-3:])} pass {number}")
    if len(todo) > 10:
        typer.echo(f"  … and {len(todo) - 10} more")
    if not yes and not typer.confirm("Launch?", default=False):
        raise typer.Exit(1)
    try:
        judge_lib.judge_campaign(todo, b, force, threads, echo=typer.echo)
    except (QuotaReached, NotLoggedIn, RunError) as e:
        typer.echo(f"stopped: {e}", err=True)
        raise typer.Exit(3)


@app.command()
def report(campaign: str) -> None:
    """HTML report of the campaign in runs/<campaign>/report/: per task and contestant, the mean and its
    95 % interval, median, σ, min and max of every grade, of time and of cost, and how sure the ranking
    and the judge are. Launches nothing."""
    if importlib.util.find_spec("plotly") is None:
        typer.echo("plotly is missing: uv run --extra report bench report …", err=True)
        raise typer.Exit(2)
    b = load_all()
    stats = report_lib.build_report(campaign, b.pricing.electricity_eur_per_kwh)
    for task, t in stats["tasks"].items():
        rows = t["contestants"].values()
        graded = sum(s is not None for row in rows for s in row["run_scores"].values())
        rho = f"ranking ρ {t['ranking']['rho']:.2f} ({t['ranking']['reading']})" if t["ranking"] else "ranking ρ n/a"
        typer.echo(f"{task:<22} {graded}/{sum(row['runs'] for row in rows)} runs graded · {rho}")
    typer.echo(f"→ {report_lib.RUNS_ROOT / campaign / 'report' / 'index.html'}")
