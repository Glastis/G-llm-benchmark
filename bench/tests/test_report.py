"""The campaign report: the statistics over the runs, the grades read from grade.md and the two ρ."""

import json
import random
from pathlib import Path

import pytest

from bench import report, stats

SHEET = """## Delivered

| `review.json` readable as JSON | yes (auto) |
|---|---|

## The review

| Criterion | Score /10 | Notes |
|---|---|---|
| Bugs found | {} | 5 of 7 |
| Following the statement | {} | |
| Severity | {} | |

## Remarks
"""


def test_describe_mean_interval_and_spread():
    s = stats.describe([9.2, 9.2, 1.5], 0, 10)
    assert round(s["mean"], 2) == 6.63 and s["median"] == 9.2 and round(s["sd"], 2) == 4.45
    assert s["ci"] == [0, 10]   # three runs this far apart say nothing of the mean
    s = stats.describe([7.5, 8.0, 7.5], 0, 10)
    assert [round(v, 2) for v in s["ci"]] == [6.95, 8.38] and (s["min"], s["max"]) == (7.5, 8.0)
    assert stats.describe([4.0])["sd"] is None and stats.describe([4.0])["ci"] is None
    assert stats.describe([]) is None


def test_spearman_and_reading():
    assert stats.spearman([1, 2, 3, 4], [10, 20, 30, 45]) == pytest.approx(1)
    assert stats.spearman([1, 2, 2, 3], [3, 2, 2, 1]) == pytest.approx(-1)   # tied values share their rank
    assert stats.spearman([1, 2, 3], [5, 5, 5]) is None and stats.spearman([1, 2], [1, 2]) is None
    assert [stats.reading(r) for r in (0.95, 0.8, 0.6, 0.2, None)] == ["excellent", "good", "moderate", "poor", "n/a"]


def test_judge_agreement():
    a = stats.agreement([(6, 7), (8, 8), (3, 4), (9, 8)])
    assert a["n"] == 4 and a["gap"] == 0.75 and round(a["rho"], 3) == 0.949


def test_split_half_ranking():
    steady = {f"c{i}": [i + d for d in (0, 0.1, -0.1, 0.05, -0.05, 0)] for i in range(5)}
    r = stats.split_half({**steady, "short": [1, 2, 3]}, splits=200)
    assert r["rho"] == pytest.approx(1) and r["contestants"] == 5 and r["min_runs"] == 6 and r["left_out"] == ["short"]
    rng = random.Random(1)
    noise = stats.split_half({f"c{i}": [rng.uniform(0, 10) for _ in range(6)] for i in range(6)}, splits=200)
    assert noise["rho"] < 0.5 and noise["reading"] == "poor"
    assert stats.split_half({"a": [1, 2, 3, 4], "b": [1, 2, 3, 4]}) is None


def test_sheet_scores_and_task_score():
    scores = report.sheet_scores(SHEET.format("5 (auto)", "N/A", ""))
    assert scores == {"Bugs found": 5.0, "Following the statement": "N/A", "Severity": ""}
    assert report.task_score(scores) is None   # a criterion still blank
    assert report.task_score(report.sheet_scores(SHEET.format("5 (auto)", "N/A", "8 (judge)"))) == 6.5


def _run(root: Path, contestant: str, rep: int, grades: tuple, judge: tuple | None = None) -> None:
    run = root / "c9" / "T3-pr-review" / contestant / f"r{rep}"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"status": "ok"}))
    (run / "grade.md").write_text(SHEET.format(*grades))
    (run / "metrics.json").write_text(json.dumps({"wall_s": 120, "usd_total": 0.5, "gpu_energy_wh": None,
                                                  "by_model": {"m": {"output": 2000}, "n": {"output": 500}}}))
    if judge:
        passes = {str(n): {"judgement": {"criteria": {"Truth": {"score": s}}}} for n, s in enumerate(judge, 1)}
        (run / "judge.json").write_text(json.dumps({"passes": passes}))


def _campaign(root: Path) -> None:
    for rep, (grades, judge) in enumerate([(("9", "10", "8"), (6, 7)), (("1", "10", "N/A"), (3, 3)),
                                           (("5", "10", "6"), (8, 9))], 1):
        _run(root, "spread", rep, grades, judge)
    for rep in (1, 2):
        _run(root, "steady", rep, ("8 (auto)", "8 (auto)", "8 (judge)"))
    _run(root, "steady", 3, ("8 (auto)", "8 (auto)", ""))


def test_campaign_stats(tmp_path):
    _campaign(tmp_path)
    t = report.campaign_stats("c9", 0.2, tmp_path)["tasks"]["T3-pr-review"]
    assert t["criteria"] == ["Bugs found", "Following the statement", "Severity"]
    assert list(t["contestants"]) == ["steady", "spread"]   # best mean first
    steady, spread = t["contestants"]["steady"], t["contestants"]["spread"]
    assert steady["run_scores"] == {"r1": 8.0, "r2": 8.0, "r3": None} and steady["task_score"]["sd"] == 0
    assert spread["run_scores"] == {"r1": 9.0, "r2": 5.5, "r3": 7.0} and spread["task_score"]["min"] == 5.5
    assert spread["criteria"]["Severity"]["n"] == 2 and steady["criteria"]["Severity"]["n"] == 2
    assert spread["figures"]["time_min"]["mean"] == 2.0 and spread["figures"]["output_tokens"]["mean"] == 2500
    assert spread["figures"]["electricity_eur"] is None
    assert t["ranking"] is None   # three runs each, two contestants
    assert t["judge"]["Truth"]["n"] == 3 and t["judge"]["Truth"]["rho"] == pytest.approx(1)


def test_build_report_writes_the_page(tmp_path):
    pytest.importorskip("plotly")
    _campaign(tmp_path)
    report.build_report("c9", 0.2, tmp_path)
    page = (tmp_path / "c9" / "report" / "index.html").read_text()
    assert "Campaign c9" in page and "spread" in page and "ρ between the passes" in page
    assert json.loads((tmp_path / "c9" / "report" / "report.json").read_text())["campaign"] == "c9"
