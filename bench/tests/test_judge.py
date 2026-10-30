"""The blind judge, with the fake claude: what it gets to see, its verdict, the passes and the sheet."""

import json
from pathlib import Path

from bench import judge
from bench.config import ROOT, Task, load_all

FAKE = str(Path(__file__).with_name("fake_claude.py"))


def _task(tmp_path: Path, kind: str = "code") -> Task:
    (tmp_path / "task" / "fixture").mkdir(parents=True)
    (tmp_path / "task" / "fixture" / "README.md").write_text("haiku in the fixture stays\n")
    (tmp_path / "task" / "prompt.md").write_text("Write a program.\n")
    return Task(id="T1-simulation", title="t", timeout_min=1, prompt=Path("prompt.md"), fixture=Path("fixture"),
                deliverables=[], grading_sheet=True, judge=kind, dir=tmp_path / "task")


def _run(tmp_path: Path, text: str = "int main() {}\n") -> Path:
    run = tmp_path / "runs" / "c9" / "T1-simulation" / "opus-haiku" / "r1"
    (run / "final" / "src").mkdir(parents=True)
    (run / "final" / "build").mkdir()
    (run / "final" / "build" / "CMakeCache.txt").write_text("cache\n")
    (run / "final" / "README.md").write_text("haiku in the fixture stays\n")
    (run / "final" / "src" / "main.cpp").write_text(text)
    (run / "run.json").write_text(json.dumps({"run_id": "c9_T1-simulation_opus-haiku_r1", "status": "ok",
                                              "workspace": "/home/u/bench-ws/c9_T1-simulation_opus-haiku_r1"}))
    (run / "grade.md").write_text("| Readability | | metrics (auto) |\n| Safety | 6 | mine |\n")
    return run


def test_the_judge_sees_no_name(tmp_path):
    task, b = _task(tmp_path), load_all()
    run = _run(tmp_path, '// written by Claude for opus-haiku\nauto p = "/home/u/bench-ws/c9_T1-simulation_opus-haiku_r1/assets";\n')
    p = judge.stage(run, task, judge.names(b, json.loads((run / "run.json").read_text())), tmp_path / "judge")
    files = sorted(f.relative_to(p.ws).as_posix() for f in p.ws.rglob("*") if f.is_file())
    assert files == ["README.md", "_judge/STATEMENT.md", "src/main.cpp"]
    code = (p.ws / "src" / "main.cpp").read_text()
    assert "opus" not in code.lower() and "claude" not in code.lower() and "bench-ws" not in code
    assert code.count("[redacted]") == 3 and "/assets" in code
    assert (p.ws / "README.md").read_text() == "haiku in the fixture stays\n"   # a fixture file is left as it is


def test_one_pass_with_the_fake_claude(tmp_path):
    task, b = _task(tmp_path), load_all()
    run = _run(tmp_path)
    result = judge.judge_once(task, run, b, 1, claude_bin=FAKE, sandbox=False, root=tmp_path / "judge")
    assert result["status"] == "ok" and result["judgement"]["criteria"]["Safety"]["score"] == 7
    assert (run / "judge" / "pass1" / "transcript.jsonl").is_file() and not any((tmp_path / "judge").iterdir())


def test_passes_order_record_and_sheet(tmp_path):
    task = _task(tmp_path)
    run = _run(tmp_path)
    todo = judge.pending("c9", {"T1-simulation": task}, {"opus-haiku"}, passes=2, runs_root=tmp_path / "runs")
    assert [n for n, *_ in todo] == [1, 2]
    verdict = lambda s: {"status": "ok", "judgement": {"criteria": {n: {"score": s} for n in judge.CRITERIA["code"]}}}
    judge.record(run, task, 1, verdict(6))
    report = judge.record(run, task, 2, verdict(7))
    assert report["scores"]["Readability"] == 6.5 and report["spread"]["Readability"] == 1
    assert (run / "grade.md").read_text() == "| Readability | 6.5 (judge) | metrics (auto) |\n| Safety | 6 | mine |\n"
    assert judge.pending("c9", {"T1-simulation": task}, {"opus-haiku"}, passes=2, runs_root=tmp_path / "runs") == []


def test_the_code_prompt_carries_the_author_grid():
    text = judge.prompt("code")
    assert "{grid}" not in text and "Readability /10" in text and "template or `constexpr`" in text
    assert "## The program" not in text and (ROOT / "config" / "judge" / "summary.md").is_file()
