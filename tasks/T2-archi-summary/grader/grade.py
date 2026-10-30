"""T2 grader: the objective part of the summary's grading (PLAN §4 T2, §10.28). Nothing is executed.

- Form: the imposed sections in order, at most 1,200 words outside fenced blocks, a diagram.
- References: every inline code span that looks like a path or an identifier must exist in the
  fixture, as a file or folder, or as text in some file. A missing one is often an invention; a
  reference to something the code only gets from outside (an API of the mod itself, say) can also
  miss, so the list is for the author to judge.
Whether each statement is true stays a judgement: no score here.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bench.grade import changed_files, created_files

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
DELIVERABLE = "ARCHITECTURE.md"
SECTIONS = ["Purpose", "Layout", "Components", "Entry points", "Data flows", "Diagram", "Observations"]
MAX_WORDS = 1200

FENCE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[ \t]*$", re.M | re.S)
SPAN = re.compile(r"`([^`\n]+)`")
PATH = re.compile(r"[\w.-]*(/[\w.*-]*)+|[\w-]+\.\w{1,5}")
IDENT = re.compile(r"[A-Za-z_][\w]*([.:][A-Za-z_]\w*)*(\(\))?")


def sections(text: str) -> list[tuple[str, str]]:
    """The second-level sections (title, body), fenced blocks left intact."""
    prose = FENCE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)   # headings inside fences don't count
    heads = [(m.start(), m.end(), m.group(1).strip()) for m in re.finditer(r"^##[ \t]+(.+?)[ \t#]*$", prose, re.M)]
    return [(title, text[end:heads[i + 1][0] if i + 1 < len(heads) else len(text)])
            for i, (_, end, title) in enumerate(heads)]


def _title(title: str) -> str:
    return re.sub(r"^\d+[.)]?\s*", "", title).strip().lower()


def words(text: str) -> int:
    """Words as `wc -w` counts them, fenced blocks excluded."""
    return len(FENCE.sub(" ", text).split())


def has_diagram(body: str) -> bool:
    return any(len(block.group(0).strip().splitlines()) >= 4 for block in FENCE.finditer(body))


def references(text: str) -> list[str]:
    """The inline code spans outside fenced blocks that are a path or an identifier, each once."""
    spans = (s.strip() for s in SPAN.findall(FENCE.sub(" ", text)))
    return list(dict.fromkeys(s for s in spans if PATH.fullmatch(s) or IDENT.fullmatch(s)))


class Corpus:
    """The fixture's paths and text, read once. A path may be cited without its extension, as Lua
    modules are required."""

    def __init__(self, root: Path):
        entries = list(root.rglob("*"))
        self.paths = {p.relative_to(root).as_posix() for p in entries}
        self.paths |= {path.rsplit(".", 1)[0] for path in self.paths if "." in Path(path).name}
        self.names = {p.name for p in entries} | {p.stem for p in entries}
        self.files = {p: p.read_text(errors="replace") for p in entries if p.is_file()}
        self.text = "\n".join(self.files.values())

    def _word(self, name: str, text: str | None = None) -> bool:
        if text is None and name in self.names:
            return True
        return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", self.text if text is None else text) is not None

    def _member(self, ref: str) -> bool:
        """`module.name`, as callers write it: the module's file mentions the name."""
        module, *_, name = re.split(r"[.:]", ref)
        return any(p.stem == module and self._word(name, text) for p, text in self.files.items())

    def _path(self, path: str) -> bool:
        if "*" in path:
            prefix = path.split("*")[0].rstrip("/")
            return any(p.startswith(prefix) for p in self.paths)
        return path in self.paths or path in self.names or any(p.endswith("/" + path) for p in self.paths)

    def has(self, ref: str) -> bool:
        if not PATH.fullmatch(ref) or IDENT.fullmatch(ref):
            name = ref.removesuffix("()")
            return self._word(name) or ("." in name or ":" in name) and self._member(name)
        path = re.sub(r"^\./|^/", "", ref).rstrip("/.")
        # Otherwise a module path quoted in the code, or a list of alternatives such as `up/down`.
        return self._path(path) or path in self.text or all(self._word(part) for part in path.split("/") if part)


def grade(tree: Path, fixture: Path = FIXTURE) -> dict:
    path = tree / DELIVERABLE
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    found = sections(text)
    titles = [_title(t) for t, _ in found]
    wanted = [s.lower() for s in SECTIONS]
    diagram_body = next((b for t, b in found if _title(t) == "diagram"), "")
    corpus = Corpus(fixture)
    refs = references(text)
    missing = [r for r in refs if not corpus.has(r)]
    edited = changed_files(tree, fixture) + created_files(tree, fixture, allowed=(DELIVERABLE,))
    return {
        "scores": {},
        "checks": {
            "delivered": bool(text.strip()),
            "sections": [t for t in titles if t in wanted] == wanted,
            "word-limit": bool(text.strip()) and words(text) <= MAX_WORDS,
            "diagram": has_diagram(diagram_body),
            "no-code-edit": not edited,
        },
        "figures": {
            "words": words(text),
            "references": len(refs),
            "references_missing": len(missing),
        },
        "details": {
            "sections_found": [t for t, _ in found],
            "missing_references": missing,
            "edited_files": edited[:20],
        },
    }


if __name__ == "__main__":
    print(json.dumps(grade(Path(sys.argv[1]).resolve()), indent=2))
