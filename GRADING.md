# Grading

> The grid for grading the four tasks. Nobody grades by hand (PLAN §10.32): each score comes from a formula, written by `bench grade` and marked `(auto)` (PLAN §10.28), or from the blind judge, written by `bench judge` and marked `(judge)` (PLAN §10.31). Both only fill blank cells, so a grade written by hand is never overwritten. `bench grade` also writes the raw figures in the *Raw figure* and *Notes* columns (PLAN §10.29); the judge never sees them. `bench grade` runs before `bench judge`: the T4 judge looks at the screenshots the grader takes, and a cell the grader set to 0 or N/A stays so.
> Agents never see this grid: the bench repository is invisible from the sandbox (ARCHITECTURE.md §7), and this file must never go into a fixture.
> Blank sheets: [GRADING-SHEET.md](GRADING-SHEET.md) for the code tasks (T1, T4), [GRADING-SHEET-T2.md](GRADING-SHEET-T2.md) and [GRADING-SHEET-T3.md](GRADING-SHEET-T3.md). `bench collect`, which `bench run` also runs at the end, drops the task's sheet as `grade.md` into the folder of every finished run, with the task, contestant, rep, time and cost filled in, and never overwrites one (`runs/` stays out of git).

## Rules

- Each task is graded on its own, with its own grid and **no weighting** between tasks.
- A formula on a log scale gives 10 at its best bound or below and 0 at its worst bound or above. The bounds are set on the spread of the c01 and c02 campaigns; the graders hold them next to the formula.
- The judge applies the criteria as they are written, two passes per run, and the grade kept is their mean.
- **Over the runs** (PLAN §10.33): a run's *task score* is the mean of its criteria, N/A left out, counted once every criterion has its grade. `bench report` gives, per task and contestant, the mean of each grade and of the task score with its 95 % confidence interval, the median, the standard deviation, the min and the max, and checks with Spearman's ρ that the ranking of the contestants and the judge's grades hold from one set of runs, or one pass, to the next.
- **When the build fails** (T1, T4), *Working* is 0 and every other score is N/A. **When the deliverable is missing** (T2, T3), every score is 0. Time and cost are still recorded: the model is considered not advanced enough to give reliable results on this exercise.

## Measured

Objective figures from the harness, not scored out of 10:

- **Time**: wall-clock duration of the run.
- **Cost**: API equivalent in $, plus electricity in € for Strata (`config/pricing.yaml`). Only the GPU is measured, so the electricity is an underestimate.

## The program

T1 and T4.

- **Working /10** (auto): what is attempted works, or is buggy. 10 × the share of the robustness checks passed.
  - Build: the exact command from the statement; for T1, no warning with `-Wall -Wextra`.
  - Robustness, T1: invalid input gives a single `error:` line and exit code 2, never a crash or a hang (empty file, duplicate ID, integer beyond 64 bits, missing or repeated header).
  - Robustness, T4: no crash and no error output under rapid clicks, clicks off the map, placement at the edge, restart while running, actions after the game is over. `bench grade` sends random clicks and keys to a sanitizer build (PLAN §10.30).
- **Following the statement /10** (auto): is what was asked there.
  - Exactness, T1: the output matches the specification to the letter, including on scenarios the agent never saw (ties, full car, direction reversal, times up to 10^15). 10 × the mean, over the hidden scenarios, of 0.6 × the passenger lines found, 0.3 × the similarity of the stop lines and 0.1 × the summary line.
  - Exactness, T4: the test mode against the oracle (money, population, status, tick by tick): placement rules, order of the tick steps, win and bankruptcy, without any research (PLAN §10.30). 10 × the mean, over the hidden scenarios, of the share of the lines equal to the oracle's.
  - Constraints, T4: SDL2 and libpng only, 24 × 16 map of 32 px cells at the top left, shortcuts `1` to `6`, space, `R` and Escape, right click to select a building, state always readable. The libraries are a check (`sdl2-libpng-only`), not a score.
- **Creativity /10** (judge; N/A for T1, whose rules leave nothing to polish): the level of polish, whether it goes in the intended direction or is the bare minimum. The judge plays the game on a virtual screen (PLAN §10.34), looks at the three screenshots `bench grade` takes in the test mode, and reads the code.
  - Looks: roads that join up, buildings composed of several tiles, recognisable and distinct, decorations (PLAN §10.24).
  - Usability: selected tool visible, footprint preview on hover, visible feedback on a refused placement, digits drawn by hand since there is no SDL_ttf, end of game obvious.
  - Research and upgrades: does the tree make sense, is the panel readable, does the balance hold, does each upgrade do exactly what it shows.
- **Performance /10** (auto):
  - T1: time on the 200,000-passenger scenario, on a log scale from 100 ms to 1 s, the statement's limit; 0 when the summary is wrong.
  - T4: delay from an input to the next frame, p95 over 10 s of random clicks and keys in the imposed build, on a log scale from 16 ms, one frame at 60 Hz, to 500 ms, one tick of the game. An input counts from the moment a steady input every 5 ms would have produced it, so the time it would have spent in the queue counts.
- **Resources /10** (auto):
  - T1: peak RAM of the same run, on a log scale from 25 MB to 250 MB; 0 when the summary is wrong.
  - T4: the mean of two grades of the idle game: CPU, 10 × (1 − the share of a core), since a core at 100 % while nothing happens is a bad sign; peak RAM, on a log scale from 16 MB to 256 MB. SDL's dummy driver has no vsync, so a game that relies on vsync to slow down spins a core and loses points.

## The code

- **Readability /10**: messy, or tidy and organised.
  - Early returns, correct blank lines.
  - Files and functions as short as possible: a 10-line file beats a 20-line one. Fine granularity and a single responsibility, because a narrow context is easier to grasp. No threshold in figures: judged from experience.
  - Names that speak for themselves: every comment counts as a naming failure, except in very specific cases such as a workaround.
- **Architecture /10**: spaghetti or pyramid, judged from experience. Declarations go in the headers and implementations in the `.cpp` files: the "config" (class definitions, enums, constants, tables of references) in the headers, the "runtime", what executes, in the `.cpp` files. A function body belongs in a header only for a template or `constexpr`. Hint for T4: is the simulation separate from the SDL rendering, testable without a window?
- **Factoring /10**: do patterns repeat, is the code generic or all ultra specific.
- **Cleanliness /10**:
  - everything correctly typed;
  - tables of references or pointers rather than long `if`/`else if` chains or `switch`;
  - enums rather than rows of macros;
  - no configuration, such as table-to-method mappings, in the `.cpp` files;
  - idiomatic C++20 (`enum class`, `optional`/`variant`, `string_view`, `span`, ranges, `constexpr`) rather than C with classes;
  - no forgotten debug scripts, output files, commented-out or dead code, or `TODO`;
  - a clean CMake: `target_compile_options`, pkg-config, no hardcoded path.
- **Safety /10**: RAII rather than manual `new`/`delete`, no undefined behaviour, no integer overflow (T1 times reach 10^15), const-correctness. A build with `-fsanitize=address,undefined` gives an objective signal.

## The summary

T2. *Delivered*: `ARCHITECTURE.md` is there and not empty.

- **Following the statement /10** (auto): 10 × the share of the four form checks passed: the seven sections in order, at most 1,200 words outside fenced blocks, a diagram in a fenced block, no other file touched.
- **Truth /10** (judge): each claim checked against the code; each false claim costs points, more when it would mislead a newcomer about how the code works. The paths and identifiers cited that are nowhere in the code are a figure, in the *Notes*.
- **Completeness /10** (judge): a newcomer can find their way in the code with the summary alone; each important fact left out costs points, more when it concerns a central part.

## The review

T3. *Delivered*: `review.json` can be read as JSON.

- **Bugs found /10** (auto): 10 × F1 over the seven seeded bugs. A comment finds a bug when it names its file, a line within 5 of it and words of its description. Every other comment is a false positive, even a real problem the key does not list.
- **Following the statement /10** (auto): 10 × the share of the three checks passed: `review.schema.json` followed, no file of the repository touched, every severity one of `low`, `medium`, `high` and `critical`.
- **Severity /10** (auto): over the bugs found, 1 when the severity is the key's, 0.5 one level off, 0 otherwise, times 10. N/A when no bug is found.
