"""C++ code metrics of the code tasks, by criterion of GRADING.md (PLAN §10.29). Raw figures only: they
inform the author's grades and are never shown to the LLM judge.

Two halves. `sandbox_script` builds with strict warnings and runs clang-tidy: that configures the
agent's CMake project, so it runs in the sandbox, inside the grader's script. `measure` then reads
those logs and the sources: lizard for the functions, a small tokenizer for the rest. Counters come
with their rate per 1,000 lines of code.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import lizard

SOURCE_SUFFIXES = {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx", ".ipp", ".inl"}
HEADER_SUFFIXES = {".h", ".hpp", ".hh", ".hxx", ".ipp", ".inl"}
SKIPPED_DIRS = {"build", ".grade", ".git"}
KEPT_FILES = {"CMakeLists.txt", ".gitignore"}
KEPT_SUFFIXES = SOURCE_SUFFIXES | {".cmake", ".md"}
KEPT_DIRS = {"tests", "test", "docs", "doc"}   # test data and documentation are not leftovers
STRICT_FLAGS = "-Wall -Wextra -Wconversion -Wsign-conversion -Wshadow -Wpedantic"
TIDY_CHECKS = ",".join(["-*", "bugprone-*", "-bugprone-easily-swappable-parameters", "performance-*",
                        "misc-const-correctness", "readability-function-cognitive-complexity",
                        "readability-else-after-return"])
TIDY_CONFIG = "{CheckOptions: {readability-function-cognitive-complexity.Threshold: 0}}"
DUPLICATE_TOKENS = 75   # a block repeated over at least this many tokens, identifiers and literals ignored
KEYWORDS = set("""
alignas alignof auto bool break case catch char char8_t char16_t char32_t class co_await co_return
co_yield concept const consteval constexpr constinit const_cast continue decltype default delete do
double dynamic_cast else enum explicit export extern false float for friend goto if inline int long
mutable namespace new noexcept nullptr operator private protected public register reinterpret_cast
requires return short signed sizeof static static_assert static_cast struct switch template this
thread_local throw true try typedef typeid typename union unsigned using virtual void volatile
wchar_t while override final
""".split())
IDIOMS = {
    "enum class": r"\benum\s+(class|struct)\b",
    "optional": r"\bstd::optional\b",
    "variant": r"\bstd::variant\b",
    "string_view": r"\bstd::string_view\b",
    "span": r"\bstd::span\b",
    "ranges": r"\bstd::(ranges|views)::",
    "constexpr": r"\bconstexpr\b",
}
TOKEN = re.compile(r"[A-Za-z_]\w*|\d[\w.']*|::|->|\S")


def compiler(name: str, flags: str, g: str = "$G") -> tuple[str, str]:
    """A C++ compiler for a grading build: g++ with `flags` after the project's own, on every compile
    and link, which a CMakeLists.txt cannot drop the way it can overwrite CMAKE_CXX_FLAGS. Returns the
    shell line that writes it and the CMake option that selects it. Its name ends in g++, so that
    clang-tidy reads the compile database in C++ mode."""
    path = f"{g}/{name}-g++"
    return (f"printf '#!/bin/sh\\nexec g++ \"$@\" {flags}\\n' > {path} && chmod +x {path}",
            f"-DCMAKE_CXX_COMPILER=$PWD/{path}")


def sandbox_script(g: str = "$G") -> list[str]:
    """Shell lines for the grader's sandbox script: a strict build that also exports the compile
    database, then clang-tidy on every file of that database."""
    write, use = compiler("strict", STRICT_FLAGS, g)
    return [
        write,
        f"{{ cmake -B {g}/strict -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON {use}"
        f" && cmake --build {g}/strict --clean-first; }} > {g}/strict.log 2>&1",
        f"if [ -f {g}/strict/compile_commands.json ]; then"
        f"  for f in $(sed -n 's/.*\"file\": \"\\(.*\\)\".*/\\1/p' {g}/strict/compile_commands.json); do"
        f"    timeout 120 clang-tidy -p {g}/strict --quiet --checks='{TIDY_CHECKS}' --config='{TIDY_CONFIG}'"
        f" --header-filter=\"^$PWD/\" \"$f\";"
        f"  done > {g}/tidy.log 2>&1; fi",
    ]


def sources(tree: Path) -> list[Path]:
    return sorted(p for p in tree.rglob("*") if p.suffix in SOURCE_SUFFIXES and p.is_file()
                  and not SKIPPED_DIRS & set(p.relative_to(tree).parts))


def strip(text: str) -> tuple[str, list[tuple[int, str]]]:
    """The code with comments and literals blanked (lines kept), and the comments with their line."""
    out, comments = [], []
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if text.startswith("//", i) or text.startswith("/*", i):
            end = text.find("\n", i) if c == "/" and text[i + 1] == "/" else text.find("*/", i + 2) + 2
            end = n if end < 2 or end == -1 else end
            comment = text[i:end]
            comments += [(line + k, part) for k, part in enumerate(comment.split("\n"))]
            out.append(re.sub(r"[^\n]", " ", comment))
        elif c in "\"'":
            end = i + 1
            while end < n and text[end] != c and text[end] != "\n":
                end += 2 if text[end] == "\\" else 1
            end = min(end + 1, n)
            out.append(c + re.sub(r"[^\n]", " ", text[i + 1:end - 1]) + c)
        elif text.startswith('R"', i) and (m := re.match(r'R"([^(\s]*)\(', text[i:])):
            close = text.find(f"){m.group(1)}\"", i)
            end = n if close == -1 else close + len(m.group(1)) + 2
            out.append('""' + re.sub(r"[^\n]", " ", text[i + 2:end]))
        else:
            end = i + 1
            out.append(c)
        line += text.count("\n", i, end)
        i = end
    return "".join(out), comments


class Scopes:
    """The braces of a stripped file: for each `{`, the text before it (its header), the headers that
    enclose it and its commas; and the statements ended by `;` outside any function or class."""

    def __init__(self, code: str):
        self.blocks: list[dict] = []   # {header, line, parents: [headers], commas}
        self.top_statements: list[str] = []
        stack, start, line = [], 0, 1
        for i, c in enumerate(code):
            if c == "\n":
                line += 1
            elif c == "{":
                block = {"header": code[start:i].strip(), "line": line, "parents": [b["header"] for b in stack], "commas": 0}
                self.blocks.append(block)
                stack.append(block)
                start = i + 1
            elif c == "}":
                if stack:
                    stack.pop()
                start = i + 1
            elif c == ";":
                if all(NAMESPACE.match(_clean(b["header"])) for b in stack):
                    self.top_statements.append(_clean(code[start:i]))
                start = i + 1
            elif c == "," and stack:
                stack[-1]["commas"] += 1

    def inside(self, words: str, first: int, last: int) -> bool:
        """Whether a block opened between these lines has `words` in its header or in an enclosing one."""
        return any(first <= b["line"] <= last and any(re.search(words, h) for h in [b["header"], *b["parents"]])
                   for b in self.blocks)


NAMESPACE = re.compile(r"((inline\s+)?namespace|extern)\b")


def _clean(header: str) -> str:
    """A block header without its preprocessor lines."""
    return "\n".join(line for line in header.split("\n") if not line.lstrip().startswith("#")).strip()


def _kind(block: dict) -> str | None:
    """What a block of a .cpp file defines: an enum, a class, constant data (a brace initializer outside
    any function, or a `static` one inside), or None for code."""
    header = _clean(block["header"])
    if NAMESPACE.match(header):
        return None
    if re.search(r"\benum\b", header):
        return "enum"
    if re.search(r"\b(class|struct|union)\s+[A-Za-z_]\w*[^()]*$", header):
        return "class"
    at_top = all(NAMESPACE.match(_clean(h)) for h in block["parents"])
    if (at_top or re.search(r"\bstatic\b", header)) and re.search(r"(=|[A-Za-z_]\w*(\s*\[[^\]]*\])?)\s*$", header) \
            and not re.search(r"\breturn\b|\)\s*(const|override|noexcept|final|->[^=]*)?\s*$", header):
        return "constant"
    return None


def _constant(statement: str) -> bool:
    """A `const` or `constexpr` variable defined with `=` outside any function: `const int kMax = 8`."""
    head = statement.split("=", 1)[0]
    return "=" in statement and "(" not in head and re.search(r"\bconst(expr|init)?\b", head) is not None


def _rate(count: int, lines: int) -> dict:
    return {"count": count, "per_kloc": round(1000 * count / lines, 1) if lines else None}


def _spread(values: list[float]) -> dict:
    if not values:
        return {"median": None, "p90": None, "max": None}
    ordered = sorted(values)
    return {"median": statistics.median(ordered), "p90": ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))],
            "max": ordered[-1]}


def _tidy(log: str, tree: Path) -> dict:
    """clang-tidy warnings, each (file, line, check) once, and the cognitive complexity per function."""
    found, cognitive = set(), {}
    for m in re.finditer(r"^(/[^:\n]+):(\d+):\d+: warning: (.*) \[([\w.,-]+)\]$", log, re.M):
        path, line, message, check = m.groups()
        if not path.startswith(str(tree)) or "/.grade/" in path:
            continue
        if check == "readability-function-cognitive-complexity":
            if c := re.search(r"cognitive complexity of (\d+)", message):
                cognitive[(path, int(line))] = int(c.group(1))
        else:
            found.add((path, int(line), check))
    return {"by_check": dict(sorted(Counter(check for *_, check in found).items())), "cognitive": cognitive}


def _includes(tree: Path, files: list[Path], texts: dict[Path, str]) -> tuple[dict[Path, set[Path]], set[Path]]:
    """The project include graph, and the files that include SDL themselves."""
    by_name = defaultdict(list)
    for f in files:
        by_name[f.name].append(f)
    graph, sdl = {}, set()
    for f in files:
        graph[f] = set()
        for kind, name in re.findall(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', texts[f], re.M):
            if re.match(r"SDL", name):
                sdl.add(f)
            local = (f.parent / name).resolve()
            target = local if local in texts else next(iter(by_name.get(Path(name).name, [])), None)
            if target is not None and target != f:
                graph[f].add(target)
    return graph, sdl


def _reach(graph: dict[Path, set[Path]], start: Path) -> set[Path]:
    seen, todo = set(), [start]
    while todo:
        for nxt in graph[todo.pop()] - seen:
            seen.add(nxt)
            todo.append(nxt)
    return seen


def _else_if_chains(tokens: list[str]) -> int:
    """Chains of at least 3 branches: an `if` followed by two `else if` or more, at the same depth."""
    chains, depth, runs = 0, 0, defaultdict(int)
    for i, tok in enumerate(tokens):
        depth += (tok == "{") - (tok == "}")
        if tok == "if" and i and tokens[i - 1] == "else":
            runs[depth] += 1
            chains += runs[depth] == 3
        elif tok == "if":
            runs[depth] = 1
    return chains


def _duplicated_lines(units: list[tuple[str, int]]) -> set[tuple[int, int]]:
    """(file index, line) of the tokens inside a block that appears twice or more."""
    seen: dict[tuple, int] = {}
    covered: set[int] = set()
    norm = [tok for tok, _ in units]
    for i in range(len(norm) - DUPLICATE_TOKENS + 1):
        key = tuple(norm[i:i + DUPLICATE_TOKENS])
        if (first := seen.setdefault(key, i)) != i and first + DUPLICATE_TOKENS <= i:
            covered.update(range(first, first + DUPLICATE_TOKENS))
            covered.update(range(i, i + DUPLICATE_TOKENS))
    return {units[k][1] for k in covered}


def _commented_code(comment: str) -> bool:
    body = comment.strip().lstrip("/*").strip()
    return bool(re.search(r"[;{}]\s*$|^(if|for|while|return|std::|#include)\b", body))


def measure(tree: Path, grade_dir: Path, created: list[str]) -> dict:
    """The metrics of the sources of `tree`, with the logs that `sandbox_script` left in `grade_dir`.
    `created`: the files of the tree that the fixture does not have."""
    files = sources(tree)
    texts = {f.resolve(): f.read_text(errors="replace") for f in files}
    files = list(texts)
    stripped = {f: strip(t) for f, t in texts.items()}
    analysed = {f: lizard.analyze_file.analyze_source_code(str(f), texts[f]) for f in files}
    lines = sum(a.nloc for a in analysed.values())
    functions = [fn for a in analysed.values() for fn in a.function_list]
    tidy = _tidy(_read(grade_dir / "tidy.log"), tree)
    code_of = {f: stripped[f][0] for f in files}
    tokens = {f: [(m.group(0), code_of[f].count("\n", 0, m.start()) + 1) for m in TOKEN.finditer(code_of[f])] for f in files}
    all_tokens = [tok for f in files for tok, _ in tokens[f]]
    comments = [(f, line, text) for f in files for line, text in stripped[f][1] if text.strip(" /*")]

    # Architecture: implementations in headers, "config" in the .cpp files, includes.
    header_bodies, header_body_lines, in_cpp = 0, 0, Counter()
    for f in files:
        scopes = Scopes(code_of[f])
        if f.suffix in HEADER_SUFFIXES:
            code_lines = code_of[f].split("\n")
            for fn in analysed[f].function_list:
                head = " ".join(code_lines[max(0, fn.start_line - 3):fn.start_line])
                if re.search(r"\btemplate\s*<|\bconst(expr|eval)\b", head) \
                        or scopes.inside(r"\btemplate\s*<", fn.start_line, fn.start_line + 2):
                    continue
                header_bodies += 1
                header_body_lines += fn.nloc
        else:
            in_cpp.update(kind for b in scopes.blocks if (kind := _kind(b)))
            in_cpp["constant"] += sum(map(_constant, scopes.top_statements))
    graph, sdl = _includes(tree, files, texts)
    with_sdl = {f for f in files if f in sdl or _reach(graph, f) & sdl}
    cycles = sum(1 for f in files if f in _reach(graph, f))
    function_lines = sum(fn.nloc for fn in functions)

    # Factoring.
    units = [("ID" if tok not in KEYWORDS and re.match(r"[A-Za-z_]", tok) else "N" if tok[0].isdigit() else tok, (i, line))
             for i, f in enumerate(files) for tok, line in tokens[f]]
    duplicated = _duplicated_lines(units)
    code_lines = {(i, line) for i, f in enumerate(files) for _, line in tokens[f]}

    # Cleanliness and safety.
    code = "\n".join(code_of.values())
    defines = len(re.findall(r"^\s*#\s*define\s+\w+\s+\S", code, re.M))
    previous = [None, *all_tokens[:-1]]
    manual = sum(1 for tok, before in zip(all_tokens, previous)   # `= delete` is a deleted function
                 if tok == "new" and before != "operator" or tok == "delete" and before not in ("operator", "="))
    manual += len(re.findall(r"\b(malloc|calloc|realloc|free)\s*\(", code))
    cmake = "\n".join(_read(p) for p in tree.rglob("*") if p.is_file() and (p.name == "CMakeLists.txt" or p.suffix == ".cmake")
                      and not SKIPPED_DIRS & set(p.relative_to(tree).parts))
    strict_warnings = len({w for w in re.findall(r"^(/[^:\n]+:\d+:\d+): warning: .*\[(-W[\w-]+)\]",
                                                 _read(grade_dir / "strict.log"), re.M) if w[0].startswith(str(tree))})
    leftovers = [f for f in created if Path(f).suffix not in KEPT_SUFFIXES and Path(f).name not in KEPT_FILES
                 and not (SKIPPED_DIRS | KEPT_DIRS) & set(Path(f).parts[:-1])]
    by_check = tidy["by_check"]
    cognitive = list(tidy["cognitive"].values()) + [0] * max(0, len(functions) - len(tidy["cognitive"]))

    return {
        "lines": lines, "files": len(files), "functions": len(functions),
        "readability": {
            "function_lines": _spread([fn.nloc for fn in functions]),
            "cognitive_complexity": _spread(cognitive) if tidy["cognitive"] else None,
            "comments": _rate(len(comments), lines),
            "file_lines": _spread([a.nloc for a in analysed.values()]),
        },
        "architecture": {
            "header_function_bodies": {"count": header_bodies, "share_of_function_lines":
                                       round(header_body_lines / function_lines, 3) if function_lines else None},
            "in_cpp": {"enums": in_cpp["enum"], "classes": in_cpp["class"], "constants": in_cpp["constant"]},
            "includes_per_file": round(sum(map(len, graph.values())) / len(files), 2) if files else None,
            "files_in_include_cycles": cycles,
            "sdl_free_share": round(sum(analysed[f].nloc for f in files if f not in with_sdl) / lines, 3) if lines else None,
        },
        "factoring": {
            "duplicated_share": round(len(duplicated & code_lines) / len(code_lines), 3) if code_lines else None,
            "else_if_chains": _rate(_else_if_chains(all_tokens), lines),
            "switches": _rate(all_tokens.count("switch"), lines),
        },
        "cleanliness": {
            "todos": _rate(sum(bool(re.search(r"\b(TODO|FIXME|XXX|HACK)\b", t)) for *_, t in comments), lines),
            "commented_code_lines": _rate(sum(_commented_code(t) for *_, t in comments), lines),
            "leftover_files": leftovers[:20],
            "defines": _rate(defines, lines),
            "plain_enums": _rate(len(re.findall(r"\benum\b(?!\s+(class|struct)\b)", code)), lines),
            "cpp20_idioms": {name: len(re.findall(rx, code)) for name, rx in IDIOMS.items()},
            "else_after_return": _rate(by_check.get("readability-else-after-return", 0), lines),
            "cmake": {
                "hardcoded_paths": len(re.findall(r"[\"\s(](/(usr|home|opt|tmp)/[^\s\")]*)", cmake)),
                "sets_cmake_cxx_flags": bool(re.search(r"\bCMAKE_CXX_FLAGS\b", cmake)),
                "target_compile_options": bool(re.search(r"\btarget_compile_options\b", cmake)),
                "pkg_config": bool(re.search(r"\b(pkg_check_modules|pkg_search_module|PkgConfig)\b", cmake)),
            },
        },
        "safety": {
            "manual_memory": _rate(manual, lines),
            "strict_warnings": _rate(strict_warnings, lines),
            "tidy": {check: n for check, n in by_check.items() if check != "readability-else-after-return"},
        },
    }


def notes(m: dict) -> dict[str, str]:
    """One line per code criterion, for the Notes column of grade.md."""
    r, a, f, c, s = (m[k] for k in ("readability", "architecture", "factoring", "cleanliness", "safety"))
    fl, cc = r["function_lines"], r["cognitive_complexity"] or {}
    bodies = a["header_function_bodies"]
    tidy = sum(s["tidy"].values())
    return {
        "Readability": f"functions p90 {fl['p90']} / max {fl['max']} lines, cognitive p90 {cc.get('p90')} / max {cc.get('max')}, "
                       f"{r['comments']['per_kloc']} comments/kloc, files max {r['file_lines']['max']} lines",
        "Architecture": f"{bodies['count']} bodies in headers; in .cpp {a['in_cpp']['enums']} enums, {a['in_cpp']['classes']} classes, "
                        f"{a['in_cpp']['constants']} constants; {a['files_in_include_cycles']} files in include cycles",
        "Factoring": f"{round(100 * (f['duplicated_share'] or 0))} % duplicated, {f['else_if_chains']['count']} else-if chains, "
                     f"{f['switches']['count']} switch",
        "Cleanliness": f"{c['todos']['count']} TODO, {c['commented_code_lines']['count']} commented-out lines, "
                       f"{len(c['leftover_files'])} leftover files, {c['defines']['count']} #define, {c['plain_enums']['count']} plain enums",
        "Safety": f"{s['manual_memory']['count']} new/delete/malloc, {s['strict_warnings']['per_kloc']} strict warnings/kloc, "
                  f"{tidy} clang-tidy findings",
    }


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""
