"""T1 grader: builds the agent's project and runs it in the sandbox, then compares its traces with the
oracle's (PLAN §4 T1, §10.28). The criteria are those of GRADING.md.

Everything that executes agent code happens in a single `sandbox_exec` call, with a time and memory
limit per program. The expected traces never enter the sandbox.

Scores (0 if the build fails):
- statement: 10 × the mean, over the hidden scenarios, of 0.6 × passenger lines found + 0.3 ×
  similarity of the stop lines + 0.1 × summary line;
- working: 10 × the share of the robustness checks passed: each invalid input and each command-line
  error gives a single `error:` line and exit code 2, each hidden scenario and the performance one
  ends without a crash or a timeout.
Performance (time on 200,000 passengers) and resources (peak RAM) stay raw figures.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from scenarios import perf_scenario  # noqa: E402

from bench import cpp_metrics  # noqa: E402
from bench.grade import MEASURE, created_files  # noqa: E402
from bench.runner import sandbox_exec  # noqa: E402

SCENARIOS = sorted((HERE / "scenarios").glob("*.txt"))
INVALID = sorted((HERE / "invalid").glob("*.txt"))
PERF_SUMMARY = (HERE / "expected" / "perf.summary").read_text().strip()
FIXTURE = HERE.parent / "fixture"
MEMORY_KB = 4_000_000          # address-space limit of the agent's program (no ASan)
ASAN_RSS_MB = 2048
PERF_LIMIT_MS = 1000           # the statement's "under one second"
SANITIZERS = "-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer"
CLI_ERRORS = {                 # command-line errors: arguments after build/sim
    "no-arguments": "",
    "missing-out": "--scenario examples/basic.txt",
    "unknown-flag": "--scenario examples/basic.txt --out .grade/cli.out --verbose",
    "missing-file": "--scenario .grade/does-not-exist.txt --out .grade/cli.out",
}

STOP_LINE = re.compile(r"\d+ \d+ \d+ (up|down) out=(-|\d+(,\d+)*) in=(-|\d+(,\d+)*)")
PASSENGER_LINE = re.compile(r"passenger \d+ elevator \d+ wait \d+ ride \d+")
SUMMARY_LINE = re.compile(r"summary passengers \d+ makespan \d+ avg_wait \d+\.\d\d max_wait \d+ avg_ride \d+\.\d\d")

# Standard headers allowed by "standard library only": C++20 plus the C compatibility headers.
STD_HEADERS = set("""
algorithm any array atomic barrier bit bitset charconv chrono codecvt compare complex concepts
condition_variable coroutine deque exception execution expected filesystem format forward_list
fstream functional future initializer_list iomanip ios iosfwd iostream istream iterator latch
limits list locale map memory memory_resource mutex new numbers numeric optional ostream queue
random ranges ratio regex scoped_allocator semaphore set shared_mutex source_location span
sstream stack stdexcept stop_token streambuf string string_view syncstream system_error thread
tuple type_traits typeindex typeinfo unordered_map unordered_set utility valarray variant vector
version cassert cctype cerrno cfenv cfloat cinttypes climits clocale cmath csetjmp csignal
cstdarg cstddef cstdint cstdio cstdlib cstring ctime cuchar cwchar cwctype
assert.h ctype.h errno.h float.h inttypes.h limits.h math.h stddef.h stdint.h stdio.h stdlib.h
string.h time.h
""".split())
FORBIDDEN_CMAKE = re.compile(r"\b(find_package|FetchContent\w*|ExternalProject\w*|pkg_check_modules|"
                             r"target_link_libraries|add_subdirectory|file\s*\(\s*DOWNLOAD)\b", re.I)

def _script() -> str:
    """The shell script run in the sandbox. Its working directory is the agent's workspace."""
    warn, asan = cpp_metrics.compiler("warn", "-Wall -Wextra"), cpp_metrics.compiler("asan", SANITIZERS)
    lines = [
        "G=.grade",
        "mkdir -p $G/out $G/asan-out $G/invalid-out $G/cli",
        warn[0],
        asan[0],
        # 1. the imposed build
        "{ cmake -B build -G Ninja && cmake --build build; } > $G/build.log 2>&1; echo $? > $G/build.rc",
        # 2. -Wall -Wextra forced, from scratch, to count the warnings
        f"{{ cmake -B $G/warn -G Ninja {warn[1]} && cmake --build $G/warn --clean-first; }}"
        " > $G/warn.log 2>&1; echo $? > $G/warn.rc",
        # 3. sanitizers
        f"{{ cmake -B $G/asan -G Ninja -DCMAKE_BUILD_TYPE=Debug {asan[1]} && cmake --build $G/asan; }}"
        " > $G/asan.log 2>&1; echo $? > $G/asan.rc",
        # 4. strict warnings and clang-tidy, for the code metrics
        *cpp_metrics.sandbox_script(),
        "SIM=build/sim",
        # 5. hidden scenarios, then the same under the sanitizers
        "for f in $G/scenarios/*.txt; do n=$(basename $f .txt);"
        f"  (ulimit -v {MEMORY_KB}; timeout 10 $SIM --scenario $f --out $G/out/$n.out 2> $G/out/$n.err); echo $? > $G/out/$n.rc;"
        f"  ASAN_OPTIONS=hard_rss_limit_mb={ASAN_RSS_MB}:detect_leaks=0 timeout 30 $G/asan/sim --scenario $f"
        "   --out $G/asan-out/$n.out 2> $G/asan-out/$n.err; echo $? > $G/asan-out/$n.rc;"
        "done",
        # 6. performance and peak RAM, measured inside the sandbox
        f"(ulimit -v {MEMORY_KB}; python3 $G/measure.py 10 $G/perf.err $SIM --scenario $G/perf.txt --out $G/perf.out)"
        " > $G/perf.result",
        # 7. invalid input and command-line errors
        "for f in $G/invalid/*.txt; do n=$(basename $f .txt);"
        f"  (ulimit -v {MEMORY_KB}; timeout 5 $SIM --scenario $f --out $G/invalid-out/$n.out 2> $G/invalid-out/$n.err);"
        "  echo $? > $G/invalid-out/$n.rc; done",
    ]
    for name, args in CLI_ERRORS.items():
        lines.append(f"(ulimit -v {MEMORY_KB}; timeout 5 $SIM {args} 2> $G/cli/{name}.err); echo $? > $G/cli/{name}.rc")
    lines.append(f"(ulimit -v {MEMORY_KB}; timeout 10 $SIM --scenario examples/basic.txt --out $G/example.out"
                 " 2> $G/example.err); echo $? > $G/example.rc")
    return "\n".join(lines) + "\n"


def _read(path: Path, default: str = "") -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return default


def _rc(path: Path) -> int | None:
    text = _read(path).strip()
    return int(text) if text.lstrip("-").isdigit() else None


def _split(text: str) -> tuple[list[str], list[str], str]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    stops = [line for line in lines if not line.startswith(("passenger ", "summary "))]
    passengers = [line for line in lines if line.startswith("passenger ")]
    summary = next((line for line in reversed(lines) if line.startswith("summary ")), "")
    return stops, passengers, summary


def summary_matches(expected: str, got: str) -> bool:
    """Same summary, the averages within 0.01 (rounding of the last digit)."""
    a, b = expected.split(), got.split()
    if a[:1] != ["summary"] or b[:1] != ["summary"]:
        return False
    a, b = a[1:], b[1:]   # then key value pairs
    if len(a) != len(b) or a[::2] != b[::2]:
        return False
    for key, x, y in zip(a[::2], a[1::2], b[1::2]):
        if key.startswith("avg_"):
            try:
                if abs(float(x) - float(y)) > 0.0101:
                    return False
            except ValueError:
                return False
        elif x != y:
            return False
    return True


def scenario_score(expected: str, got: str) -> dict:
    e_stops, e_pass, e_sum = _split(expected)
    g_stops, g_pass, g_sum = _split(got)
    passengers = len(set(e_pass) & set(g_pass)) / len(e_pass) if e_pass else 1.0
    stops = difflib.SequenceMatcher(None, e_stops, g_stops, autojunk=False).ratio() if e_stops or g_stops else 1.0
    summary = 1.0 if summary_matches(e_sum, g_sum) else 0.0
    return {"score": round(0.6 * passengers + 0.3 * stops + 0.1 * summary, 4), "passengers": round(passengers, 4),
            "stops": round(stops, 4), "summary": summary, "exact": expected.strip() == got.strip()}


def _includes(tree: Path, sources: list[Path]) -> list[str]:
    """Includes that are neither standard headers nor files of the project."""
    bad = []
    for src in sources:
        for m in re.finditer(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', _read(src), re.M):
            kind, name = m.groups()
            if kind == "<" and name in STD_HEADERS:
                continue
            if kind == '"' and ((src.parent / name).is_file() or any(p.name == Path(name).name for p in sources)):
                continue
            bad.append(f"{src.relative_to(tree)}: {name}")
    return bad


def _stage_inputs(g: Path) -> None:
    if g.exists():
        shutil.rmtree(g)
    (g / "scenarios").mkdir(parents=True)
    (g / "invalid").mkdir()
    for f in SCENARIOS:
        shutil.copy2(f, g / "scenarios" / f.name)
    for f in INVALID:
        shutil.copy2(f, g / "invalid" / f.name)
    (g / "perf.txt").write_text(perf_scenario())
    (g / "measure.py").write_text(MEASURE)


def _handled(rc_file: Path, err_file: Path) -> bool:
    return _rc(rc_file) == 2 and _read(err_file).startswith("error:")


def _sheet(built: bool, scores: dict, figures: dict) -> dict:
    """The cells of grade.md. When the build fails, Working is 0 and the rest N/A (GRADING.md)."""
    if not built:
        return {"Builds with the exact command": ["no"], "Working": ["0"]}
    notes = cpp_metrics.notes(figures["code"])
    perf = figures["perf_ms"]
    perf_text = "timeout" if perf is None else f"{perf} ms" + ("" if figures["perf_summary_ok"] else ", wrong summary")
    ram = figures["peak_ram_mb"]
    return {
        "Builds with the exact command": ["yes"],
        "Working": [f"{scores['working']:g}"],
        "Following the statement": [f"{scores['statement']:g}"],
        "Performance": [None, perf_text],
        "Resources": [None, f"{'?' if ram is None else ram} MB peak RAM"],
        **{row: [None, note] for row, note in notes.items()},
        "Safety": [None, f"sanitizers clean on {figures['sanitizer_clean']}; {notes['Safety']}"],
    }


def grade(tree: Path) -> dict:
    g = tree / ".grade"
    _stage_inputs(g)
    try:
        run = sandbox_exec(_script(), tree, timeout_s=1200)
        sandbox_log = (run.stdout + run.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        sandbox_log = "grading timed out"

    built = _rc(g / "build.rc") == 0 and (tree / "build" / "sim").is_file()
    warnings = len(re.findall(r": warning: ", _read(g / "warn.log")))
    sources = cpp_metrics.sources(tree)

    scenarios, survived, asan_clean = {}, [], 0
    for f in SCENARIOS:
        n = f.stem
        rc = _rc(g / "out" / f"{n}.rc")
        survived.append(rc == 0)
        got = _read(g / "out" / f"{n}.out") if built and rc == 0 else ""
        scenarios[n] = scenario_score(_read(HERE / "expected" / f"{n}.out"), got) if got \
            else {"score": 0.0, "rc": rc, "stderr": _read(g / "out" / f"{n}.err")[:300]}
        asan_err = _read(g / "asan-out" / f"{n}.err")
        asan_clean += "Sanitizer" not in asan_err and "runtime error" not in asan_err
    correctness = sum(s["score"] for s in scenarios.values()) / len(scenarios)

    perf_rc, perf_ms, perf_kib = (_read(g / "perf.result").split() + ["?", "?", "?"])[:3]
    perf_ok = built and perf_rc == "0" and summary_matches(PERF_SUMMARY, _split(_read(g / "perf.out"))[2])
    invalid = {f.stem: _handled(g / "invalid-out" / f"{f.stem}.rc", g / "invalid-out" / f"{f.stem}.err") for f in INVALID}
    cli_errors = {name: _handled(g / "cli" / f"{name}.rc", g / "cli" / f"{name}.err") for name in CLI_ERRORS}
    robustness = [*invalid.values(), *cli_errors.values(), *survived, perf_rc == "0"]
    example = _read(g / "example.out").splitlines()
    cli_ok = built and _rc(g / "example.rc") == 0 and bool(example) and SUMMARY_LINE.fullmatch(example[-1]) is not None \
        and all(STOP_LINE.fullmatch(x) or PASSENGER_LINE.fullmatch(x) for x in example[:-1])

    scores = {"statement": round(10 * correctness, 1) if built else 0.0,
              "working": round(10 * sum(robustness) / len(robustness), 1) if built else 0.0}
    figures = {
        "exact_scenarios": f"{sum(s.get('exact', False) for s in scenarios.values())}/{len(SCENARIOS)}",
        "perf_ms": int(perf_ms) if perf_rc == "0" and perf_ms.isdigit() else None,
        "perf_summary_ok": perf_ok,
        "peak_ram_mb": round(int(perf_kib) / 1024, 1) if perf_rc == "0" and perf_kib.isdigit() else None,
        "warnings": warnings if _rc(g / "warn.rc") == 0 else None,
        "sanitizer_clean": f"{asan_clean}/{len(SCENARIOS)}" if _rc(g / "asan.rc") == 0 else "no sanitizer build",
        "code": cpp_metrics.measure(tree, g, created_files(tree, FIXTURE)),
    }
    return {
        "scores": scores,
        "checks": {
            "builds": built,
            "stdlib-only": not FORBIDDEN_CMAKE.search(_read(tree / "CMakeLists.txt")) and not _includes(tree, sources),
            "no-warnings": _rc(g / "warn.rc") == 0 and warnings == 0,
            "output-format": cli_ok,
            "under-one-second": perf_ok and figures["perf_ms"] is not None and figures["perf_ms"] <= PERF_LIMIT_MS,
        },
        "figures": figures,
        "sheet": _sheet(built, scores, figures),
        "details": {
            "scenarios": scenarios,
            "invalid_input": invalid,
            "cli_errors": cli_errors,
            "perf": {"rc": perf_rc, "stderr": _read(g / "perf.err")[-500:]},
            "foreign_includes": _includes(tree, sources),
            "source_files": [s.relative_to(tree).as_posix() for s in sources],
            "build_log": _read(g / "build.log")[-2000:],
            "sandbox_log": sandbox_log,
        },
    }


if __name__ == "__main__":
    print(json.dumps(grade(Path(sys.argv[1]).resolve()), indent=2))
