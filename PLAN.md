# Coding-agent benchmark — plan

> Status: **phase 1 done, phase 2 done** (2026-10-25). Smoke runs only so far. The four tasks are written. `bench grade` grades T1, T2 and T3 automatically where a formula is objective; the rest stays the author's, by hand (§10.28).
> The choices and their rationale are summarized in §10.

## 1. Goal

Core question: **how much Anthropic spend does a local coding agent (Strata) save, and what does it cost in quality and time?** It is tested alone, then driven by Opus, against Haiku, Sonnet, Opus low and Opus normal.

Hypotheses to confirm or refute:

- **H1**: Strata alone holds up on reading tasks (architecture summary, review), but not on longer code production (simulation, game).
- **H2**: Opus extra → Strata reaches a quality close to Opus normal alone, at a much lower Anthropic cost, possibly below Opus low.
- **H3**: Opus extra → Haiku does as well as Opus extra → Strata, faster, for a negligible extra cost (Haiku 5.5 costs $0.10/$0.50 per MTok).
- **H4**: Sonnet normal remains the best value for money "without thinking about it".

Final deliverable: for each task, the deliverables of every contestant, compared by the author by hand, next to each run's time and Anthropic cost.

## 2. Strata survey (taken on 2026-10-25)

| Item | Value |
|---|---|
| Strata | Local engine, **Qwen3.8-Flash-Next** (MoE) in two variants: `coder-iq1_m` (200K context) and `qwen iq3_xxs` (131K) |
| Strata API | Anthropic-compatible on `http://127.0.0.1:8080`; `strata-agent` runs `claude -p --model strata` against it |
| Measured throughput (logs) | decode **~48–52 tok/s** · prefill 130–520 tok/s · effective prompt cache (~31K tokens reused) |
| Strata effort | reasoning off / low / medium / high (README) |
| Strata constraints | one model at a time · ~30 GB of RAM · the PC can freeze for 1–3 min while loading · `CLAUDE_CODE_MAX_OUTPUT_TOKENS=4096` in `strata-agent` |
| Current state | the Coder iq1_m is already serving (`/health` OK) |

## 3. Contestants

| ID | Name | Model(s) | Effort | Anthropic cost |
|---|---|---|---|---|
| `haiku` | Haiku normal | `claude-haiku-5-5` | `medium` | yes |
| `haiku-low` | Haiku low | `claude-haiku-5-5` | `low` | yes |
| `haiku-xhigh` | Haiku extra | `claude-haiku-5-5` | `xhigh` | yes |
| `sonnet` | Sonnet normal | `claude-sonnet-5-5` | `medium` | yes |
| `sonnet-low` | Sonnet low | `claude-sonnet-5-5` | `low` | yes |
| `sonnet-xhigh` | Sonnet extra | `claude-sonnet-5-5` | `xhigh` | yes |
| `strata` | Strata high | Strata Coder iq1_m (local) | high reasoning | **$0** |
| `opus-low` | Opus low | `claude-opus-5-5` | `low` | yes |
| `opus-haiku` | Opus extra → Haiku | Opus 5.5 orchestrates, Haiku 5.5 executes (native subagents) | `xhigh` / `medium` | yes (both) |
| `opus-strata` | Opus extra → Strata | Opus 5.5 orchestrates, Strata executes (Bash script, sequential calls) | `xhigh` / high | Opus only |
| `sonnet-haiku` | Sonnet extra → Haiku | Sonnet 5.5 orchestrates, Haiku 5.5 executes, same mechanism as `opus-haiku` | `xhigh` / `medium` | yes (both) |
| `sonnet-strata` | Sonnet extra → Strata | Sonnet 5.5 orchestrates, Strata executes, same mechanism as `opus-strata` | `xhigh` / high | Sonnet only |
| `opus-medium` | Opus normal | `claude-opus-5-5` | `medium` | yes |
| `opus-xhigh` | Opus extra | `claude-opus-5-5` | `xhigh` | yes |

Working definitions:

- "Opus extra" = effort `xhigh`. **Decided (§10.2).**
- "Strata high" = the Coder iq1_m with high reasoning. **Decided (§10.1)**: no iq3 control.
- "normal" = effort `medium`, for Haiku, Sonnet and Opus alone (and therefore for the Haiku workers), pinned explicitly in the config. **Decided (§10.3, §10.22).**

`opus-medium` replaces the `opus-xhigh` control (**decided, §10.22**). Opus alone therefore runs at `medium` while the orchestrators run at `xhigh`: comparing them mixes the effect of delegation with the effect of effort, and the analysis says so. `opus-xhigh` was added back on 2026-10-27, alongside `opus-medium`: it gives Opus alone at the orchestrators' effort.

All contestants go through **the same harness (Claude Code in headless mode)**, with the same tools and the same task statement: the only variable is the model. The two orchestrated configurations differ on two points, the orchestration preamble and the delegation mechanism, which is specific to each (§10.5).

## 4. Tasks

Common rules: **every task is in C++20** (§10.21), with no dependency beyond what is installed: the standard library, SQLite for T3, SDL2 and libpng for T4. No network access is needed in the sandbox. Deliverables go to fixed paths, and the timeout is the same for everyone (exceeding it counts as a give-up). The bench repository, T3's answer key included, is never visible from the workspace.

### T1 — Small simulation (30 min announced, 5 h timeout, §10.23)

- **Language: C++20, standard library only** (decided, §10.11).
  - Required build: `cmake -B build -G Ninja && cmake --build build` produces `build/sim`.
  - The standard library has no JSON, so input and output formats are **line-based text**, specified in the task statement.
  - Available tools: g++, CMake, Ninja, clang-tidy.
- **Subject: discrete-event elevator simulation** (decided, §10.11), with imposed **deterministic** rules (SCAN algorithm, capacities, travel times). The CLI is fixed: `build/sim --scenario x.txt --out trace.txt`.
- **Written on 2026-10-25** (`tasks/T1-simulation/`):
  - **Statement**: elevator group control. A cost function assigns each passenger to an elevator, with a load term and a penalty for calls behind a moving car. Each elevator runs SCAN, with capacity and doors. Ticks are processed in a fixed order and every tie is broken explicitly. Times go up to 10^15. Error handling is imposed: a line starting with `error:` on stderr and exit code 2. A public example sits in `fixture/examples/`.
  - **Checked on 2026-10-25**: an agent that saw only the statement implemented it blind, and its output matched an independent implementation on 1,010 scenarios out of 1,010: the statement is unambiguous in practice.

### T2 — Architecture summary (20 min announced, 5 h timeout, §10.23)

- **Fixture**: **`ComputerCraft`** (decided, §10.9), about 6.8 kLOC of Lua, a snapshot frozen at commit `aa65141` (2025-05-15), without `.idea/`. It is a private repository: the fixture is never committed here.
  - **Settled on 2026-10-25**: the fixture is `git archive aa65141` (64 files, 6,739 lines of Lua), rebuilt by `make_fixture.py` with `CC_REPO` pointing to the clone. The untracked folders `programs/specific/fission_mekanism/` and `programs/turtle/` are therefore left out: they are not part of the commit.
  - `README.md` (the project's intent) and `NORM.md` (coding rules) stay: neither describes the architecture.
- **Deliverable**: `ARCHITECTURE.md` with seven imposed sections (Purpose, Layout, Components, Entry points, Data flows, Diagram, Observations), at most 1,200 words outside code blocks, and a diagram in a code block.

### T3 — PR review (20 min announced, 5 h timeout, §10.23)

- **Fixture**: a **small C++ repository written for the occasion** (decided, §10.9 and §10.21), about 2 kLOC with tests, and a branch whose diff is about 600 lines. It contains **6 to 8 seeded bugs** of varying difficulty (off-by-one, null, race condition, injection, swallowed error, N+1) hidden among legitimate changes.
- **Deliverable**: `review.json` following an imposed schema (`file`, `line`, `severity`, `description`), without modifying the code.
- **Written on 2026-10-25** (`tasks/T3-pr-review/`):
  - **Shelfwise**, a lending service for a neighbourhood library: C++20 and SQLite, worker threads, CMake, 2,285 lines with 33 tests. Rewritten from Python to C++ on 2026-10-25 (§10.21). The base version (`build/base/`, hidden) is `main`. The fixture is the branch, plus `pr/PR.md`, `pr/changes.diff` (596 changed lines over 26 files, rebuilt by `build/build_pr.py`) and `review.schema.json`.
  - The PR "renewals, overdue reminders, paginated search" seeds **7 bugs** (`build/seeded_bugs.yaml`, the author's answer key), each triggered by a small program:
    - injection through `ORDER BY` (the order of the results leaks a bit of another table per query);
    - an empty optional e-mail dereferenced, which crashes the process from a worker thread;
    - data race and check-then-act on the set of reminded loans (duplicate reminders);
    - swallowed `MailError`, counted as sent;
    - negative fine for an early return, hidden by a loosened test;
    - N+1 in the overdue report;
    - off-by-one in the page count.
  - The PR's tests pass despite the bugs, and builds and tests run inside the sandbox. Under ASan and UBSan the tests find nothing, and TSan reports only the seeded race.

### T4 — Small game with provided tiles (60 min announced, 5 h timeout, §10.23 and §10.26)

- **Game**: a **mini city builder** in C++20 with SDL2 and libpng (§10.21), built with CMake, with research and building upgrades the agent designs itself (§10.26), and a test mode driven by a script (§10.30). Without a screen in the sandbox, the agent runs it with SDL's `dummy` video driver; checked on 2026-10-25 inside Firejail (window, renderer, a tile loaded with libpng).
- **Fixture**: `assets/` contains 151 individual 16×16 px tiles: the 132 tiles of the **Kenney Tiny City** pack (CC0) and 19 tiles from the **Kenney Tiny Town** pack (CC0) (grass, dirt, mushrooms, sprouts).
  - **Names**: each tile is renamed after **what it visually depicts** (`roof_brown_corner_top_left.png`, `wall_red_bricks.png`, `road_line_horizontal_top.png`, `tree_tall_green_top.png`…).
  - **No building name or in-game role** (no `house`, `shop`…), and **no assembly recipe**: the agent composes buildings from the pieces itself. Giving such names would have pre-chewed the work and biased the benchmark in favour of small models (§10.10).
  - **Done and approved (2026-10-25)**:
    - `tasks/T4-game/fixture/assets/` contains the 151 tiles and the licenses of both packs (`License_TinyCity.txt`, `License_TinyTown.txt`). The tiles are split into two folders:
      - `opaque/` (82 tiles): no transparent pixel, the tile covers the whole cell;
      - `transparent/` (69 tiles): at least one transparent pixel, the tile goes on top of something else.
      - The 19 Tiny Town tiles were named and sorted with the same rules. Their origin is verified pixel for pixel.
      - 14 almost-full tiles (rounded roof corners, white panel, 2 to 6 transparent pixels) are filed under `transparent/` by the strict rule, a choice that was approved.
    - Four groups of tiles are the same image under several names.
  - **Terrain**: Tiny City has no grass or natural ground. The 19 Tiny Town tiles fill that gap: grass in four variants and a complete dirt area (centre, edges, outer and inner corners). The available terrain therefore covers asphalt, pavement, grass and dirt.
- **Specification** (written on 2026-10-25, `prompt.md`):
  - a 24 × 16 map of 32 px cells, five buildings placed with the mouse: road 1×1, house 2×2, shop 2×2, factory 3×2, park 2×2, each with a cost and an upkeep. The agent chooses how to depict each building with the tiles;
  - tools, play/pause and restart by button or key (`1` to `6`, space, `R`), the stats in the window or its title bar; the game starts paused and runs a tick every 500 ms;
  - a tick in eight ordered, integer steps. Residents move one step toward a capacity: 8, plus 4 with a park within 3, minus 3 per factory within 2. Then jobs and wages, shop customers within 4, and taxes every 10 ticks. Connection means a road orthogonally adjacent; distance is Chebyshev between footprints;
  - win at 150 residents, bankruptcy below 0. A scripted player wins around tick 90, and two factories without houses go bankrupt in about twenty ticks.

## 5. What is compared

| Criterion | How |
|---|---|
| **Cost** | measured: $ = Σ tokens × price (input, output, cache write and cache read) |
| **Time** | measured: wall-clock time from launch to final result |
| **Result quality**, **code quality**, **instruction following** | `bench grade` where a formula is objective (§10.28), the author by hand for the rest |

Scores out of 10 only where a fixed formula is objective (T1 exactness and robustness, T3 F1); raw figures elsewhere. The author keeps the final grade (§10.28).

## 6. Protocol

- **Repetitions**: N = 3 per (contestant, task) pair. The median and spread are reported.
- **Order**: seeded random draw. Models alternate so that the prompt cache is uniformly cold. Strata runs are grouped in blocks, for a single model load, and are **exclusive**: no other run in parallel, so as not to skew timings.
- **Pinned version**: the same Claude Code version everywhere, auto-update off, dated prices in `pricing.yaml`.
- **Isolation**: blank Claude Code configuration (no global `CLAUDE.md`, no plugins, MCP, skills or memory) and a workspace **outside the bench repository**. Permissions are open only inside a **Firejail** sandbox (§10.8). See ARCHITECTURE.md §7.
- **Diagnostics collected**: turns, tool calls, tool errors, give-ups, tokens per model, and Strata GPU energy (indicative, §10.13).

## 7. Phases

| # | Phase | Content | Exit criterion | Estimated cost* |
|---|---|---|---|---|
| 0 | Scoping | this brainstorm, settle §10 | decisions written here | $0 |
| 1 | Skeleton + smoke tests | skeleton, runner and collector **written on 2026-10-25**, tested with a fake `claude`, sandbox verified. "hello" smoke run passed on all 7 contestants on 2026-10-25, with costs matching Claude Code. `bench smoke` done on 2026-10-25: effort, blank config and sandbox tightness PASS. Subagent effort pinned to `medium` in its definition on 2026-10-26, Strata output cap comparison not run (§10.15) | telemetry OK everywhere (see ARCHITECTURE.md §9) | < $5 |
| 2 | Tasks | the 4 statements and fixtures. **Done on 2026-10-25** | statements and fixtures ready | $0 |
| 3 | Pilot | 1 run × 7 contestants × 4 tasks = 28 runs | timeouts calibrated, real budget known | ~$35 |
| 4 | Campaign | N = 3 → 84 runs | every run done | ~$120–180 |
| 5 | Analysis | the author's comparison, time and cost per contestant, verdict per hypothesis | written report | included |

\* Costs in **API equivalent**, order of magnitude only. They assume about $1 to $2 per Opus run, about $1 for Sonnet, a few cents for Haiku and $0 for Strata. The pilot will give the real figures. **Decided (§10.6)**: everything goes through the subscription, so these amounts are quota consumed, not real dollars.

Machine time: at ~50 tok/s, a Strata run can last up to the 5 h timeout (§10.23). In the worst case, the 24 Strata runs of the campaign take **5 machine days** if runs are serialized.

## 8. Out of scope

- API network latency as distinct from thinking time: only total duration counts.
- Harnesses other than an identical Claude Code for everyone (Aider, OpenHands…).
- Large codebases (over 50 kLOC) and multi-hour tasks.

## 9. Risks and biases

| Risk | Effect | Mitigation |
|---|---|---|
| Very aggressive IQ1_M quantization | Strata gives up often | timeout and give-up are part of the result. No iq3 control (§10.1), so the effect of compression cannot be isolated |
| Output capped on the Strata side | large files written in several pieces, or failed. More sensitive in C++ (T1), which is verbose | it is a Claude Code client setting, not a server limit. Raised from 4,096 to 32,768 after the pilot (§10.25), then to 65,536 (§10.27); truncations are counted in every run |
| Sequential Strata calls, parallel Haiku subagents | `opus-strata` slower than `opus-haiku` | deliberate choice (§10.5): this is real-world usage, documented in the report |
| Different delegation mechanisms | the `opus-haiku` ↔ `opus-strata` comparison mixes model and mechanism | stated plainly in the analysis. Opus alone (`opus-medium`) is not at the orchestrators' effort (§10.22) |
| Grader bias and fatigue | the author knows the contestants, and about 112 deliverables are graded by hand | the author's call: for instance, grading before looking at the metrics, and spreading the sessions over the pilot and the campaign |
| Contamination | overly well-known tasks (Snake, Game of Life) | original task statements with specific constraints |
| Building buildings from tiles (T4) | models that look at the images (Claude's native vision) compose better, while Strata's vision runs on the CPU and is slow | visual names make vision optional. The remaining gap is documented in the report |
| Effort not passed to Strata | "Strata high" actually runs without reasoning | checked in phase 1 (low/high comparison) |
| Warm or cold prompt cache | incomparable costs | models alternate, cache reads and writes reported separately |
| Answer-key leak | the agent reads T3's seeded bugs | workspace outside the repository, and a Firejail whitelist that hides the bench repository |
| Network not filtered by domain | an agent could reach other sites | the tasks do not need it, access shows up in transcripts, accepted limitation |
| PC frozen while Strata loads | skewed timings | loading **before** the clock starts, mandatory health check |
| Subscription limit reached mid-run | interrupted run, skewed timing | quota error detected → run marked `quota` (neither success nor give-up) and rerun later |

## 10. Brainstorm decisions (2026-10-25)

1. **"Strata high"**: the Coder iq1_m with high reasoning, or the qwen iq3_xxs variant? → ✅ **Coder iq1_m, high reasoning, no iq3 control.**
2. **"Opus extra"**: `xhigh` or `max`? → ✅ **`xhigh`.**
3. **"normal"**: which effort for Haiku and Sonnet? → ✅ **`medium` for both**, pinned in the config.
4. **`opus-xhigh` control**: add it? → ✅ **Yes, as a full contestant** (3 repetitions). **Reversed by §10.22.**
5. **Orchestration**: which delegation mechanism? → ✅ **Native subagents for Haiku, a Bash script with sequential calls for Strata.** The comparison between the two orchestrated configurations therefore mixes model and mechanism, and the analysis will say so.
6. **Billing**: API key or subscription? → ✅ **Subscription** (the tasks stay modest). Cost is computed in API equivalent from the tokens.
7. **Campaign budget cap**? → ✅ **No cost cap.** The task timeout bounds each run, and runs costing more than 3 times their contestant's median are flagged.
8. **Sandbox**: which one? → ✅ **Firejail**, already installed, with a minimal home whitelist. See ARCHITECTURE.md §7.
9. **Repository for T2 and T3**: one of the author's projects or an open-source one frozen at a commit?
   - T2 → ✅ **`ComputerCraft`**, commit `aa65141`.
   - T3 → ✅ **small repository written for the occasion** (tests, trapped PR), in C++ since §10.21.
10. **T4**: game genre and graphics?
    - Genre → ✅ **mini city builder**, with deterministic rules.
    - Tiles → ✅ **Kenney Tiny City** and 19 terrain tiles from **Kenney Tiny Town** (CC0), 151 tiles in total, **renamed after their visual content**. No building name and no assembly recipe: the agent composes on its own. Giving roles (`house`, `shop`…) would have biased the benchmark in favour of small models.
11. **Imposed language** for T1? → ✅ **C++20, standard library only**, CMake/Ninja build and text formats. Subject → ✅ **discrete-event elevators**.
12. **Human grading**: how much does the author take on? → ✅ **All of it**, by their own criteria (§10.19): validating the T4 tile names (done on 2026-10-25), then comparing by hand the 112 deliverables of the pilot and the campaign (7 contestants × 4 tasks × 4 runs), T4 playtest included.
13. **Strata energy**: what to do with power consumption? → ✅ **GPU only** (`nvidia-smi`), converted to € and shown alongside, as an indication, outside the cost score. The CPU is not measured (RAPL is only readable as root), so the figure underestimates real consumption.
14. **Weighted overall score**? → ✅ **No**, and no score at all since the automatic grading was removed (§10.20).
15. **Strata output cap** (`CLAUDE_CODE_MAX_OUTPUT_TOKENS`)? → ✅ **4,096, the value Strata tested.** **Reversed by §10.25.**
    - The 4,096 versus 16,384 comparison (smoke test #5) was not run: up to half an hour of machine time for a point the pilot will show anyway.
    - Every run counts its truncated responses and its `length` finishes in the Strata server log. If they show up in the pilot, the cap is revisited.
    - The value applies to `strata` and to the `opus-strata` workers alike.
16. **T2 fixture and ground truth** (phase 2) → ✅ **`git archive aa65141`**: the untracked folders are left out and `README.md` and `NORM.md` stay.
17. **Driving the browser for T4** (phase 2) → removed with the automatic grading (§10.20).
18. **Behaviour of the graders** (phase 2) → removed with the automatic grading (§10.20).
19. **Who judges** → ✅ **the author, by hand, by their own criteria, for everything** (2026-10-25): "on ne peut pas être juge et partie". Every Claude model is a contestant, so no LLM judges, whatever the model. No rubric is imposed: the author's own criteria apply. **Partly reversed by §10.31**: a blind Opus grades the subjective criteria, the author keeps the final grade.
20. **Automatic grading** → ✅ **removed** (2026-10-25). **Partly reversed by §10.28.** The author only wants to compare by hand what the models produce on the four tasks: the graders, the reference and sabotaged solutions, the scores out of 10 and the T2 ground-truth sheet are gone. The harness runs the models and measures time, tokens and cost; T3's seeded bugs stay as the author's answer key.
21. **Language of the tasks** → ✅ **C++ everywhere** (2026-10-25). T1 already was. T3's Shelfwise is rewritten in C++20 with SQLite, with the same seven bugs. T4 becomes a C++20 game with SDL2 and libpng, both already installed. T2 keeps ComputerCraft (Lua): its deliverable is a summary, not code. The harness stays in Python.
22. **Opus alone** → ✅ **`opus-medium`** (2026-10-26). Opus alone runs at `medium`, "normal" like Haiku and Sonnet, and replaces the `opus-xhigh` control: still 7 contestants. The price: the orchestrators run Opus at `xhigh`, so comparing them with Opus alone no longer separates the effect of delegation from the effect of effort.
23. **Timeouts** → ✅ **5 h for every task** (2026-10-26). In the pilot, Strata timed out on T1 after 30 min at ~50 tok/s, and its time must be measured even when it is slow. The statements still announce 20, 30 or 45 min, so every agent works under the same pressure: the 5 h are only a safety net.
24. **T4 decorations** → ✅ **kept, left to the agent** (2026-10-26). The statement says only that they are purely visual, cost 10 and occupy their cells. Which ones exist, how they look and how the player places them are the agent's choice: the only open room for creativity in the benchmark.
25. **Strata output cap** → ✅ **32,768** (2026-10-26). In the pilot, Strata wrote nothing to T3's `review.json`. The server keeps 3,072 of the 4,096 tokens for thinking: it cut the thinking at that budget, and the model ended its turn with "Here's my final answer." without writing the file. The thinking budget grows with the cap. First raised to 16,384, then to 32,768 the same day: the Anthropic contestants get 128,000, Claude Code's default, and 32,768 still leaves about 170k of Strata's 200k context for the input. Also applies to the Strata workers. **Raised by §10.27.**
26. **T4 research and upgrades** → ✅ **fixed frame, free content** (2026-10-26). A right click selects a building, and a panel offers its upgrades, unlocked by research that costs money and ticks. Which upgrades exist and what they do are the agent's choice, effects included; each upgrade must show what it does and do exactly that. As long as no research is started, the base rules stay exact, so the reference game can still be checked by hand. The announced time goes from 45 to 60 min.
27. **Strata output cap, again** → ✅ **65,536** (2026-10-27). With 32,768, the server cuts the thinking at 24,576 tokens so that the answer keeps a quarter of the cap. In c01, 3 of 500 Strata requests reached it: one real line of reasoning on T1, cut just before its end, and two loops on T4 that the cut stopped. The cap is a maximum, so a request that finishes thinking earlier is not affected. At 65,536 the thinking budget is 49,152: the author prefers never cutting a line of reasoning, even if a loop then runs longer. About 139k of Strata's 200k context remain for the input. Also applies to the Strata workers.
28. **Automatic grading, back** → ✅ **`bench grade`** (2026-10-30). The author wants criteria applied more automatically. A grader per task runs on each finished run and writes `auto.json`, plus the objective figures in `grade.md` where the author left the cell blank. T1: the oracle of §10.20 is restored (10 hidden scenarios, 13 invalid inputs, command-line errors, sanitizers, 200,000 passengers, peak RAM). T3: the comments are matched with `seeded_bugs.yaml`, score 10 × F1, the unmatched comments listed for the author. T2: form, and every path or identifier cited checked against the fixture. Decided the same day, still to build: C++ code metrics, to define with the author; a test interface in the T4 statement, so that its rules can be checked (T4 then runs again for every contestant), and a check of how the tiles are used; a blind LLM judge for the subjective criteria (readability, architecture, truth of the T2 summary): Opus at `xhigh`, in Firejail, that never learns which contestant it grades. This reverses §10.19 for those criteria. **The code metrics are §10.29, the T4 test interface §10.30, the judge §10.31.**
29. **C++ code metrics** → ✅ **raw figures, by criterion of GRADING.md** (2026-10-30), defined with the author, for T1 and T4. Readability: function and file length, cognitive complexity, comments per 1,000 lines. Architecture: declarations and "config" (class definitions, enums, constants and tables) in the headers, "runtime" in the `.cpp` files, so a function body in a header counts unless it is a template or `constexpr`, and a class, enum or constant defined in a `.cpp` counts too; includes per file and include cycles; for T4, the share of the code that does not include SDL. Factoring: duplicated code (blocks of 75 tokens, names and literals ignored), `else if` chains of 3 branches or more, `switch`. Cleanliness: `TODO`, commented-out code, leftover files, `#define`, plain enums, C++20 idioms, `else` after `return`, a clean CMake. Safety: `new`/`delete`/`malloc`, strict warnings (`-Wconversion -Wsign-conversion -Wshadow -Wpedantic`), clang-tidy `bugprone-*`, `performance-*` and `misc-const-correctness`, sanitizers. Functions are found with lizard. Counters come with their rate per 1,000 lines. No score: the figures inform the author, and the LLM judge never sees them, so that the measure and the judgement stay independent.
30. **T4 test mode** → ✅ **in the statement** (2026-10-30), contract approved by the author. `build/city --script <file> --out <file>` runs `place`, `bulldoze`, `step`, `reset` and `screenshot` commands with the same code as the mouse and the keyboard, and writes `<result> <tick> <money> <population> <status>` after each. Research and upgrades stay out of it, so they are judged, not checked. The grader runs 13 hidden scenarios against the Python oracle of §10.20, restored as is since the rules have not changed, plus a restart in the middle of a game. Three screenshots (every road shape, each type of building, connected or not) are matched cell by cell, pixel for pixel, against the provided tiles: share of the cells drawn with tiles, buildings made of several tiles, types that do not share their tiles, roads whose straight parts, corners and crossings look different and whose identical layouts look alike. The real game also gets 20 s of random clicks and keys, twice, in a sanitizer build, through a library preloaded before SDL; then its CPU and RAM while idle (indicative: the dummy driver has no vsync). T4 must run again for every contestant: the c01 and c02 games have no test mode, so they keep a statement score of 0 and are judged on the random input alone.
31. **Blind judge** → ✅ **`bench judge`** (2026-10-30), scope chosen by the author: Opus at `xhigh` grades the five code criteria of GRADING.md for T1 and T4 (the "The code" section is sent as is), and the truth and completeness of the T2 summary, with the false claims and the missing facts listed. Blind: a copy of the final workspace under a random name, without the transcript, the metrics or any grade, every contestant or model name and the run's own workspace path replaced by `[redacted]`, in the agents' sandbox, so the bench repository stays out of its sight. Two passes per run, in separate sessions and a seeded random order, every first pass before the second ones: the grade kept is their mean, and the spread shows how steady the judge is. The grades go to `judge.json` and, for T1 and T4, to the *Score* column of `grade.md`, marked `(judge)`, never over the author's own cells. A known bias remains: blindness hides the contestant, not a possible taste of Opus for its own style. About $0.5 to $2 per pass in API equivalent, on the subscription.
