# G llm benchmark

Cost × quality benchmark of coding agents: Strata running locally, alone or driven by Opus, against Haiku, Sonnet and Opus.

- [PLAN.md](PLAN.md): goal, contestants, tasks, phases and decisions.
- [ARCHITECTURE.md](ARCHITECTURE.md): the harness, its files and how tokens are measured.
- [GRADING.md](GRADING.md): the author's grid for grading the code tasks.

## Status

`validate`, `plan`, `run`, `collect`, `grade`, `judge` and `smoke` work. Every contestant passed the smoke runs. The four tasks are written. `grade` grades the four tasks where a formula is objective, `judge` has a blind Opus grade the code of T1 and T4 and the truth of T2, and the author keeps the final grade; `report` is still to come.

## Requirements

- Linux, [uv](https://docs.astral.sh/uv/), [Claude Code](https://claude.com/claude-code), Firejail and jq;
- for the Strata contestants: an Anthropic-compatible Strata server that is already running;
- for the tasks, all in C++: g++, CMake and Ninja, plus the SQLite (T3), SDL2 and libpng (T4) development packages;
- for `bench grade`: clang-tidy.

| Variable | Role |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | subscription token (`claude setup-token`), for the Anthropic contestants |
| `STRATA_URL` | Strata server address, `http://127.0.0.1:8080` by default |
| `STRATA_SERVER_LOG` | Strata server log, to keep an excerpt per run; optional, the most recent `*.server.log` in `$XDG_STATE_HOME/strata/runtime` by default |
| `BENCH_WS_ROOT` | folder for the run workspaces, `~/bench-ws` by default; must be inside the home |
| `CC_REPO` | clone of the private ComputerCraft repository, only to rebuild the T2 fixture (`tasks/T2-archi-summary/make_fixture.py`) |

## Commands

```bash
uv sync
uv run bench validate                 # checks configs, prices and tasks
uv run bench plan c01                 # lists the planned runs, launches nothing
uv run pytest
```

Before a run with an Anthropic contestant, once per terminal: `claude setup-token`, then the line below, which waits for the token without displaying it or keeping it in the history.

```bash
read -rs CLAUDE_CODE_OAUTH_TOKEN && export CLAUDE_CODE_OAUTH_TOKEN
```

The "hello" smoke run of one contestant: `uv run bench run s01 --tasks-dir tasks/smoke --only hello --contestants haiku --reps 1`. Targeted checks: `uv run bench smoke` lists them.
