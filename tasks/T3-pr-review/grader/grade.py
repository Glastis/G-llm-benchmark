"""T3 grader: matches the comments of review.json with the seeded bugs (build/seeded_bugs.yaml) and
computes recall, precision and F1 (PLAN §4 T3, §10.28).

A comment finds a bug when it names the same file, a line within TOLERANCE of the bug's lines, and
its description matches one of the bug's keywords. Each comment finds at most one bug, each bug
counts once. Every other comment counts as a false positive, even a real problem the key does not
list (§10.32); they are listed in full in the report.
Nothing is executed: the review is only read.

Scores (0 when review.json cannot be read as JSON):
- review: 10 × F1;
- statement: 10 × the share of the checks passed (schema, no file touched, valid severities);
- severity: over the bugs found, 1 for the key's severity, 0.5 one level off, 0 otherwise, times 10;
  None when no bug is found.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from bench.grade import changed_files, created_files

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
BUGS = HERE.parent / "build" / "seeded_bugs.yaml"
DELIVERABLE = "review.json"
TOLERANCE = 5
LEVELS = ["low", "medium", "high", "critical"]
SEVERITIES = set(LEVELS)
FIELDS = {"file", "line", "severity", "description"}


def load_bugs() -> list[dict]:
    bugs = yaml.safe_load(BUGS.read_text())
    for bug in bugs:
        lines = (FIXTURE / bug["file"]).read_text().splitlines()
        hits = [i for i, line in enumerate(lines, 1) if bug["anchor"] in line]
        if len(hits) != 1:
            raise ValueError(f"{bug['id']}: anchor found {len(hits)} times in {bug['file']}")
        bug["lines"] = [hits[0], hits[0] + bug["span"]]
    return bugs


def check_schema(review: object) -> list[str]:
    """What breaks review.schema.json (no external validator: the schema is small)."""
    if not isinstance(review, dict):
        return ["the document is not an object"]
    errors = [f"unexpected key {k}" for k in review if k not in ("summary", "comments")]
    if "summary" in review and not isinstance(review["summary"], str):
        errors.append("summary is not a string")
    comments = review.get("comments")
    if not isinstance(comments, list):
        return errors + ["comments is missing or not a list"]
    for i, c in enumerate(comments):
        if not isinstance(c, dict):
            errors.append(f"comment {i} is not an object")
            continue
        if missing := FIELDS - set(c):
            errors.append(f"comment {i}: missing {', '.join(sorted(missing))}")
        if extra := set(c) - FIELDS:
            errors.append(f"comment {i}: unexpected {', '.join(sorted(extra))}")
        if "file" in c and not isinstance(c["file"], str):
            errors.append(f"comment {i}: file is not a string")
        if "line" in c and (not isinstance(c["line"], int) or isinstance(c["line"], bool) or c["line"] < 1):
            errors.append(f"comment {i}: line is not a positive integer")
        if "description" in c and (not isinstance(c["description"], str) or not c["description"].strip()):
            errors.append(f"comment {i}: empty description")
        if "severity" in c and c["severity"] not in SEVERITIES:
            errors.append(f"comment {i}: severity {c['severity']!r}")
    return errors


def _norm(path: object) -> str:
    text = str(path).strip().replace("\\", "/")
    return re.sub(r"^(\./|/?workspace/|[ab]/)", "", text)


def _distance(comment: dict, bug: dict, tolerance: float = TOLERANCE) -> float | None:
    """Line distance between the comment and the bug, None when the comment cannot find it."""
    if _norm(comment.get("file")) != bug["file"] or not isinstance(comment.get("line"), int):
        return None
    start, end = bug["lines"]
    line = comment["line"]
    distance = 0 if start <= line <= end else min(abs(line - start), abs(line - end))
    if distance > tolerance:
        return None
    text = str(comment.get("description", ""))
    if not any(re.search(k, text, re.I) for k in bug["keywords"]):
        return None
    return distance


def match(comments: list[dict], bugs: list[dict], tolerance: float = TOLERANCE) -> dict:
    """Assigns comments to bugs: the bugs with the fewest candidates first, the closest comment."""
    candidates = {b["id"]: sorted((d, i) for i, c in enumerate(comments)
                                  if (d := _distance(c, b, tolerance)) is not None)
                  for b in bugs}
    found: dict[str, int] = {}
    used: set[int] = set()
    for bug_id in sorted(candidates, key=lambda b: len(candidates[b])):
        for _, i in candidates[bug_id]:
            if i not in used:
                found[bug_id] = i
                used.add(i)
                break
    # A comment that only repeats a bug already found is a duplicate, not a false positive.
    duplicates = sorted(i for b, cands in candidates.items() if b in found for _, i in cands if i not in used)
    unmatched = [i for i in range(len(comments)) if i not in used and i not in duplicates]
    return {"found": found, "duplicates": duplicates, "unmatched": unmatched}


def score(n_bugs: int, n_found: int, false_positives: int) -> dict:
    recall = n_found / n_bugs
    precision = n_found / (n_found + false_positives) if n_found + false_positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"recall": round(recall, 4), "precision": round(precision, 4), "f1": round(f1, 4)}


def severity_score(severities: dict[str, tuple[object, str]]) -> float | None:
    """10 × the mean credit of the bugs found: 1 for the key's severity, 0.5 one level off."""
    def credit(got: object, want: str) -> float:
        if got not in SEVERITIES:
            return 0.0
        return {0: 1.0, 1: 0.5}.get(abs(LEVELS.index(got) - LEVELS.index(want)), 0.0)
    if not severities:
        return None
    return round(10 * sum(credit(*pair) for pair in severities.values()) / len(severities), 1)


def _review(tree: Path) -> tuple[list[dict], list[str], bool]:
    """The comments that are objects, what is wrong with the document, and whether it is JSON at all."""
    try:
        review = json.loads((tree / DELIVERABLE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [], [str(e)], False
    comments = review.get("comments") if isinstance(review, dict) else None
    return [c for c in comments if isinstance(c, dict)] if isinstance(comments, list) else [], check_schema(review), True


def _sheet(delivered: bool, scores: dict, checks: dict, figures: dict) -> dict:
    """The cells of grade.md. When review.json cannot be read, every score is 0 (GRADING.md)."""
    if not delivered:
        return {"`review.json` readable as JSON": ["no"],
                **{row: ["0"] for row in ("Bugs found", "Following the statement", "Severity")}}
    failed = [name for name, ok in checks.items() if not ok]
    severity = scores["severity"]
    return {
        "`review.json` readable as JSON": ["yes"],
        "Bugs found": [f"{scores['review']:g}", f"{figures['found']} found ({figures['found_ignoring_lines']} ignoring"
                       f" the lines), precision {figures['precision']:g}, {figures['unmatched']} unmatched comments,"
                       f" {figures['duplicates']} duplicates"],
        "Following the statement": [f"{scores['statement']:g}",
                                    f"failed: {', '.join(failed)}" if failed else "every check passed"],
        "Severity": ["N/A" if severity is None else f"{severity:g}", f"{figures['same_severity']} exact"],
    }


def grade(tree: Path) -> dict:
    bugs = load_bugs()
    comments, schema_errors, delivered = _review(tree)
    m = match(comments, bugs)
    s = score(len(bugs), len(m["found"]), len(m["unmatched"]))
    severities = {b["id"]: (comments[m["found"][b["id"]]].get("severity"), b["severity"])
                  for b in bugs if b["id"] in m["found"]}
    edited = changed_files(tree, FIXTURE) + created_files(tree, FIXTURE, allowed=(DELIVERABLE,))
    checks = {
        "json-valid": not schema_errors,
        "no-code-edit": not edited,
        "severity-enum": bool(comments) and all(c.get("severity") in SEVERITIES for c in comments),
    }
    scores = {"review": round(10 * s["f1"], 1), "statement": round(10 * sum(checks.values()) / len(checks), 1),
              "severity": severity_score(severities)}
    if not delivered:
        scores = dict.fromkeys(scores, 0.0)
    figures = {
        **s,
        "found": f"{len(m['found'])}/{len(bugs)}",
        # A review that describes the bugs but cites the wrong lines shows up here.
        "found_ignoring_lines": f"{len(match(comments, bugs, float('inf'))['found'])}/{len(bugs)}",
        "unmatched": len(m["unmatched"]),
        "duplicates": len(m["duplicates"]),
        "same_severity": f"{sum(got == want for got, want in severities.values())}/{len(severities)}",
    }
    return {
        "scores": scores,
        "checks": checks,
        "figures": figures,
        "sheet": _sheet(delivered, scores, checks, figures),
        "details": {
            "found": {b["id"]: m["found"].get(b["id"]) for b in bugs},
            "missed": [b["id"] for b in bugs if b["id"] not in m["found"]],
            "severities": severities,
            "unmatched_comments": [comments[i] for i in m["unmatched"]],
            "duplicates": m["duplicates"],
            "schema_errors": schema_errors[:20],
            "edited_files": edited[:20],
        },
    }


if __name__ == "__main__":
    print(json.dumps(grade(Path(sys.argv[1]).resolve()), indent=2))
