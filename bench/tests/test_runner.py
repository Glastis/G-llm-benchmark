"""The runner and the collector end to end, with a fake `claude` and without the sandbox: no agent
is launched."""

import json
import shutil
from pathlib import Path

import pytest

from bench.campaign import RunSpec
from bench.collect import collect, metrics_for
from bench.config import load_all
from bench.pricing import Usage, request_cost
from bench.runner import RunError, paths_for, run_campaign, run_one, sandboxed

FAKE = str(Path(__file__).with_name("fake_claude.py"))


def make_task(root: Path, mode: str, timeout_min: float = 1, grading_sheet: bool = False) -> Path:
    task = root / "tasks" / "t"
    (task / "fixture").mkdir(parents=True)
    (task / "fixture" / "seed.txt").write_text("fixture\n")
    (task / "prompt.md").write_text(f"Do it. MODE={mode}\n")
    (task / "task.yaml").write_text(
        f"id: t\ntitle: test\ntimeout_min: {timeout_min}\nprompt: prompt.md\nfixture: fixture\n"
        f"deliverables: [hello.txt]\ngrading_sheet: {str(grading_sheet).lower()}\n")
    return root / "tasks"


def go(tmp_path: Path, mode: str, timeout_min: float = 1, contestant: str = "haiku", grading_sheet: bool = False):
    bundle = load_all(make_task(tmp_path, mode, timeout_min, grading_sheet))
    spec = RunSpec("c00", "t", contestant, 1, False)
    roots = dict(ws_root=tmp_path / "ws", runs_root=tmp_path / "runs")
    status = run_one(spec, bundle, claude_bin=FAKE, sandbox=False, **roots)
    return status, paths_for(spec, **roots), bundle


def test_ok_run_is_archived(tmp_path):
    status, p, _ = go(tmp_path, "ok")
    assert status == "ok"
    record = json.loads(p.record.read_text())
    assert record["claude_version"] == "9.9.9 (fake)" and record["sandbox"] is False
    assert (p.run / "deliverables" / "hello.txt").read_text() == "hello\n"
    assert sorted(f.name for f in (p.run / "final").iterdir()) == ["hello.txt", "seed.txt"]
    diff = (p.run / "workspace.diff").read_text()
    assert "hello.txt" in diff and "seed.txt" not in diff   # the fixture is in the initial commit
    assert (p.run / "claude-home").is_dir()


def test_metrics_dedupe_messages_and_price_them(tmp_path):
    _, p, bundle = go(tmp_path, "ok")
    m = metrics_for(p.run, bundle)
    opus, haiku = m["by_model"]["claude-opus-5-5"], m["by_model"]["claude-haiku-5-5"]
    assert opus["requests"] == 1 and opus["output"] == 200 and opus["cache_read"] == 5000
    assert haiku["requests"] == 1 and m["subagent_calls"] == 1 and m["subagent_requests"] == 1
    assert m["tool_calls"] == 2 and m["tool_errors"] == 1 and m["turns"] == 3
    expected = (request_cost("claude-opus-5-5", Usage(10, 200, 5000, 1000), bundle.pricing)
                + request_cost("claude-haiku-5-5", Usage(3000, 100), bundle.pricing))
    assert m["usd_total"] == pytest.approx(expected, abs=1e-6)
    assert m["warnings"] == []                                # tokens and cost match Claude Code's own
    assert m["subscription"] == {"status": "allowed", "five_hour_utilization": 0.25, "seven_day_utilization": 0.5}


def test_without_a_session_journal_the_stream_is_used_and_flagged(tmp_path):
    _, p, bundle = go(tmp_path, "ok")
    shutil.rmtree(p.run / "claude-home" / "projects")
    m = metrics_for(p.run, bundle)
    assert m["by_model"]["claude-opus-5-5"]["output"] == 20   # the stream's snapshot undercounts
    assert any("no session journal" in w for w in m["warnings"])
    assert m["subagent_calls"] is None and m["subagent_requests"] == 1   # from the stream
    assert any("output tokens counted" in w for w in m["warnings"])


def test_timeout_kills_the_run(tmp_path):
    status, p, _ = go(tmp_path, "sleep", timeout_min=0.02)
    assert status == "timeout"
    assert json.loads(p.record.read_text())["wall_s"] < 10


def test_quota_is_detected(tmp_path):
    status, _, _ = go(tmp_path, "quota")
    assert status == "quota"


def test_unwritten_prompt_is_refused(tmp_path):
    bundle = load_all(make_task(tmp_path, "ok"))
    (bundle.tasks["t"].dir / "prompt.md").write_text("<!-- TODO -->\n")
    with pytest.raises(RunError):
        run_one(RunSpec("c00", "t", "haiku", 1, False), bundle, claude_bin=FAKE, sandbox=False,
                ws_root=tmp_path / "ws", runs_root=tmp_path / "runs")


def test_campaign_skips_finished_runs_and_sets_aside_failed_ones(tmp_path):
    bundle = load_all(make_task(tmp_path, "ok"))
    kw = dict(claude_bin=FAKE, sandbox=False, ws_root=tmp_path / "ws", runs_root=tmp_path / "runs",
              contestants={"haiku": bundle.contestants["haiku"]}, echo=lambda s: None)
    assert run_campaign("c00", bundle, reps=2, **kw) == {"c00_t_haiku_r1": "ok", "c00_t_haiku_r2": "ok"}
    p1 = paths_for(RunSpec("c00", "t", "haiku", 1, False), tmp_path / "ws", tmp_path / "runs")
    first = p1.record.read_text()
    p2 = paths_for(RunSpec("c00", "t", "haiku", 2, False), tmp_path / "ws", tmp_path / "runs")
    p2.record.unlink()                                       # r2 "interrupted"
    run_campaign("c00", bundle, reps=2, **kw)
    assert p1.record.read_text() == first                    # r1 is not rerun
    assert list(p2.run.parent.glob("r2.attempt-*"))          # the previous attempt is set aside
    assert len(collect("c00", bundle, tmp_path / "runs")) == 2
    assert not list((tmp_path / "runs").glob("**/grade.md"))   # the task has no grading sheet


def test_collect_fills_a_grading_sheet_and_never_overwrites_it(tmp_path):
    _, p, bundle = go(tmp_path, "ok", grading_sheet=True)
    collect("c00", bundle, tmp_path / "runs")
    sheet = p.run / "grade.md"
    text = sheet.read_text()
    assert "| Task | t |" in text and "| Contestant | haiku |" in text and "| Rep | 1 |" in text
    cost = next(line for line in text.splitlines() if line.startswith("| Cost "))
    assert "| Time (s) | |" not in text and cost.endswith(" $ |")   # no electricity outside Strata
    sheet.write_text("graded\n")
    collect("c00", bundle, tmp_path / "runs")
    assert sheet.read_text() == "graded\n"


def test_sandbox_argv(tmp_path):
    p = paths_for(RunSpec("c00", "t", "opus-strata", 1, True), Path.home() / "bench-ws-argv-test", tmp_path / "runs")
    argv = sandboxed(["claude", "-p", "x"], p)   # creates nothing
    assert argv[0] == "firejail" and argv[argv.index("--") + 1:] == ["claude", "-p", "x"]
    assert f"--whitelist={p.ws}" in argv and f"--whitelist={p.state}" in argv
    assert not any(str(p.run) in a for a in argv)            # results stay outside the sandbox
    assert f"--read-only={p.state / 'bin'}" in argv


def test_sandbox_refuses_a_workspace_outside_home(tmp_path):
    p = paths_for(RunSpec("c00", "t", "haiku", 1, False), tmp_path / "ws", tmp_path / "runs")
    with pytest.raises(RunError):
        sandboxed(["claude"], p)


def test_sandbox_state_joins_the_results(tmp_path):
    _, p, _ = go(tmp_path, "ok")
    assert (p.run / "claude-home").is_dir() and not p.state.exists()
