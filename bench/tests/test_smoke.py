"""The smoke checks: planning, verdicts on synthetic results, and one end-to-end check with the fake
`claude`. No agent is launched."""

import json
from pathlib import Path

from bench import smoke
from bench.collect import strata_log_stats
from bench.config import load_all

FAKE = str(Path(__file__).with_name("fake_claude.py"))
B = smoke.smoke_bundle(load_all())


def write_run(root: Path, task: str, contestant: str, metrics: dict, files: dict | None = None,
              transcript: list | None = None, campaign: str = smoke.CAMPAIGN) -> Path:
    run = root / campaign / task / contestant / "r1"
    (run / "deliverables").mkdir(parents=True)
    (run / "metrics.json").write_text(json.dumps(metrics))
    for name, text in (files or {}).items():
        (run / "deliverables" / name).write_text(text)
    if transcript is not None:
        (run / "transcript.jsonl").write_text("\n".join(json.dumps(e) for e in transcript) + "\n")
    return run


def metrics(output: int, model: str = "claude-haiku-5-5", **extra) -> dict:
    return {"status": "ok", "wall_s": 10.0, "by_model": {model: {"output": output}},
            "reported": {"model_usage": {}}, "truncated_responses": 0, **extra}


def test_plan_dedupes_runs_and_puts_strata_last():
    specs = smoke.plan(["effort", "subagent-effort"], B)
    assert [s.contestant for s in specs][-2:] in (["strata@low", "strata"], ["strata", "strata@low"])
    assert sorted(s.contestant for s in specs) == sorted(["haiku@low", "haiku", "haiku@xhigh", "opus-haiku", "strata@low", "strata"])


def test_effort_verdict(tmp_path):
    for contestant, out in (("haiku@low", 100), ("haiku@xhigh", 400), ("strata@low", 200), ("strata", 900)):
        write_run(tmp_path, "reasoning", contestant, metrics(out), {"answer.txt": "4001\n"})
    v = smoke.verdict_effort(smoke.Results(B, tmp_path, tmp_path / "ws"))
    assert v.status == "PASS" and "answer 4001" in v.lines[0]
    write_run(tmp_path / "x", "reasoning", "haiku@low", metrics(500))
    for contestant, out in (("haiku@xhigh", 400), ("strata@low", 200), ("strata", 900)):
        write_run(tmp_path / "x", "reasoning", contestant, metrics(out))
    assert smoke.verdict_effort(smoke.Results(B, tmp_path / "x", tmp_path / "ws")).status == "REVIEW"


def test_sandbox_verdict(tmp_path):
    hidden = ("== home\n.\n== home tree\n/home/u\n/home/u/bench-ws\n== ssh\nls: cannot access '/home/u/.ssh': No such file or directory\n"
              "== run user\nls: cannot open directory '/run/user/1000': Permission denied\n== claude config\nls: cannot access '/home/u/.claude': No such file or directory\n")
    write_run(tmp_path, "sandbox-audit", "haiku", metrics(10), {"audit.txt": hidden})
    assert smoke.verdict_sandbox(smoke.Results(B, tmp_path, tmp_path / "ws")).status == "PASS"
    leaky = hidden.replace("ls: cannot open directory '/run/user/1000': Permission denied", "srw------- openssh_agent")
    write_run(tmp_path / "x", "sandbox-audit", "haiku", metrics(10), {"audit.txt": leaky})
    v = smoke.verdict_sandbox(smoke.Results(B, tmp_path / "x", tmp_path / "ws"))
    assert v.status == "FAIL" and "run user" in v.lines[0]


def test_blank_config_verdict(tmp_path):
    init = {"type": "system", "subtype": "init", "mcp_servers": [], "plugins": [{"name": "p", "path": "builtin"}],
            "agents": ["claude", "Explore"], "memory_paths": {"auto": "/h/bench-ws/x.state/claude-home/projects/m/"}}
    write_run(tmp_path, "hello", "haiku", metrics(1), transcript=[init], campaign=smoke.HELLO_CAMPAIGN)
    assert smoke.verdict_blank_config(smoke.Results(B, tmp_path, tmp_path / "ws")).status == "PASS"
    write_run(tmp_path, "hello", "sonnet", metrics(1), campaign=smoke.HELLO_CAMPAIGN,
              transcript=[{**init, "agents": ["claude", "my-reviewer"], "mcp_servers": [{"name": "github"}]}])
    v = smoke.verdict_blank_config(smoke.Results(B, tmp_path, tmp_path / "ws"))
    assert v.status == "FAIL" and len(v.lines) == 2


def test_strata_log_stats(tmp_path):
    log = tmp_path / "strata-server.log"
    log.write_text("\n".join([
        "[strata] thinking limited to 3072 of max_tokens 4096 so the answer has room",
        "[strata] thinking: 40 of budget 3072 (max 4096) tokens, 50 tok/s, 1 s",
        "[strata] thinking: 118 of budget 3072 (max 4096) tokens, 52.6 tok/s, 3 s",
        "[strata] answering: 315 of max 4096 tokens, 59.2 tok/s, 6 s",
        "[strata] done: 318 tokens in 6 s (59.5 tok/s) (stop, cancel=False), expert cache 58.7% hit",
        "[strata] thinking budget reached (3072 tokens): wrapping up the thinking",
        "[strata] thinking: 3072 of budget 3072 (max 4096) tokens, 50 tok/s, 60 s",
        "[strata] done: 4096 tokens in 80 s (51.2 tok/s) (length, cancel=False), expert cache 60% hit",
    ]) + "\n")
    s = strata_log_stats(log)
    assert s["responses"] == 2 and s["thinking_tokens"] == 118 + 3072 and s["total_tokens"] == 318 + 4096
    assert s["finish_reasons"] == {"stop": 1, "length": 1} and s["thinking_cut"] == 1 and s["max_tokens"] == 4096


def test_sandbox_check_end_to_end_with_the_fake_claude(tmp_path):
    kw = dict(claude_bin=FAKE, sandbox=False, ws_root=tmp_path / "ws", runs_root=tmp_path / "runs")
    smoke.run(["sandbox"], B, echo=lambda s: None, **kw)
    v = smoke.report(["sandbox"], B, runs_root=tmp_path / "runs", ws_root=tmp_path / "ws")["sandbox"]
    # The fake writes no audit.txt: the check must say so rather than pass.
    assert v.status == "FAIL" and "audit.txt missing" in v.lines[0]
    assert (tmp_path / "runs" / smoke.CAMPAIGN / "smoke-report.json").is_file()
