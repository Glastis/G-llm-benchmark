"""T4 grader (PLAN §10.28): the test mode of the statement against the Python oracle of the rules, the
screenshots of the map against the provided tiles, random clicks and keys in the real game, and the
code metrics (§10.29). The criteria are those of GRADING.md.

Everything that executes agent code happens in a single `sandbox_exec` call, with SDL's dummy video
driver and a timeout per program. The expected lines never enter the sandbox.

Scores (0 if the build fails):
- statement: 10 × the mean, over the hidden scenarios, of the share of output lines equal to the
  oracle's, at the same position. Research and upgrades are out of the test mode: not checked here.
- working: 10 × the share of the robustness checks passed: each test-mode run ends by itself without
  a crash, each random-input run without a crash or a sanitizer report and quits on SDL_QUIT, and
  nothing is ever printed to stderr. A game without a test mode (made before §10.30) is judged on
  the random input alone; its statement score is 0, and the `test-mode` check says why.
Tiles, idle CPU and RAM stay figures and checks.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import showcase  # noqa: E402
from hidden import hidden_scenarios  # noqa: E402
from scenarios import expected, script  # noqa: E402
from tiles import Shot, Tiles, checks as tile_checks  # noqa: E402

from bench import cpp_metrics  # noqa: E402
from bench.grade import MEASURE, created_files  # noqa: E402
from bench.runner import sandbox_exec  # noqa: E402

FIXTURE = HERE.parent / "fixture"
FUZZ_SEEDS = (1, 2)
FUZZ_MS, IDLE_MS = 20000, 5000
FORBIDDEN_INCLUDES = re.compile(r'^\s*#\s*include\s*[<"](SDL2?/)?(SDL_image|SDL_ttf|SDL_mixer|SDL_net)\.h[>"]', re.M)
SANITIZER = re.compile(r"Sanitizer|runtime error")


def _script() -> str:
    """The shell script run in the sandbox. Its working directory is the agent's workspace."""
    asan = cpp_metrics.compiler("asan", "-fsanitize=address,undefined -fno-omit-frame-pointer")
    fuzz_env = f"ASAN_OPTIONS=verify_asan_link_order=0:detect_leaks=0:hard_rss_limit_mb=2048 LD_PRELOAD=$PWD/$G/fuzz.so"
    return "\n".join([
        "G=.grade",
        "export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy",
        "mkdir -p $G/out $G/shots",
        # 1. the imposed build, a sanitizer build, then strict warnings and clang-tidy
        "{ cmake -B build -G Ninja && cmake --build build; } > $G/build.log 2>&1; echo $? > $G/build.rc",
        asan[0],
        f"{{ cmake -B $G/asan -G Ninja -DCMAKE_BUILD_TYPE=Debug {asan[1]} && cmake --build $G/asan; }} > $G/asan.log 2>&1",
        *cpp_metrics.sandbox_script(),
        # 2. the test mode: a probe, then the hidden scenarios and the screenshots
        "timeout 10 build/city --script $G/probe.txt --out $G/out/probe.out > /dev/null 2> $G/out/probe.err;"
        " echo $? > $G/out/probe.rc",
        "if [ -s $G/out/probe.out ]; then",
        "  for f in $G/scenarios/*.txt; do n=$(basename $f .txt);"
        "    timeout 30 build/city --script $f --out $G/out/$n.out > /dev/null 2> $G/out/$n.err; echo $? > $G/out/$n.rc;"
        "  done",
        "fi",
        # 3. random input in the sanitizer build, then the idle game in the imposed one
        "gcc -shared -fPIC -O1 $G/fuzz.c -o $G/fuzz.so $(pkg-config --cflags --libs sdl2) -ldl > $G/fuzz-build.log 2>&1",
        f"for s in {' '.join(map(str, FUZZ_SEEDS))}; do",
        f"  env {fuzz_env} FUZZ_SEED=$s FUZZ_MS={FUZZ_MS} timeout {FUZZ_MS // 1000 + 30} $G/asan/city"
        "   > /dev/null 2> $G/out/fuzz$s.err; echo $? > $G/out/fuzz$s.rc;",
        "done",
        f"python3 $G/measure.py {IDLE_MS // 1000 + 20} $G/out/idle.err env LD_PRELOAD=$PWD/$G/fuzz.so FUZZ_IDLE=1"
        f" FUZZ_MS={IDLE_MS} build/city > $G/out/idle.result",
    ]) + "\n"


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _rc(path: Path) -> int | None:
    text = _read(path).strip()
    return int(text) if text.lstrip("-").isdigit() else None


def _stage_inputs(g: Path, scenarios: dict[str, list[list]], shots: list[list]) -> None:
    if g.exists():
        shutil.rmtree(g)
    (g / "scenarios").mkdir(parents=True)
    for name, actions in scenarios.items():
        (g / "scenarios" / f"{name}.txt").write_text(script(actions))
    (g / "scenarios" / "showcase.txt").write_text(script(shots))
    (g / "probe.txt").write_text("step 1\n")
    (g / "fuzz.c").write_text((HERE / "fuzz.c").read_text())
    (g / "measure.py").write_text(MEASURE)


def match(want: list[str], got: list[str]) -> float:
    """The share of the expected lines found at the same position."""
    return sum(a == b for a, b in zip(want, got)) / len(want) if want else 1.0


def _tiles(g: Path, shots: list[list], starts: dict[str, int]) -> tuple[dict, dict]:
    lines = _read(g / "out" / "showcase.out").splitlines()
    found = {name: g / "shots" / f"{name}.png" for name in showcase.SCENES}
    try:
        tiles = Tiles(FIXTURE / "assets")
        images = {name: Shot(path, tiles) for name, path in found.items() if path.is_file()}
    except (ValueError, OSError) as e:
        return {"tiles-used": False}, {"error": str(e)}
    if len(images) < len(found):
        return {"tiles-used": False}, {"error": f"screenshots missing: {sorted(set(found) - set(images))}"}
    buildings, roads = showcase.placed(shots, starts, lines)
    return tile_checks(images, buildings, roads)


def _sheet(built: bool, scores: dict, figures: dict, tile_ok: dict) -> dict:
    """The cells of grade.md. When the build fails, Working is 0 and the rest N/A (GRADING.md)."""
    if not built:
        return {"Builds with the exact command": ["no"], "Working": ["0"]}
    notes = cpp_metrics.notes(figures["code"])
    t = figures["tiles"]
    tile_note = (f"tiles on {round(100 * t['tile_share'])} % of the cells; " if t.get("tile_share") is not None else "") \
        + ", ".join(f"{k} {'yes' if v else 'no'}" for k, v in tile_ok.items())
    idle = figures["idle"]
    return {
        "Builds with the exact command": ["yes"],
        "Working": [f"{scores['working']:g}"],
        "Following the statement": [f"{scores['statement']:g}", None,
                                    f"rules: {figures['exact_scenarios']} hidden scenarios exact, research not checked"
                                    if figures["tiles"].get("error") != "no test mode" else "no test mode"],
        "Creativity (N/A for T1)": [None, None, tile_note],
        "Resources": [None, f"idle CPU {idle['cpu_percent']} %, {idle['peak_ram_mb']} MB peak RAM"],
        **{row: [None, note] for row, note in notes.items()},
        "Safety": [None, f"random input under sanitizers clean on {figures['fuzz_clean']}; {notes['Safety']}"],
    }


def grade(tree: Path) -> dict:
    g = tree / ".grade"
    scenarios = hidden_scenarios()
    shots, starts = showcase.script()
    _stage_inputs(g, scenarios, shots)
    try:
        run = sandbox_exec(_script(), tree, timeout_s=3600)
        sandbox_log = (run.stdout + run.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        sandbox_log = "grading timed out"

    built = _rc(g / "build.rc") == 0 and (tree / "build" / "city").is_file()
    test_mode = built and bool(_read(g / "out" / "probe.out").strip())
    results, ended, stderr = {}, [], []
    for name, actions in {**scenarios, "showcase": shots}.items() if test_mode else ():
        got = _read(g / "out" / f"{name}.out").splitlines()
        stderr.append(_read(g / "out" / f"{name}.err"))
        ended.append(_rc(g / "out" / f"{name}.rc") == 0)
        if name != "showcase":
            want = expected(actions)
            results[name] = {"match": round(match(want, got), 4), "exact": want == got, "rc": _rc(g / "out" / f"{name}.rc")}
    fuzz = {}
    for seed in FUZZ_SEEDS:
        err, rc = _read(g / "out" / f"fuzz{seed}.err"), _rc(g / "out" / f"fuzz{seed}.rc")
        stderr.append(err)
        fuzz[seed] = {"rc": rc, "clean": rc == 0 and not SANITIZER.search(err), "quits": rc not in (None, 124),
                      "stderr": err[:300]}
    idle_rc, idle_ms, idle_kib, idle_cpu = (_read(g / "out" / "idle.result").split() + ["?"] * 4)[:4]
    silent = built and not any(e.strip() for e in stderr)
    robustness = ended + [f["clean"] for f in fuzz.values()] + [f["quits"] for f in fuzz.values()] + [silent]
    tile_ok, tile_figures = _tiles(g, shots, starts) if test_mode else ({"tiles-used": False}, {"error": "no test mode"})

    scores = {"statement": round(10 * sum(r["match"] for r in results.values()) / len(scenarios), 1) if test_mode else 0.0,
              "working": round(10 * sum(robustness) / len(robustness), 1) if built else 0.0}
    figures = {
        "exact_scenarios": f"{sum(r['exact'] for r in results.values())}/{len(scenarios)}",
        "fuzz_clean": f"{sum(f['clean'] for f in fuzz.values())}/{len(fuzz)}",
        "idle": {"cpu_percent": round(100 * int(idle_cpu) / int(idle_ms)) if idle_ms.isdigit() and idle_cpu.isdigit() and int(idle_ms) else None,
                 "peak_ram_mb": round(int(idle_kib) / 1024, 1) if idle_kib.isdigit() else None, "rc": idle_rc},
        "tiles": tile_figures,
        "code": cpp_metrics.measure(tree, g, created_files(tree, FIXTURE)),
    }
    sources = cpp_metrics.sources(tree)
    return {
        "scores": scores,
        "checks": {
            "builds": built,
            "sdl2-libpng-only": not any(FORBIDDEN_INCLUDES.search(_read(s)) for s in sources),
            "test-mode": test_mode,
            "silent": silent,
            **tile_ok,
        },
        "figures": figures,
        "sheet": _sheet(built, scores, figures, tile_ok),
        "attachments": [f".grade/shots/{name}.png" for name in showcase.SCENES],
        "details": {
            "scenarios": results,
            "fuzz": fuzz,
            "stderr": [e[:300] for e in stderr if e.strip()][:5],
            "source_files": [s.relative_to(tree).as_posix() for s in sources],
            "build_log": _read(g / "build.log")[-2000:],
            "sandbox_log": sandbox_log,
        },
    }


if __name__ == "__main__":
    print(json.dumps(grade(Path(sys.argv[1]).resolve()), indent=2))
