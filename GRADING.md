# Grading

> The author's grid for grading the code tasks (T1 and T4). `bench grade` fills in what a formula can measure, marked `(auto)`, and never overwrites the author's own cells (PLAN §10.28); the rest is graded by hand. For the code criteria it only writes raw figures in the *Notes* column (PLAN §10.29), never a score. `bench judge` writes the blind judge's grades for the code criteria in the *Score* column, marked `(judge)`, on the same terms (PLAN §10.31).
> Agents never see this grid: the bench repository is invisible from the sandbox (ARCHITECTURE.md §7), and this file must never go into a fixture.
> Blank sheet: [GRADING-SHEET.md](GRADING-SHEET.md). `bench collect`, which `bench run` also runs at the end, drops it as `grade.md` into the folder of every finished T1 and T4 run, with the task, contestant, rep, time and cost filled in, and never overwrites one (`runs/` stays out of git).

## Rules

- Each code task is graded on its own, with the same grid and **no weighting** between tasks.
- Scores out of 10 are the author's judgement. Some points cannot be reduced to rules: architecture and readability are judged from experience.
- **When the build fails**, *Working* is 0 and every other score is N/A. Time and cost are still recorded: the model is considered not advanced enough to give reliable results on this exercise.

## Measured

Objective figures from the harness, not scored out of 10:

- **Time**: wall-clock duration of the run.
- **Cost**: API equivalent in $, plus electricity in € for Strata (`config/pricing.yaml`). Only the GPU is measured, so the electricity is an underestimate.

## The program

- **Working /10**: what is attempted works, or is buggy.
  - Build: the exact command from the statement; for T1, no warning with `-Wall -Wextra`.
  - Robustness, T1: invalid input gives a single `error:` line and exit code 2, never a crash or a hang (empty file, duplicate ID, integer beyond 64 bits, missing or repeated header).
  - Robustness, T4: no crash and no error output under rapid clicks, clicks off the map, placement at the edge, restart while running, actions after the game is over. `bench grade` sends random clicks and keys to a sanitizer build (PLAN §10.30).
- **Following the statement /10**: is what was asked there.
  - Exactness, T1: the output matches the specification to the letter, including on scenarios the agent never saw (ties, full car, direction reversal, times up to 10^15).
  - Exactness, T4: the test mode against the oracle (money, population, status, tick by tick): placement rules, order of the tick steps, win and bankruptcy, without any research (PLAN §10.30). Each upgrade does exactly what it shows, which is checked by hand.
  - Constraints, T4: SDL2 and libpng only, 24 × 16 map of 32 px cells at the top left, shortcuts `1` to `6`, space, `R` and Escape, right click to select a building, state always readable.
- **Creativity /10** (N/A for T1, whose rules leave nothing to polish): the level of polish, whether it goes in the intended direction or is the bare minimum.
  - Looks: roads that join up, buildings composed of several tiles, recognisable and distinct, decorations (PLAN §10.24).
  - Usability: selected tool visible, footprint preview on hover, visible feedback on a refused placement, digits drawn by hand since there is no SDL_ttf, end of game obvious.
  - Research and upgrades: does the tree make sense, is the panel readable, does the balance hold.
- **Performance /10**: raw figures recorded, converted to a score once the spread is known.
  - T1: time on the 200,000-passenger scenario (the statement requires under one second).
  - T4: smoothness and responsiveness to clicks. FPS is only a hint: the game ticks every 500 ms and rendering is often tied to vsync.
- **Resources /10**: peak RAM (`/usr/bin/time -v`); for T4, also the CPU while idle, since a core at 100 % while nothing happens is a bad sign. Converted the same way.

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
