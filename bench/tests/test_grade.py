"""The pure parts of the graders: scoring, matching, parsing, and the grading sheet. Building and running
agent code is left to `bench grade` on real runs."""

import json

from bench.config import ROOT
from bench.grade import fill_sheet, finished_runs, load_module

TASKS = ROOT / "tasks"


def load(task: str, name: str):
    return load_module(TASKS / task / "grader" / f"{name}.py", f"test_{task}_{name}".replace("-", "_"))


# The grading sheet and the runs

def test_sheet_fills_blank_cells_and_replaces_its_own():
    text = ("| Builds with the exact command | yes / no |\n| Working | 0 (auto) | — | |\n"
            "| Performance | | 812 ms (auto) | |\n| Resources | 7 | 40 MB | mine |\n")
    sheet = {"Builds with the exact command": ["yes"], "Performance": [None, "500 ms"], "Resources": ["3", "50 MB"]}
    once = fill_sheet(text, sheet)
    assert once == ("| Builds with the exact command | yes (auto) |\n| Working | | — | |\n"
                    "| Performance | | 500 ms (auto) | |\n| Resources | 7 | 40 MB | mine |\n")
    assert fill_sheet(once, sheet) == once


def test_finished_runs_leave_out_attempts_and_quota(tmp_path):
    for name, status in (("r1", "ok"), ("r2", "quota"), ("r1.attempt-20261027", "ok"), ("r3", "timeout")):
        (tmp_path / "c9" / "T" / "c" / name).mkdir(parents=True)
        (tmp_path / "c9" / "T" / "c" / name / "run.json").write_text(json.dumps({"status": status}))
    assert [p.name for p in finished_runs("c9", tmp_path)] == ["r1", "r3"]


# T1

def test_t1_scenario_score_gives_partial_credit():
    t1 = load("T1-simulation", "grade")
    expected = (TASKS / "T1-simulation" / "grader" / "expected" / "02-collect-along.out").read_text()
    assert t1.scenario_score(expected, expected) == {"score": 1.0, "passengers": 1.0, "stops": 1.0, "summary": 1.0, "exact": True}
    first = next(line for line in expected.splitlines() if line.startswith("passenger "))
    partial = t1.scenario_score(expected, expected.replace(first, first.split(" wait ")[0] + " wait 999 ride 1"))
    assert 0 < partial["score"] < 1 and partial["stops"] == 1.0


def test_t1_summary_tolerates_the_last_decimal_only():
    t1 = load("T1-simulation", "grade")
    ref = "summary passengers 3 makespan 175 avg_wait 18.33 max_wait 46 avg_ride 21.00"
    assert t1.summary_matches(ref, ref.replace("18.33", "18.34"))
    assert not t1.summary_matches(ref, ref.replace("18.33", "18.40"))
    assert not t1.summary_matches(ref, ref.replace("makespan 175", "makespan 176"))


def test_t1_oracle_reproduces_the_example_and_the_hidden_traces():
    oracle = load("T1-simulation", "oracle")
    examples, grader = TASKS / "T1-simulation" / "fixture" / "examples", TASKS / "T1-simulation" / "grader"
    assert oracle.run((examples / "basic.txt").read_text()) == (examples / "basic.out").read_text()
    for scenario in (grader / "scenarios").glob("*.txt"):
        assert oracle.run(scenario.read_text()) == (grader / "expected" / f"{scenario.stem}.out").read_text()


def test_t1_oracle_rejects_every_invalid_file():
    oracle = load("T1-simulation", "oracle")
    for path in (TASKS / "T1-simulation" / "grader" / "invalid").glob("*.txt"):
        try:
            oracle.parse(path.read_text())
        except oracle.InputError:
            continue
        raise AssertionError(f"{path.name} accepted")


# T3

def test_t3_matching_and_f1():
    t3 = load("T3-pr-review", "grade")
    bugs = t3.load_bugs()
    injection = next(b for b in bugs if b["id"] == "sort-injection")
    line = injection["lines"][0]
    comments = [
        {"file": injection["file"], "line": line + 3, "severity": "critical", "description": "SQL injection via sort"},
        {"file": injection["file"], "line": line, "severity": "high", "description": "sort is not validated"},
        {"file": "src/cli.cpp", "line": 3, "severity": "low", "description": "rename this variable"},
        {"file": injection["file"], "line": line + 20, "severity": "high", "description": "injection"},
    ]
    m = t3.match(comments, bugs)
    # The closest comment wins, the other one is a duplicate; the off-topic and too-far ones remain.
    assert m["found"] == {"sort-injection": 1} and m["duplicates"] == [0] and m["unmatched"] == [2, 3]
    assert t3.match(comments, bugs, float("inf"))["found"] == {"sort-injection": 1}
    s = t3.score(len(bugs), 1, 2)
    assert s["recall"] == round(1 / 7, 4) and s["precision"] == round(1 / 3, 4)


def test_t3_schema_errors():
    t3 = load("T3-pr-review", "grade")
    assert t3.check_schema({"comments": [{"file": "a.cpp", "line": 3, "severity": "high", "description": "x"}]}) == []
    errors = t3.check_schema({"comments": [{"file": "a.cpp", "line": 0, "severity": "urgent", "description": "", "extra": 1}]})
    assert len(errors) == 4


# T2 (generic checks only: the fixture is private)

def test_t2_sections_words_and_diagram():
    t2 = load("T2-archi-summary", "grade")
    doc = "# Title\n\n" + "".join(f"## {i}. {name}\n\ntext text\n\n" for i, name in enumerate(t2.SECTIONS, 1))
    doc = doc.replace("## 6. Diagram\n\ntext text", "## 6. Diagram\n\n```mermaid\ngraph TD\n  A --> B\n  B --> C\n```")
    assert [t2._title(t) for t, _ in t2.sections(doc)] == [s.lower() for s in t2.SECTIONS]
    assert t2.has_diagram(dict(t2.sections(doc))["6. Diagram"])
    assert t2.words(doc) == t2.words(doc.replace("A --> B", "A --> B --> D --> E"))
    assert t2.words("a lib/x-y.lua b") == 3
    assert not t2.has_diagram("no block here")


def test_t2_references_are_checked_against_the_code(tmp_path):
    t2 = load("T2-archi-summary", "grade")
    (tmp_path / "lib" / "net").mkdir(parents=True)
    (tmp_path / "lib" / "net" / "route.lua").write_text("local M = {}\nfunction M.send(x) end\nreturn M\n")
    (tmp_path / "main.lua").write_text('local route = require("lib/net/route")\nprint(up, down)\n')
    corpus = t2.Corpus(tmp_path)
    doc = "`lib/net/route.lua`, `net/route`, `route.send()`, `up/down`, `main.lua`, `print` and `x = 1`\n" \
          "but `lib/net/peer.lua` and `route.receive`\n```\n`fenced.lua`\n```\n"
    refs = t2.references(doc)
    assert "x = 1" not in refs and "fenced.lua" not in refs
    assert [r for r in refs if not corpus.has(r)] == ["lib/net/peer.lua", "route.receive"]


# C++ code metrics

def test_strip_blanks_comments_and_literals_and_keeps_lines():
    from bench.cpp_metrics import strip
    code, comments = strip('int a = 1; // note\nconst char* s = "x { y"; /* two\nlines */ char c = \'{\';\n')
    assert code.count("\n") == 3 and "{" not in code and "note" not in code
    assert [line for line, _ in comments] == [1, 2, 3]


def test_measure_counts_what_grading_md_asks(tmp_path):
    from bench.cpp_metrics import measure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "game.hpp").write_text(
        "#pragma once\n#include <SDL.h>\ntemplate <class T> T twice(T x) { return x + x; }\n"
        "constexpr int square(int x) { return x * x; }\nclass Game {\npublic:\n  int money() const { return money_; }\n"
        "private:\n  int money_ = 0;\n};\n")
    (tmp_path / "src" / "rules.cpp").write_text(
        '#include "rules.hpp"\n#define MAX 8\nenum Kind { A, B };\nconst int kLimit = 3;\nstruct Cell { int x; };\n'
        "int pick(int k) {\n  // TODO: tidy\n  // return 0;\n  if (k == 1) { return 1; } else if (k == 2) { return 2; }"
        " else if (k == 3) { return 3; }\n  switch (k) { default: break; }\n  int* p = new int(k);\n  delete p;\n  return 0;\n}\n")
    (tmp_path / "src" / "rules.hpp").write_text("#pragma once\nint pick(int k);\n")
    (tmp_path / "out.log").write_text("debug\n")
    m = measure(tmp_path, tmp_path / ".grade", created=["out.log", "src/rules.cpp", "tests/in.txt"])
    a, c, f, s = m["architecture"], m["cleanliness"], m["factoring"], m["safety"]
    assert a["header_function_bodies"]["count"] == 1   # money(): twice() and square() are allowed
    assert a["in_cpp"] == {"enums": 1, "classes": 1, "constants": 1}
    assert a["sdl_free_share"] < 1 and a["files_in_include_cycles"] == 0
    assert f["else_if_chains"]["count"] == 1 and f["switches"]["count"] == 1
    assert c["todos"]["count"] == 1 and c["commented_code_lines"]["count"] == 1
    assert c["defines"]["count"] == 1 and c["plain_enums"]["count"] == 1 and c["leftover_files"] == ["out.log"]
    assert s["manual_memory"]["count"] == 2
    assert m["readability"]["comments"]["count"] == 2


def test_duplication_ignores_names_and_literals():
    from bench.cpp_metrics import DUPLICATE_TOKENS, _duplicated_lines
    block = [("ID", 0), ("(", 0), ("N", 0), (")", 0), (";", 0)] * (DUPLICATE_TOKENS // 5 + 1)
    units = [(tok, (0, k)) for k, (tok, _) in enumerate(block)] + [("{", (1, 0))] \
        + [(tok, (2, k)) for k, (tok, _) in enumerate(block)]
    assert {f for f, _ in _duplicated_lines(units)} == {0, 2}


def test_stage_leaves_out_a_top_level_build(tmp_path):
    from bench.grade import stage
    (tmp_path / "final" / "build").mkdir(parents=True)
    (tmp_path / "final" / "src" / "build").mkdir(parents=True)
    (tmp_path / "final" / "main.cpp").write_text("int main() {}\n")
    tree = stage(tmp_path / "final", "x", root=tmp_path / "grading")
    assert sorted(p.relative_to(tree).as_posix() for p in tree.rglob("*")) == ["main.cpp", "src", "src/build"]


# T4

def _write_png(path, rows):
    """An 8-bit RGBA PNG from rows of RGBA bytes."""
    import struct
    import zlib

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    header = struct.pack(">IIBBBBB", len(rows[0]) // 4, len(rows), 8, 6, 0, 0, 0)
    data = zlib.compress(b"".join(b"\0" + row for row in rows))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", data) + chunk(b"IEND", b""))


def test_t4_oracle_gives_the_statement_example():
    scenarios = load("T4-game", "scenarios")
    assert scenarios.expected([["place", "house", 3, 4], ["step", 2]]) == ["ok 0 900 0 playing", "- 2 900 0 playing"]
    assert scenarios.script([["place", "road", -1, 0], ["reset"]]) == "place road -1 0\nreset\n"
    t4 = load("T4-game", "grade")
    assert t4.match(["a", "b", "c", "d"], ["a", "x", "c"]) == 0.5


def test_t4_tiles_are_recognised_cell_by_cell(tmp_path):
    png, tiles = load("T4-game", "png"), load("T4-game", "tiles")
    assets = TASKS / "T4-game" / "fixture" / "assets"
    grass = png.read(assets / "opaque" / "grass_plain.png").rows
    tree = png.read(assets / "transparent" / "mushrooms_red.png").rows
    quarters = [png.read(assets / "opaque" / f"{n}.png").rows for n in ("dirt_plain", "pavement_plain", "wall_red_door", "roof_blue_center")]

    def doubled(rows):
        return [b"".join(row[i:i + 4] * 2 for i in range(0, len(row), 4)) for row in rows for _ in range(2)]

    def over(base, top):
        return [b"".join(t[i:i + 4] if t[i + 3] == 255 else b[i:i + 4] for i in range(0, len(b), 4)) for b, t in zip(base, top)]

    cells = {(0, 0): doubled(over(grass, tree)), (1, 0): [q1 + q2 for q1, q2 in zip(quarters[0], quarters[1])]
             + [q3 + q4 for q3, q4 in zip(quarters[2], quarters[3])], (2, 0): [b"\x10\x20\x30\xff" * 32] * 32}
    image = []
    for y in range(16 * 32):
        row = b""
        for x in range(24):
            cell = cells.get((x, y // 32), doubled(grass))
            row += cell[y % 32]
        image.append(row)
    _write_png(tmp_path / "shot.png", image)
    shot = tiles.Shot(tmp_path / "shot.png", tiles.Tiles(assets))
    assert shot.cells[0, 0] == ["opaque/grass_plain", "transparent/mushrooms_red"]
    assert shot.cells[1, 0] == ["opaque/dirt_plain", "opaque/pavement_plain", "opaque/roof_blue_center", "opaque/wall_red_door"]
    assert shot.cells[2, 0] == [] and shot.cells[5, 5] == ["opaque/grass_plain"]
    assert shot.signature((2, 0)).startswith("pixels:")


def test_t4_tile_checks():
    tiles = load("T4-game", "tiles")

    class Fake:
        def __init__(self, cells, looks):
            self.cells, self.looks = cells, looks

        def signature(self, cell):
            return "+".join(self.cells[cell]) or "pixels"

    roads = {(1, 1), (2, 1), (3, 1), (2, 0), (2, 2)}   # a cross with four arms
    cells = {c: ["a"] for c in roads} | {(5, 5): ["roof"], (6, 5): ["wall"], (8, 8): ["roof"], (9, 8): ["wall"]}
    looks = {(1, 1): "h", (3, 1): "h", (2, 1): "x", (2, 0): "v", (2, 2): "v"} | {c: "b" for c in cells if c not in roads}
    shot = Fake(cells, looks)
    found, figures = tiles.checks({"s": shot}, [("s", "house", [(5, 5), (6, 5)]), ("s", "shop", [(8, 8), (9, 8)])], ("s", roads))
    assert found["buildings-composed"] and not found["types-distinct"] and figures["same_tiles"] == ["house=shop"]
    assert tiles.road_shape((2, 1), roads) == ("cross", frozenset("NESW"))


def test_grading_flags_survive_a_cmakelists_that_overwrites_them(tmp_path):
    """The wrapper keeps the sanitizers of a build whose CMakeLists.txt sets CMAKE_CXX_FLAGS itself."""
    import subprocess
    from bench.cpp_metrics import compiler
    (tmp_path / "CMakeLists.txt").write_text('cmake_minimum_required(VERSION 3.20)\nproject(p CXX)\n'
                                             'set(CMAKE_CXX_FLAGS "-O1")\nadd_executable(p main.cpp)\n')
    (tmp_path / "main.cpp").write_text("int main(int argc, char**) { int a[2] = {0, 0}; return a[argc + 1]; }\n")
    write, use = compiler("asan", "-fsanitize=address", g=".grade")
    script = f"mkdir -p .grade && {write} && cmake -B .grade/b -G Ninja {use} > /dev/null && cmake --build .grade/b > /dev/null"
    subprocess.run(["sh", "-c", script], cwd=tmp_path, check=True)
    run = subprocess.run([str(tmp_path / ".grade" / "b" / "p")], capture_output=True, text=True)
    assert "AddressSanitizer" in run.stderr
