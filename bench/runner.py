"""Running the benchmark (ARCHITECTURE §5): workspace, sandbox, clock, timeout, archive.

This module launches real agents (`claude -p`). The tests run it with a fake `claude` and
without the sandbox. A real run only starts through `bench run`.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from bench.backends import anthropic, strata
from bench.campaign import RunSpec, plan_runs
from bench.config import ROOT, Bundle, Contestant, Task
from bench.energy import GpuSampler

WS_ROOT = Path(os.environ.get("BENCH_WS_ROOT", Path.home() / "bench-ws"))
RUNS_ROOT = ROOT / "runs"
PROFILE = ROOT / "config" / "firejail" / "bench.profile"
WORKER = ROOT / "bench" / "worker" / "bench-worker"

FINAL = ("ok", "timeout", "error")   # `quota`, or no run.json: the run must be redone
# Messages that signal the subscription limit. To be confirmed in smoke test #9.
QUOTA_MARKERS = ("usage limit", "rate limit", "limit reached", "quota")
KILL_GRACE_S = 10
# Ignored by the final diff: build outputs and dependencies, not code written by the agent.
GIT_EXCLUDE = "build/\nnode_modules/\n__pycache__/\n.pytest_cache/\n"


class RunError(RuntimeError):
    pass


class QuotaReached(RuntimeError):
    pass


class Interrupted(RuntimeError):
    """Ctrl-C stopped the agent: its run gets no run.json, so the next launch sets it aside and redoes it."""


class Agents:
    """The agents running now, so that Ctrl-C stops them all: each runs in its own process group,
    which the terminal's signal does not reach."""

    def __init__(self) -> None:
        self.procs: set[subprocess.Popen] = set()
        self.lock = threading.Lock()
        self.stopped = False

    def stop(self) -> None:
        with self.lock:
            self.stopped = True
            procs = list(self.procs)
        for proc in procs:
            _kill(proc, signal.SIGTERM)
        deadline = time.monotonic() + KILL_GRACE_S
        for proc in procs:
            try:
                proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                _kill(proc, signal.SIGKILL)


AGENTS = Agents()


def _kill(proc: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


@dataclass(frozen=True)
class RunPaths:
    ws: Path      # the agent's workspace
    state: Path   # what the sandbox may write outside ws: CLAUDE_CONFIG_DIR, workers/
    run: Path     # results, in the bench repository, never visible from the sandbox

    @property
    def claude_home(self) -> Path:
        return self.state / "claude-home"

    @property
    def record(self) -> Path:
        return self.run / "run.json"


def paths_for(spec: RunSpec, ws_root: Path = WS_ROOT, runs_root: Path = RUNS_ROOT) -> RunPaths:
    return RunPaths(ws_root / spec.run_id, ws_root / f"{spec.run_id}.state",
                    runs_root / spec.campaign / spec.task / spec.contestant / f"r{spec.rep}")


def status_of(p: RunPaths) -> str | None:
    if not p.record.is_file():
        return None
    return json.loads(p.record.read_text(encoding="utf-8")).get("status")


def strata_side(c: Contestant, bundle: Bundle) -> Contestant | None:
    """The Strata contestant involved in a run: the contestant itself, or its workers."""
    if c.backend == "strata":
        return c
    if c.workers and bundle.contestants[c.workers.contestant].backend == "strata":
        return bundle.contestants[c.workers.contestant]
    return None


def _git(ws: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@localhost",
           "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "bench@localhost"}
    return subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=ws, env=env,
                          check=True, capture_output=True, text=True).stdout


def _set_aside(path: Path, stamp: str) -> None:
    """An incomplete attempt is renamed, never deleted."""
    if path.exists():
        path.rename(path.with_name(f"{path.name}.attempt-{stamp}"))


def prepare(task: Task, p: RunPaths) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in (p.ws, p.state, p.run):
        _set_aside(path, stamp)
    shutil.copytree(task.dir / task.fixture, p.ws, ignore=shutil.ignore_patterns(".gitkeep"))
    _git(p.ws, "init", "-q")
    (p.ws / ".git" / "info" / "exclude").write_text(GIT_EXCLUDE, encoding="utf-8")
    _git(p.ws, "add", "-A")
    _git(p.ws, "commit", "-q", "--allow-empty", "--no-verify", "-m", "fixture")
    p.claude_home.mkdir(parents=True)
    p.run.mkdir(parents=True)
    (p.state / "bin").mkdir()
    shutil.copy2(WORKER, p.state / "bin" / WORKER.name)   # keeps the bench repository invisible to the sandbox


def build(spec: RunSpec, bundle: Bundle, p: RunPaths, health: dict | None, claude_bin: str) -> tuple[list[str], dict[str, str], str]:
    """argv, environment and the task statement, which goes on stdin."""
    c, task = bundle.contestants[spec.contestant], bundle.tasks[spec.task]
    prompt = task.prompt_text()
    if "TODO" in prompt:
        raise RunError(f"{task.id}: task statement not written yet")
    if c.backend == "strata":
        argv, env = strata.command(c, p.claude_home, health["max_context"])
    else:
        worker = bundle.contestants[c.workers.contestant] if c.workers else None
        argv, env = anthropic.command(c, p.claude_home, p.state, worker)
    base = {k: os.environ[k] for k in ("PATH", "HOME", "USER", "LANG", "TERM") if k in os.environ}
    return [claude_bin, *argv[1:]], {**base, **env}, prompt


def toolchain_paths() -> list[Path]:
    """What the agent must see in the home, read-only: the `claude` binary found in the PATH
    (link and target), and the pyenv and nvm roots if their variables are set. Nothing is
    hard-coded; outside the home, Firejail leaves everything visible."""
    found = shutil.which("claude")
    paths = [Path(found), Path(found).resolve()] if found else []
    paths += [Path(os.environ[var]) for var in ("PYENV_ROOT", "NVM_DIR") if os.environ.get(var)]
    home = Path.home()
    return [p for p in dict.fromkeys(paths) if p.exists() and p.is_relative_to(home)]


def sandboxed(argv: list[str], p: RunPaths) -> list[str]:
    if not p.ws.is_relative_to(Path.home()):
        # Firejail only masks the home when there is a whitelist inside it.
        raise RunError(f"the workspace {p.ws} must be inside the home for the sandbox to mask the rest")
    # --deterministic-shutdown: without it, a process the agent left running keeps the sandbox, and
    # so the run, alive until the timeout.
    jail = ["firejail", "--quiet", "--deterministic-shutdown", f"--profile={PROFILE}",
            f"--whitelist={p.ws}", f"--whitelist={p.state}"]
    for path in toolchain_paths():
        jail += [f"--whitelist={path}", f"--read-only={path}"]
    jail.append(f"--read-only={p.state / 'bin'}")   # bench-worker: usable, not modifiable
    return [*jail, "--", *argv]


def sandbox_exec(command: str, workdir: Path, timeout_s: float = 120) -> subprocess.CompletedProcess:
    """Runs a shell command on agent-produced files inside the same sandbox as the agents, never
    on the host. `workdir` must be inside the home (see `sandboxed`)."""
    p = RunPaths(ws=workdir, state=workdir, run=workdir)
    jail = sandboxed(["sh", "-c", command], p)
    jail.remove(f"--read-only={p.state / 'bin'}")
    env = {k: os.environ[k] for k in ("PATH", "HOME", "USER", "LANG") if k in os.environ}
    return subprocess.run(jail, cwd=workdir, env=env, capture_output=True, text=True, timeout=timeout_s)


def _final_events(transcript: Path) -> tuple[dict | None, dict | None]:
    """The `result` event and the last `rate_limit_event` info of a stream-json transcript."""
    result = limit = None
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            result = event
        elif event.get("type") == "rate_limit_event":
            limit = event.get("rate_limit_info")
    return result, limit


def classify(returncode: int | None, timed_out: bool, transcript: Path, stderr: Path) -> str:
    if timed_out:
        return "timeout"
    result, limit = _final_events(transcript)
    if returncode == 0 and result and not result.get("is_error"):
        return "ok"
    if limit and limit.get("status") not in (None, "allowed"):
        return "quota"
    text = (str(result.get("result", "")) if result else "") + stderr.read_text(encoding="utf-8", errors="replace")
    if any(marker in text.lower() for marker in QUOTA_MARKERS):
        return "quota"
    return "error"


def _execute(argv: list[str], prompt: str, env: dict, cwd: Path, timeout_s: float, out: Path, err: Path) -> tuple[int | None, bool]:
    with out.open("wb") as fout, err.open("wb") as ferr:
        with AGENTS.lock:
            if AGENTS.stopped:
                raise Interrupted("stopped before it started")
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=fout, stderr=ferr,
                                    start_new_session=True)
            AGENTS.procs.add(proc)
        try:
            proc.communicate(prompt.encode("utf-8"), timeout=timeout_s)
            result = proc.returncode, False
        except subprocess.TimeoutExpired:
            _kill(proc, signal.SIGTERM)
            try:
                proc.wait(timeout=KILL_GRACE_S)
            except subprocess.TimeoutExpired:
                _kill(proc, signal.SIGKILL)
                proc.wait()
            result = None, True
        finally:
            with AGENTS.lock:
                AGENTS.procs.discard(proc)
        if AGENTS.stopped:
            raise Interrupted("stopped by Ctrl-C")
        return result


def _scrub(paths: list[Path], secret: str | None) -> None:
    if not secret:
        return
    for path in paths:
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if secret in text:
                path.write_text(text.replace(secret, "[token removed]"), encoding="utf-8")


def archive(task: Task, p: RunPaths) -> None:
    _git(p.ws, "add", "-A")
    (p.run / "workspace.diff").write_text(_git(p.ws, "diff", "--cached", "--stat") + "\n" + _git(p.ws, "diff", "--cached"),
                                          encoding="utf-8")
    # The whole final workspace (git's view of it: build outputs and caches excluded);
    # deliverables/ keeps the declared files at hand.
    final = p.run / "final"
    for rel in _git(p.ws, "ls-files", "-z").split("\0"):
        if rel and (p.ws / rel).is_file():
            (final / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p.ws / rel, final / rel)
    out = p.run / "deliverables"
    out.mkdir(exist_ok=True)
    for name in task.deliverables:
        src = p.ws / name
        if src.is_dir():
            shutil.copytree(src, out / name, dirs_exist_ok=True)
        elif src.is_file():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out / name)


def run_one(spec: RunSpec, bundle: Bundle, health: dict | None = None, *, claude_bin: str = "claude",
            sandbox: bool = True, ws_root: Path = WS_ROOT, runs_root: Path = RUNS_ROOT) -> str:
    """One complete run. Returns its status: ok, timeout, error or quota."""
    c, task = bundle.contestants[spec.contestant], bundle.tasks[spec.task]
    p = paths_for(spec, ws_root, runs_root)
    prepare(task, p)
    argv, env, prompt = build(spec, bundle, p, health, claude_bin)
    side = strata_side(c, bundle)
    if sandbox:
        argv = sandboxed(argv, p)
    version = subprocess.run([claude_bin, "--version"], capture_output=True, text=True).stdout.strip()

    log = strata.server_log() if side else None
    log_start = log.stat().st_size if log else 0
    transcript, stderr = p.run / "transcript.jsonl", p.run / "stderr.log"
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    if side:
        with GpuSampler(p.run / "energy.csv"):
            returncode, timed_out = _execute(argv, prompt, env, p.ws, task.timeout_min * 60, transcript, stderr)
    else:
        returncode, timed_out = _execute(argv, prompt, env, p.ws, task.timeout_min * 60, transcript, stderr)
    wall_s = time.monotonic() - t0

    if log:
        with log.open("rb") as f:
            f.seek(log_start)
            (p.run / "strata-server.log").write_bytes(f.read())
    for name in ("claude-home", "workers"):   # the sandbox state joins the results
        if (p.state / name).exists():
            shutil.move(p.state / name, p.run / name)
    shutil.rmtree(p.state, ignore_errors=True)
    _scrub([transcript, stderr, *p.run.glob("workers/*.jsonl")], os.environ.get(anthropic.TOKEN_ENV))
    archive(task, p)
    status = classify(returncode, timed_out, transcript, stderr)
    record = {
        "run_id": spec.run_id, "campaign": spec.campaign, "task": spec.task, "contestant": spec.contestant,
        "rep": spec.rep, "status": status, "returncode": returncode, "wall_s": round(wall_s, 2),
        "started_at": started.isoformat(), "timeout_min": task.timeout_min, "claude_version": version,
        "sandbox": sandbox, "contestant_config": c.model_dump(mode="json"),
        "strata_health": health, "workspace": str(p.ws),
    }
    p.record.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return status


def in_parallel(threads: int, take: Callable[[list], Any], launch: Callable[[Any], Callable[[], Any]],
                finish: Callable[[Any, Any], None]) -> None:
    """Runs jobs on `threads` threads (§10.35). `take(running)` gives the next job, given the jobs
    running, or None to wait for one to end; `launch(job)` does what comes before the clock, in this
    thread, and returns what to run on a thread; `finish(job, result)` handles each result, in this
    thread too. The first exception, from any of them, stops the launches: the jobs running end
    normally, then it is raised. Ctrl-C kills the agents running, whose runs are redone at the next
    launch."""
    running, error = {}, None
    try:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            try:
                while True:
                    while error is None and len(running) < threads and (job := take(list(running.values()))) is not None:
                        try:
                            running[pool.submit(launch(job))] = job
                        except Exception as e:
                            error = e
                    if not running:
                        break
                    for future in wait(running, return_when=FIRST_COMPLETED).done:
                        job = running.pop(future)
                        try:
                            finish(job, future.result())
                        except Exception as e:
                            error = error or e
            except KeyboardInterrupt:
                AGENTS.stop()
                raise
    finally:
        AGENTS.stopped = False   # every thread has ended
    if error:
        raise error


def run_campaign(campaign: str, bundle: Bundle, reps: int, seed: int = 0, *, threads: int = 1,
                 contestants: dict | None = None, tasks: dict | None = None,
                 echo: Callable[[str], None] = print, **kw) -> dict[str, str]:
    """Runs the unfinished runs, `threads` at a time (§10.35). Strata serves one model, slower than the
    others: its runs (`exclusive`) go one at a time, back to back, and a thread that frees up takes the
    next one whenever none is running; the other threads take the remote runs, in plan order. Stops on
    the subscription limit, when the subscription token is missing or when Strata is not serving:
    finished runs are kept, and the next launch resumes from there."""
    specs = plan_runs(campaign, contestants or bundle.contestants, tasks or bundle.tasks, reps, seed)
    done, todo = {}, []
    for spec in specs:
        st = status_of(paths_for(spec, kw.get("ws_root", WS_ROOT), kw.get("runs_root", RUNS_ROOT)))
        if st in FINAL:
            done[spec.run_id] = st
        else:
            todo.append(spec)
    local = deque((i, s) for i, s in enumerate(todo, 1) if s.exclusive)
    remote = deque((i, s) for i, s in enumerate(todo, 1) if not s.exclusive)

    def take(running: list) -> tuple[int, RunSpec] | None:
        if local and not any(s.exclusive for _, s in running):
            return local.popleft()
        return remote.popleft() if remote else None

    def launch(job: tuple[int, RunSpec]) -> Callable[[], str]:
        i, spec = job
        c = bundle.contestants[spec.contestant]
        if c.backend == "anthropic":
            anthropic.ensure_token()                           # outside the clock; NotLoggedIn stops the launches
        side = strata_side(c, bundle)
        health = strata.ensure_ready(side) if side else None   # outside the clock; NotServing stops the launches
        echo(f"[{i}/{len(todo)}] {spec.run_id} …")
        return lambda: run_one(spec, bundle, health, **kw)

    def finish(job: tuple[int, RunSpec], st: str) -> None:
        i, spec = job
        done[spec.run_id] = st
        echo(f"[{i}/{len(todo)}] {spec.run_id} → {st}")
        if st == "quota":
            raise QuotaReached(f"subscription limit reached on {spec.run_id}: launch again later, the campaign will resume there")

    in_parallel(threads, take, launch, finish)
    return done
