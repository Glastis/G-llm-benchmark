"""Contestants served by Anthropic, through the subscription (PLAN §10.6). Nothing is executed here."""

from __future__ import annotations

import os
from pathlib import Path

from bench.config import ROOT, Contestant, orchestrator_preamble, subagents_json

# Long-lived subscription token (`claude setup-token`). Variable name to be confirmed in smoke
# test #9. `--bare` is ruled out: it never reads OAuth and simplifies the system prompt.
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"

COMMON_ENV = {
    "DISABLE_AUTOUPDATER": "1",
    "DISABLE_TELEMETRY": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
}


def base_argv(model: str, effort: str) -> list[str]:
    return [
        "claude", "-p",                             # the statement comes on stdin: Firejail caps arguments at 4,128 characters
        "--model", model,
        "--effort", effort,
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "bypassPermissions",   # safe only inside Firejail
        "--strict-mcp-config",                      # no MCP server
    ]


def command(c: Contestant, claude_home: Path, state_dir: Path, worker: Contestant | None = None) -> tuple[list[str], dict[str, str]]:
    """argv and environment variables of a run. `claude_home` is the run's blank CLAUDE_CONFIG_DIR,
    `state_dir` the writable folder where bench-worker writes workers/, `worker` the executing
    contestant of the orchestrated configurations."""
    argv = base_argv(c.model, c.effort)
    env = {**COMMON_ENV, "CLAUDE_CONFIG_DIR": str(claude_home)}
    if token := os.environ.get(TOKEN_ENV):
        env[TOKEN_ENV] = token
    if c.workers:
        argv += ["--append-system-prompt", orchestrator_preamble(ROOT / c.preamble, c.workers.via)]
        if c.workers.via == "subagent":
            argv += ["--agents", subagents_json()]
        else:
            env["BENCH_RUN_DIR"] = str(state_dir)
            env["PATH"] = f"{state_dir / 'bin'}:{os.environ.get('PATH', '')}"   # copy of bench-worker
            env["BENCH_STRATA_MAX_OUTPUT"] = str(worker.max_output_tokens or 4096)
            env["BENCH_STRATA_EFFORT"] = worker.effort
    return argv, env
