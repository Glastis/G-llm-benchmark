# Coding-agent benchmark — harness architecture

> Status: **runner and collector written** (2026-10-25). They are tested end to end with a fake `claude`, and every contestant passed the smoke runs. The author compares the deliverables by hand; the report is still a stub.
> The plan and the tasks are in [PLAN.md](PLAN.md).

## 1. Principles

1. **One agent harness for everyone**: headless Claude Code (`claude -p --output-format stream-json`). Strata already goes through it via `ANTHROPIC_BASE_URL`, so the only variable is the model (except for the delegation mechanism of the orchestrated contestants, §6).
2. **Everything is declarative**: contestants, prices and tasks live in versioned YAML files. A run is fully described by `(campaign, task, contestant, repetition)`.
3. **Running, collecting and reporting are separate steps** and can be replayed.
4. **The bench repository is never reachable by the agent**: the workspace is outside the repository, inside a sandbox.
5. **We compute the price ourselves** from raw tokens, rather than taking Claude Code's `total_cost_usd`. This keeps control over dated prices, the Haiku tier above 100K, and Strata at $0.

## 2. Overview

```
  config/contestants.yaml   config/pricing.yaml   tasks/<T>/{prompt.md, fixture/}
            │                      │                          │
            ▼                      │                          ▼
  ┌──────────────────────────── bench run ─────────────────────────────┐
  │ 1. copy fixture/ → ~/bench-ws/<run_id>/ (git init, commit 0)       │
  │ 2. backend.ensure_ready()   strata: /health, model loaded, outside │
  │                             the clock                              │
  │ 3. run claude -p (stream-json) in the sandbox, clock, timeout      │
  │    └─ orchestrated: subagent (Haiku) or bench-worker (Strata), §6  │
  │ 4. sample GPU power (Strata, indicative)                           │
  │ 5. archive transcript, workers/, git diff, deliverables, server log│
  └───────────────────────────────┬────────────────────────────────────┘
                                  ▼
                 runs/<campaign>/<T>/<C>/r<k>/   (raw, immutable)
                                  │
   bench collect ─────────────────┼──► metrics.json   tokens per model, $, time, turns
   bench report  ─────────────────┴──► runs/<campaign>/report/  time, cost, tokens
```

## 3. Tree

```
benchmark_ai/
├── PLAN.md · ARCHITECTURE.md · GRADING.md · GRADING-SHEET.md · README.md · .gitignore
├── pyproject.toml                  # uv, Python ≥ 3.12, `bench` command
├── config/
│   ├── contestants.yaml            # the 14 contestants
│   ├── pricing.yaml                # dated $/MTok, tiers
│   ├── orchestrator.md             # preamble of the orchestrated contestants: common core + one paragraph per mechanism
│   ├── judge/{code,summary}.md     # instructions of the blind judge; code.md takes GRADING.md's code grid as is
│   ├── agents/haiku-worker.json    # Haiku subagent, passed with --agents to opus-haiku only
│   └── firejail/bench.profile      # sandbox: hardening, session masking
├── tasks/
│   ├── T1-simulation/
│   │   ├── task.yaml               # timeout, deliverables, grading_sheet, grader
│   │   ├── grader/                 # grade.py, oracle.py, hidden scenarios and expected traces (never in the fixture)
│   │   ├── prompt.md               # task statement, sent as is
│   │   └── fixture/                # the agent's starting point
│   ├── T2-archi-summary/           # + make_fixture.py (rebuilds the private fixture, not committed), grader/ (form, references)
│   ├── T3-pr-review/               # + build/: base/ (main), build_pr.py (rebuilds the PR), seeded_bugs.yaml (answer key); grader/
│   ├── T4-game/                    # + fixture/assets/{opaque,transparent}/; grader/: rules.py (oracle), hidden.py, showcase.py, tiles.py, png.py, fuzz.c
│   └── smoke/                      # smoke-test tasks (hello, reasoning, big-file, sandbox-audit), loaded with --tasks-dir tasks/smoke
├── bench/                          # Python package (✓ = implemented, otherwise stub)
│   ├── cli.py                      # ✓ validate, plan, run, collect, grade, judge, smoke (run, judge and smoke ask for confirmation) · stub: report
│   ├── config.py                   # ✓ pydantic schemas, loading, cross-checks
│   ├── campaign.py                 # ✓ seeded plan, exclusive block
│   ├── smoke.py                    # ✓ targeted smoke checks of §9: contestant variants, runs, verdicts
│   ├── runner.py                   # ✓ workspace, Firejail, clock, timeout, statuses, resume, archive
│   ├── backends/
│   │   ├── anthropic.py            # ✓ claude -p argv + env for Haiku, Sonnet and Opus
│   │   └── strata.py               # ✓ health, model check, argv + env
│   ├── worker/bench-worker         # ✓ script Opus calls for Strata (sequential, flock)
│   ├── collect.py                  # ✓ stream-json → metrics.json (deduplication, cost per request, alert)
│   ├── grade.py                    # ✓ runs each task's grader on a copy of final/ → auto.json, objective cells of grade.md
│   ├── cpp_metrics.py              # ✓ C++ code metrics of T1 and T4 (lizard, clang-tidy, strict warnings), PLAN §10.29
│   ├── judge.py                    # ✓ blind judge (Opus xhigh): redacted copy, sandbox, two passes → judge.json, PLAN §10.31
│   ├── pricing.py                  # ✓ tokens × prices (tiers, 5m/1h cache, unknown price = error)
│   ├── energy.py                   # ✓ nvidia-smi power.draw (GPU only, indicative), integrated to Wh
│   ├── report.py                   # to come: HTML report
│   └── tests/                      # pytest: prices, plan, configs, runner and collector (fake claude)
└── runs/                           # .gitignore — raw data, and each campaign's report in runs/<campaign>/report/
```

## 4. Configuration (in place)

The files are the source of truth. `bench validate` loads them with strict schemas (`bench/config.py`), then cross-checks them: models present in the prices, workers that exist, a preamble with the right paragraph, task statements and fixtures present.

- **[`config/contestants.yaml`](config/contestants.yaml)**: the 14 contestants, with model, effort, `exclusive`, `workers: {contestant, via}` and `max_output_tokens` for Strata.
- **[`config/pricing.yaml`](config/pricing.yaml)**:
  - dated prices, with the Haiku tiers;
  - an unknown price stays `null`: `validate` flags it, and the cost computation fails instead of counting 0. Every price was checked against the official pricing page on 2026-10-25. The cross-check with Claude Code (§8) caught one error on the first Sonnet run: Sonnet 5.5 cache reads cost $0.10/MTok (0.05 × input, like Opus 5.5), not $0.20.
- **[`config/agents/haiku-worker.json`](config/agents/haiku-worker.json)**: the `worker` subagent. It is passed with `--agents` to opus-haiku only, so that no other contestant can delegate to Haiku.
- **[`config/orchestrator.md`](config/orchestrator.md)**: a common core, then one paragraph per mechanism, separated by `<!-- mechanism: … -->`.
- **`tasks/<T>/task.yaml`**: timeout, deliverables and `grading_sheet` (T1 and T4: graded with [GRADING.md](GRADING.md)).

Task statements and agent-facing prompts are in English, the language every contestant, Strata included, handles best.

## 5. Running a run

1. **Campaign plan**: `campaign.py` produces the list of runs in a seeded order. It groups the `exclusive` contestants into blocks and alternates contestants elsewhere. The resume registry is each run's `run.json`:
   - a finished run (`ok`, `timeout`, `error`) is never rerun;
   - an interrupted attempt, or one stopped by the subscription limit, is set aside (folders renamed to `.attempt-<date>`, never deleted), then redone at the next launch;
   - `bench run` lists the runs to launch and asks for confirmation before starting. At the end, even after a stop, it runs `bench collect` on the campaign. There is no cost cap (PLAN §10.7): `collect` only flags runs that cost more than 3 times their contestant's median in API equivalent.
2. **Workspace**: `fixture/` is copied to `~/bench-ws/<run_id>/`, then `git init` and an initial commit. The final diff measures what the agent produced.
3. **Backend preparation**:
   - Anthropic: nothing to do.
   - Strata: `/health` must answer with the right model loaded, and the check happens outside the clock. The harness **never** starts a model, since loading can freeze the PC for 1 to 3 minutes. If the Coder is not serving, the run stops before the clock starts and asks to launch `strata-coder`. Since the exclusive block comes at the end of the campaign, that is a single intervention. The server log is read during the run (prefill and decode throughput).
4. **Launch**, in the workspace and under Firejail (`backends/anthropic.py` and `backends/strata.py` build the command):
   ```
   claude -p --model <id> --effort <level> --output-format stream-json --verbose \
          --permission-mode bypassPermissions --strict-mcp-config
          [--append-system-prompt "<preamble>"]           # orchestrated contestants
          [--agents '<haiku-worker.json>']                # opus-haiku, sonnet-haiku
          < prompt.md   # on stdin: Firejail refuses any argument over 4,128 characters
   env: CLAUDE_CONFIG_DIR=<blank folder of the run>  DISABLE_AUTOUPDATER=1  DISABLE_TELEMETRY=1
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
        Anthropic: CLAUDE_CODE_OAUTH_TOKEN (subscription token, name to confirm in smoke test #9)
        strata: ANTHROPIC_BASE_URL=http://127.0.0.1:8080, ANTHROPIC_AUTH_TOKEN=strata-local,
                models → strata, CLAUDE_CODE_MAX_CONTEXT_TOKENS, CLAUDE_CODE_MAX_OUTPUT_TOKENS
        opus-strata, sonnet-strata: BENCH_RUN_DIR=<run state>, PATH += <run state>/bin, BENCH_STRATA_EFFORT, BENCH_STRATA_MAX_OUTPUT
   ```
   `--bare` is ruled out: it never reads OAuth, so it is incompatible with the subscription, and it simplifies the system prompt (`CLAUDE_CODE_SIMPLE=1`), which would make the runs unrepresentative.
5. **Clock and timeout**: wall-clock time of the process. When the timeout expires, SIGTERM then SIGKILL, and the status becomes `timeout`. Partial deliverables are kept and graded anyway.
   If `claude` stops on a subscription-limit error, the status becomes `quota` (neither success nor give-up) and the campaign stops. At the next launch this run is redone. The limit is detected from the stream's `rate_limit_event` (status other than `allowed`), with `QUOTA_MARKERS` in `runner.py` as a fallback on the error text.
   The final diff ignores `build/`, `node_modules/` and Python caches, through the workspace's `.git/info/exclude`.
6. **Archive** in `runs/…/r<k>/`, including `final/`, the whole final workspace as git sees it (build outputs and caches excluded). The run's state folder (`~/bench-ws/<run_id>.state`: `CLAUDE_CONFIG_DIR`, `workers/`) is moved there afterwards, because the sandbox never writes into the bench repository. Contents: `transcript.jsonl`, `workers/*.jsonl`, `workspace.diff`, `deliverables/`, `stderr.log`, `strata-server.log` (excerpt), `energy.csv`, `run.json` (resolved config, versions, timestamps).

## 6. Opus → workers orchestration

**Decided (PLAN §10.5)**: each configuration has its own mechanism, as close as possible to real-world usage.

```
opus-haiku                                    opus-strata
──────────                                    ───────────
claude -p  (Opus 5.5, xhigh)                  claude -p  (Opus 5.5, xhigh)
   │  native Agent tool                          │  Bash tool, one call at a time
   ▼                                             ▼
"worker" subagent                             bench-worker "subtask"
(claude-haiku-5-5, medium)                       │  flock lock: never 2 Strata calls
   │  same Anthropic endpoint                    ▼
   │  usage in the main stream-json           claude -p --model strata  (ANTHROPIC_BASE_URL=:8080)
   │                                             │  → $BENCH_RUN_DIR/workers/NNN.jsonl
   ◄── subagent result                           ◄── stdout: short final summary
```

- **opus-haiku**: the `worker` subagent is defined in `config/agents/haiku-worker.json` (Haiku 5.5 model, short instructions) and passed with `--agents` to this contestant and to `sonnet-haiku` only. Opus can launch several in parallel, as in everyday Claude Code use. The definition pins `effort: medium`, like the standalone `haiku` contestant (2026-10-26): without it, the subagent took the session's `xhigh`. Opus can still pass an effort when it launches a subagent, which overrides the field; it then shows in the transcript, in the Agent tool call.
- **opus-strata**: `bench-worker` reproduces the logic of `strata-agent` (health check, Strata environment) without depending on it, since the Strata installation stays outside the sandbox. The runner copies it into the run's state folder, read-only, so that the bench repository stays invisible. It adds `--output-format stream-json` and logs every call. Calls are **sequential**: Opus waits for one worker to finish before the next, and a lock guarantees that no concurrent call reaches Strata.
- **Preamble** (`config/orchestrator.md`): an identical common core (delegate the implementation, split by files, review, write code yourself only as a last resort), followed by a paragraph specific to the mechanism ("use the worker subagent" or "run `bench-worker`").
- **Consequence for the analysis**: the comparison between opus-haiku and opus-strata mixes the executing model and the mechanism (native parallel versus sequential through Bash). The report says so explicitly. Opus alone (`opus-medium`) runs at `medium`, not at the orchestrators' `xhigh` (PLAN §10.22).
- **Safeguards**: each worker call has its own timeout, capped by the run's remaining time, and the number of worker calls per run is limited.

## 7. Isolation and security

- **Blank Claude Code configuration** (an empty `CLAUDE_CONFIG_DIR` created for each run): no global `CLAUDE.md` (the author's personal instructions would skew the tokens), no plugins, MCP, skills or memory. The smoke test checks that the system prompt size is identical across contestants, apart from the preamble.
- **Sandbox: Firejail** (**decided, PLAN §10.8**). The profile `config/firejail/bench.profile` wraps the `claude` process and all its children, workers included:
  - **Home whitelist** reduced to the strict minimum:
    - writable: the run's workspace (`~/bench-ws/<run_id>`) and its state folder (`~/bench-ws/<run_id>.state`: `CLAUDE_CONFIG_DIR`, `workers/`);
    - read-only: the `claude` binary found in the PATH (link and target), `$PYENV_ROOT` and `$NVM_DIR` if set, and the copy of `bench-worker`. The runner computes these paths (`toolchain_paths`): none is hard-coded in the profile.
    - Everything else in the home is invisible, including the bench repository.
    - **Checked on 2026-10-25** with harmless commands: the bench repository, `~/.claude` and the Strata installation cannot be found in the sandbox, while `claude`, `g++` and Strata (`/health`) stay reachable. A write outside the whitelist stays in the sandbox and does not reach the real disk.
  - **Network shared with the host**: Strata on `127.0.0.1:8080` and the Anthropic servers must be reachable. Firejail does not filter by domain. The tasks need no other access, but nothing technically forbids it. This is an accepted limitation, and network calls remain visible in the transcripts.
  - **Hardening**: `caps.drop all`, `nonewprivs`, `noroot`, `nogroups`, `seccomp`, `private-tmp`, `private-dev`, no sound, GPU, video, input devices or U2F key.
  - **User session masked**: `/run/user/<uid>` (SSH agent, gpg, keyring, kwallet, Wayland, PipeWire), the X cookie (`~/.Xauthority`) and both D-Bus buses. **Found and fixed on 2026-10-25**: before this masking, the SSH agent was reachable from the sandbox, so an agent could have pushed to GitHub with the user's keys.
  - **Remaining limitation**: `x11 none` requires an isolated network, which is incompatible with Strata and Anthropic. The abstract X socket therefore stays reachable, but without a cookie and without `DISPLAY`, and the X server has access control enabled.
  - **Per-run temporary folders**: `/tmp`, `/var/tmp` and `/dev/shm` are isolated. `/dev/shm` was shared with the machine, and therefore between runs, before `private-dev` was added. **Checked on 2026-10-25**: a file dropped into `/dev/shm` by one run does not reach the machine and stays invisible to the next run. `claude`, `g++` (build and run), `python3`, `node` and Strata stay reachable.
  - **A blank `CLAUDE_CONFIG_DIR` per run**: no session or todo history carries over from one run to the next.
- **Answer key out of reach**: the bench repository is never whitelisted, so T3's `build/seeded_bugs.yaml` stays invisible to the agent.
- **Authentication (subscription)**: the blank `CLAUDE_CONFIG_DIR` does not contain the user's session. A long-lived OAuth token is therefore used, presumably through `claude setup-token`, to be confirmed in phase 1. It is passed as an environment variable to the `claude` process only, never written into `runs/`, and transcripts are scrubbed before archiving.

## 8. Measuring tokens and cost

- **Source: the session journals.** Claude Code writes a journal per session in the run's `CLAUDE_CONFIG_DIR` (`claude-home/projects/**.jsonl`), with each message's **final** usage (`input_tokens`, `output_tokens`, `cache_creation_input_tokens` with the 5m/1h split, `cache_read_input_tokens`). The `stream-json` on stdout only carries a snapshot taken while the message streams. **Found on the first real run**: it reported 28 output tokens where Claude Code counted 223, the difference being hidden thinking. The stream is therefore used for events only (tool calls, `result`, `rate_limit_event`), and as a flagged fallback when no journal exists.
- **Deduplication**: a message spans several lines, one per content block, repeating the same `message.id`. `collect.py` counts each id once, keeping the largest output count.
- **Cross-check with Claude Code**: the `result` event gives `duration_ms`, `num_turns` and, per model, the tokens and list-price cost Claude Code computed itself (`modelUsage.costUSD`). `collect.py` compares input, output, cache read and cache write tokens, and the cost of Anthropic models, with its own figures, and warns on any gap. For the Strata contestant, Claude Code's single `strata` model is compared with all our rows. On the six `s01` smoke runs (2026-10-25), every figure matches, for example $0.00165191 on the Haiku run.
- **Subscription**: the last `rate_limit_event` gives the subscription utilization (5-hour and 7-day windows), recorded in `metrics.json` to watch the quota during a campaign.
- **Haiku subagents** (opus-haiku): **confirmed on 2026-10-25** (run `s01_hello_opus-haiku_r1`). Each subagent call has its own journal under `<session>/subagents/agent-*.jsonl`, read with the others; tokens and cost match Claude Code's per-model figures for both Opus and Haiku. The stream-json only showed one of the subagent's two messages, so `subagent_calls` and `subagent_requests` are counted from the journals.
- **Strata workers** (opus-strata): each call is a separate `claude -p` session sharing the run's `CLAUDE_CONFIG_DIR`, so its journal is read with the others; `workers/*.jsonl` gives its tool calls.
- **Computation**: `pricing.py` applies `pricing.yaml` request by request, which the Haiku tier above 100K prompt tokens requires. The result is aggregated per model, workers included.
- **Strata**: tokens are counted and shown, at $0. Strata reports cache writes as a total with a zero 5m/1h split: `collect.py` counts the total. The runner keeps the excerpt of the server log written during the run (`strata-server.log`), from the most recent `*.server.log` in `$XDG_STATE_HOME/strata/runtime` or from `$STRATA_SERVER_LOG`. That log shows decode throughput and the thinking budget of each answer. Energy is measured **on the GPU side only** (`nvidia-smi --query-gpu=power.draw`, one sample per second). The CPU counter (RAPL) is only readable as root (PLAN §10.13), so the figure underestimates real consumption, while the CPU works hard. It is converted to € and shown **alongside** the Anthropic cost, as an indication, without being added to it.
- **`metrics.json`**:
  ```json
  {
    "run_id": "c01_T1_opus-strata_r2",
    "status": "ok",
    "wall_s": 812.4,
    "turns": 31, "tool_calls": 57, "tool_errors": 3, "worker_calls": 6,
    "by_model": {
      "claude-opus-5-5": { "input": 1200, "cache_write_5m": 84000, "cache_read": 910000, "output": 41000, "usd": 1.41 },
      "strata":          { "input": 2300, "cache_read": 380000, "output": 52000, "usd": 0.0 }
    },
    "usd_total": 1.41,
    "gpu_energy_wh": 41.7
  }
  ```
- **`grade.md`**: for a task with `grading_sheet`, `collect.py` also drops [GRADING-SHEET.md](GRADING-SHEET.md) into each finished run's folder, with the task, contestant, rep, time and cost filled in. An existing `grade.md` holds the author's grades: it is never overwritten.

## 9. Phase 1 smoke tests (before any task)

| # | Check | How |
|---|---|---|
| 1 | Usage is complete for every contestant | "hello" task → non-empty `metrics.json` for every model |
| 2 | Effort is actually applied | same prompt at `low` and at `high` → clearly different output tokens (Claude **and** Strata). **PASS on 2026-10-25** (`bench smoke effort`) |
| 3 | Strata is properly isolated | `/health` → expected model, no call to `api.anthropic.com` during the run. **Run `s01_hello_strata_r1` (2026-10-25)**: every message comes from `qwen3.8-flash-next-coder-iq1_m`, and the stream has no `rate_limit_event`, which only the subscription sends |
| 4 | Haiku subagent effort | does the subagent run at `medium`? If not, record the actual effort. **First hint (2026-10-25)**: on "hello", the Haiku subagent reported 327 thinking tokens where Haiku alone at `medium` reported none, which suggests it inherits the orchestrator's `xhigh`. **Not settled**: on `reasoning`, Opus answered alone without delegating. **Fixed (2026-10-26)**: the definition now pins `effort: medium`. To check in the pilot that Opus passes no other effort in its Agent tool calls |
| 5 | Strata output cap: 4,096 versus 16,384 | Same task with both values, 3 attempts each: write a C++ file of about 600 lines, high reasoning. Compare truncated responses (`stop_reason: max_tokens`), success, time, the share of the cap taken by reasoning and compaction behaviour. The author chooses the value on these numbers (PLAN §10.15). **First hint (2026-10-25)**: the Strata server log shows the 4,096 cap is applied, and that Strata reserves up to 3,072 of it for thinking so that the answer keeps some room. **Not run** (author's choice, 2026-10-25: too long for what it settles). The cap stays at 4,096; truncated responses and `length` finishes are counted in every run's metrics, so the pilot will show whether it hurts. **Raised to 32,768 (2026-10-26)** after the T3 pilot run (PLAN §10.25), **then to 65,536 (2026-10-27)** (PLAN §10.27) |
| 6 | Delegation works | opus-haiku uses the subagent and opus-strata calls `bench-worker`. In both cases, worker usage is captured. **Confirmed for both on 2026-10-25**: one subagent call for opus-haiku, one `bench-worker` call for opus-strata (Strata priced at $0, Opus matching Claude Code) |
| 7 | The configuration is blank | identical system prompt size, no trace of the global `CLAUDE.md` |
| 8 | The sandbox is tight | the agent lists what it can see from inside the sandbox → the bench repository and private folders are not there. **PASS on 2026-10-25** (`bench smoke sandbox`) |
| 9 | The subscription works with a blank configuration | **Confirmed on 2026-10-25** for `claude -p` with `CLAUDE_CODE_OAUTH_TOKEN` alone (run `s01_hello_haiku_r1`). |

`bench smoke` runs the checks that the "hello" runs of `s01` could not settle (#1, #3, #6 and the subscription part of #9 already passed there). Each check names the runs it needs, in the `s02` campaign, and turns them into a verdict: PASS, FAIL, or REVIEW when the numbers are for the author to judge. It uses contestant variants that exist only for these checks (`haiku@low`, `haiku@xhigh`, `strata@low`, `strata@4096`, `strata@16384`).

| Check | # | Runs | Verdict |
|---|---|---|---|
| `effort` | 2 | `reasoning` × haiku low/medium/xhigh, Strata low/high | PASS if the higher effort produces more output, for Claude and for Strata |
| `subagent-effort` | 4 | `reasoning` × opus-haiku, compared with Haiku alone at medium and xhigh | REVIEW: which one the subagent's output is closest to |
| `strata-cap` | 5 | `big-file` × Strata at 4,096 and at 16,384, 3 runs each | REVIEW: success (built and run inside the sandbox), time, truncated responses, thinking share |
| `blank-config` | 7 | none: reads the init event of every s01 and s02 run | PASS if no MCP server, only built-in plugins and agents, memory in the run's own config. **PASS on 2026-10-25** for the 7 s01 runs |
| `sandbox` | 8 | `sandbox-audit` × haiku | PASS if the bench repository, `~/.ssh`, the user's `~/.claude` and the session sockets are invisible |

**Results on 2026-10-25** (`s02` campaign):

| Run | Cost (API eq.) | Time | Output tokens | Thinking tokens | Answer |
|---|---|---|---|---|---|
| haiku low | $0.0018 | 3.8 s | 327 | 217 | 4001 |
| haiku medium | $0.0018 | 4.2 s | 447 | 211 | 4001 |
| haiku xhigh | $0.0019 | 6.0 s | 462 | 350 | 4001 |
| opus-haiku (did not delegate) | $0.0630 | 7.7 s | 406 | 179 | 4001 |
| strata low | $0 | 13.7 s | 447 | 333 (server log) | 4001 |
| strata high | $0 | 16.1 s | 689 | 530 (server log) | 4001 |
| sandbox-audit on haiku | $0.0037 | 10.0 s | 1,401 | 687 | PASS |

## 10. Grading

`bench grade` (PLAN §10.28) copies each finished run's `final/` into `~/bench-ws/grading/`, runs the task's grader on it, and writes `auto.json` next to the run: scores where a formula is objective, checks, raw figures and details. For T1 and T4 it also writes those figures into `grade.md`, marked `(auto)`, only where a cell is blank or holds an earlier `(auto)` value; every `bench grade` refreshes them, from `auto.json` when the run is already graded. A grader that runs agent code does it with `sandbox_exec`, in the agents' sandbox; graders and their hidden data stay in the bench repository, which the sandbox cannot see. The grading builds other than the imposed one (warnings, sanitizers, strict warnings) get their flags through a small `g++` wrapper written in the copy (`cpp_metrics.compiler`), after the project's own flags and on every compile and link: a `CMakeLists.txt` can overwrite `CMAKE_CXX_FLAGS`, not that.

| Task | Scores | Figures and checks |
|---|---|---|
| T1 | `statement`: 10 × mean match of the 10 hidden scenarios with the oracle; `working`: share of the 28 robustness checks passed (invalid inputs, command-line errors, no crash or timeout) | exact scenarios, time and peak RAM on 200,000 passengers, warnings, sanitizer reports, standard library only, output format |
| T2 | none | sections, words (as `wc -w`), diagram, no edit, every path or identifier in inline code checked against the fixture |
| T3 | `review`: 10 × F1 against `seeded_bugs.yaml` (same file, line within 5, a keyword) | found, found ignoring the lines, unmatched comments in full, same severity, no edit |
| T4 | `statement`: 10 × mean share of the test-mode lines equal to the oracle's, over 13 hidden scenarios; `working`: share of the robustness checks passed (each test-mode run ends, random clicks and keys under sanitizers end cleanly and quit on SDL_QUIT, nothing on stderr) | exact scenarios, tiles (share of cells, composed buildings, distinct types, roads that join), idle CPU and RAM, SDL2 and libpng only; the screenshots go to the run's `auto/` |

For T1 and T4, `bench/cpp_metrics.py` adds the code metrics of PLAN §10.29 under `figures.code`, one group per criterion of GRADING.md, and a one-line summary per criterion in the *Notes* column of `grade.md`. The strict build and clang-tidy configure the agent's CMake project, so they run in the sandbox; lizard and the rest only read the sources.

`bench judge` (PLAN §10.31) has Opus at `xhigh` grade what no formula measures: the five code criteria of GRADING.md for the tasks with `judge: code` (T1, T4), the truth and completeness of the summary for `judge: summary` (T2). Each pass copies the run's `final/` into `~/bench-ws/judge/<random>/`, without `build/`, redacts in the agent's files every contestant id, model name and the run's own workspace path (the fixture's files stay as they are), adds the statement as `_judge/STATEMENT.md`, and runs `claude -p` in the agents' sandbox with `config/judge/<kind>.md` on stdin. The judge writes `_judge/judgement.json`; its transcript and config go to the run's `judge/pass<n>/`. Two passes per run, all the first ones before the second ones, each list shuffled with a seed. `judge.json` keeps the passes, the mean grade and the spread; the means go to the *Score* column of `grade.md`, marked `(judge)`. A subscription limit stops the command, and the next launch resumes with the missing passes.

The author grades the rest by hand from `deliverables/` and `final/` (§5), and keeps the final grade everywhere.

- **`report.py`** (to come) gives time, cost and tokens per contestant and per task (median and spread over the repetitions), with Strata GPU energy as an indication.

## 11. Stack

Python ≥ 3.12 with **uv** · **Firejail** (sandbox) · `typer` (CLI) · `pydantic` (config and result schemas) · `pyyaml` · `lizard` and clang-tidy (code metrics) · g++, CMake and Ninja, SQLite, SDL2 and libpng (the C++ tasks) · `plotly` (standalone HTML report).

## 12. CLI

```bash
uv run bench validate                    # ✓ configs, prices, tasks (warnings and errors)
uv run bench plan c01 [--reps 3] [--only T1-simulation,T3-pr-review] [--contestants strata,opus-strata] [--seed 0]
                                         # ✓ ordered list of runs, launches nothing
uv run bench run c01 [same options as plan] [--yes]
                                         # ✓ launches unfinished runs (real agents), after confirmation, then collects
uv run bench run s01 --tasks-dir tasks/smoke --only hello --contestants haiku --reps 1
                                         # ✓ suggested first real try: one "hello" run on Haiku
uv run bench collect c01                 # ✓ metrics.json and grade.md per run, summary table, cost alerts
uv run bench grade c01 [--only …] [--contestants …] [--force]
                                         # ✓ graders on the finished runs (sandboxed builds, no agent): auto.json, grade.md
uv run bench judge c01 [--only …] [--contestants …] [--passes 2] [--seed 0] [--force] [--yes]
                                         # ✓ blind judge (real agents, Opus xhigh), after confirmation: judge.json, grade.md
uv run bench smoke                       # ✓ lists the smoke checks of §9 and their runs, launches nothing
uv run bench smoke effort sandbox        # ✓ launches their missing runs (real agents), after confirmation, then gives the verdicts
uv run bench smoke all --report          # ✓ recomputes every verdict from existing runs, launches nothing
uv run bench report c01                  # phase 5
uv run pytest                            # ✓ tests: the runner and collector end to end with a fake claude
```
