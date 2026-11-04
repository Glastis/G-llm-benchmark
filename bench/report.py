"""HTML report of a campaign (ARCHITECTURE §10, PLAN §10.33), in runs/<campaign>/report/: index.html,
and report.json with every figure.

Per task and per contestant, over its finished runs: the task score, the unweighted mean of a run's
criteria with the N/A left out, counted once every criterion of the run has its grade; each criterion;
time, cost, output tokens and the electricity of the Strata GPU. Each as n, mean and its 95 %
confidence interval, median, standard deviation, min and max. Per task, how sure the ranking of the
contestants is (split-half ρ) and how steady the judge is on each criterion (ρ between its two passes).
The grades come from each run's grade.md, where `bench grade` and `bench judge` wrote them.
"""

from __future__ import annotations

import html
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

from bench import stats
from bench.grade import finished_runs
from bench.judge import REPORT as JUDGE_REPORT
from bench.runner import RUNS_ROOT

MARKS = re.compile(r"\s*\((auto|judge)\)$")
NA, BLANK = "N/A", ""
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
RUN, MEDIAN = "#2a78d6", "#eb6834"
ROW_PX = 44
FIGURES = {   # per-run figure: column title, how a value reads
    "time_min": ("Time (min)", lambda v: f"{v:.1f}"),
    "usd": ("Cost ($ API equivalent)", lambda v: f"{v:.3f}"),
    "output_tokens": ("Output tokens", lambda v: f"{v / 1000:.1f}k"),
    "electricity_eur": ("Electricity (€, GPU only)", lambda v: f"{v:.3f}"),
}


def sheet_scores(text: str) -> dict[str, float | str]:
    """The scores of a grade.md, in the order of the sheet: a number, N/A or blank. A criterion is a row
    of a table whose second column is the score."""
    scores, scored = {}, False
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if not line.startswith("|") or len(cells) < 4:
            scored = False
        elif cells[2].startswith("Score"):
            scored = True
        elif scored and not set(cells[1]) <= {"-"}:
            value = MARKS.sub("", cells[2])
            try:
                scores[cells[1]] = NA if value == NA else float(value)
            except ValueError:
                scores[cells[1]] = BLANK
    return scores


def task_score(scores: dict[str, float | str]) -> float | None:
    """The mean of the run's criteria, N/A left out; None while a criterion is blank."""
    values = [v for v in scores.values() if isinstance(v, float)]
    return None if BLANK in scores.values() or not values else statistics.fmean(values)


def _json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def figures(m: dict | None, eur_per_kwh: float | None) -> dict[str, float | None]:
    m = m or {}
    wh = m.get("gpu_energy_wh")
    return {"time_min": m["wall_s"] / 60 if m.get("wall_s") is not None else None,
            "usd": m.get("usd_total"),
            "output_tokens": sum(u.get("output", 0) for u in m["by_model"].values()) if m.get("by_model") else None,
            "electricity_eur": wh / 1000 * eur_per_kwh if wh is not None and eur_per_kwh else None}


def load_runs(campaign: str, eur_per_kwh: float | None, runs_root: Path = RUNS_ROOT) -> list[dict]:
    runs = []
    for run_dir in finished_runs(campaign, runs_root):
        sheet = run_dir / "grade.md"
        runs.append({"task": run_dir.parent.parent.name, "contestant": run_dir.parent.name, "rep": run_dir.name,
                     "scores": sheet_scores(sheet.read_text(encoding="utf-8")) if sheet.is_file() else {},
                     "figures": figures(_json(run_dir / "metrics.json"), eur_per_kwh),
                     "judge": _json(run_dir / JUDGE_REPORT)})
    return runs


def _passed(judge: dict | None, number: str) -> dict:
    return ((((judge or {}).get("passes") or {}).get(number) or {}).get("judgement") or {}).get("criteria") or {}


def judge_pairs(runs: list[dict]) -> dict[str, list[tuple[float, float]]]:
    """Per criterion, the grades of the judge's first and second pass on each run judged twice."""
    pairs = defaultdict(list)
    for r in runs:
        first, second = _passed(r["judge"], "1"), _passed(r["judge"], "2")
        for name in (n for n in first if n in second):
            pairs[name].append((first[name]["score"], second[name]["score"]))
    return dict(pairs)


def contestant_stats(mine: list[dict], criteria: list[str]) -> dict:
    run_scores = {r["rep"]: task_score(r["scores"]) for r in mine}
    graded = [s for s in run_scores.values() if s is not None]
    return {"runs": len(mine), "run_scores": run_scores,
            "task_score": stats.describe(graded, 0, 10),
            "criteria": {c: stats.describe([v for r in mine if isinstance(v := r["scores"].get(c), float)], 0, 10)
                         for c in criteria},
            "figures": {k: stats.describe([v for r in mine if (v := r["figures"][k]) is not None]) for k in FIGURES}}


def task_stats(runs: list[dict]) -> dict:
    criteria = list(dict.fromkeys(c for r in runs for c in r["scores"]))
    by_contestant = defaultdict(list)
    for r in runs:
        by_contestant[r["contestant"]].append(r)
    rows = {c: contestant_stats(mine, criteria) for c, mine in by_contestant.items()}
    order = sorted(rows, key=lambda c: (rows[c]["task_score"] is None, -(rows[c]["task_score"] or {}).get("mean", 0), c))
    graded = {c: [s for s in rows[c]["run_scores"].values() if s is not None] for c in order}
    return {"criteria": criteria, "contestants": {c: rows[c] for c in order},
            "ranking": stats.split_half(graded),
            "judge": {name: stats.agreement(p) for name, p in judge_pairs(runs).items()}}


def campaign_stats(campaign: str, eur_per_kwh: float | None, runs_root: Path = RUNS_ROOT) -> dict:
    by_task = defaultdict(list)
    for r in load_runs(campaign, eur_per_kwh, runs_root):
        by_task[r["task"]].append(r)
    return {"campaign": campaign, "tasks": {t: task_stats(runs) for t, runs in sorted(by_task.items())}}


def build_report(campaign: str, eur_per_kwh: float | None, runs_root: Path = RUNS_ROOT) -> dict:
    """Writes index.html and report.json in runs/<campaign>/report/, and returns the figures."""
    report = campaign_stats(campaign, eur_per_kwh, runs_root)
    out = runs_root / campaign / "report"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "index.html").write_text(render(report), encoding="utf-8")
    return report


# --- HTML ---

def num(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def interval(s: dict, show=num) -> str:
    return f"{show(s['ci'][0])}–{show(s['ci'][1])}" if s["ci"] else "—"


def cell(s: dict | None, show=num) -> str:
    """One statistic in a table cell: the mean and the median, then the interval, σ, min–max and n."""
    if not s:
        return "—"
    extra = [f"CI {interval(s, show)}" if s["ci"] else None, f"σ {show(s['sd'])}" if s["sd"] is not None else None,
             f"{show(s['min'])}–{show(s['max'])}", f"n {s['n']}"]
    return (f"<b>{show(s['mean'])}</b> <span class=m>med {show(s['median'])}</span>"
            f"<br><small>{' · '.join(f'<span>{e}</span>' for e in extra if e)}</small>")


def score_row(contestant: str, row: dict) -> list[str]:
    graded = f"{sum(s is not None for s in row['run_scores'].values())}/{row['runs']}"
    if not (s := row["task_score"]):
        return [contestant, graded, *["—"] * 5]
    return [contestant, graded, num(s["mean"]), interval(s), num(s["median"]), num(s["sd"]), f"{num(s['min'])}–{num(s['max'])}"]


def table(head: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


def chart(t: dict) -> str:
    """Each run's task score as a dot, the mean with its 95 % interval, the median as a tick; best first."""
    import plotly.graph_objects as go

    order = [c for c, row in t["contestants"].items() if row["task_score"]]
    if not order:
        return "<p class=note>No run graded on every criterion yet.</p>"
    y = {c: len(order) - 1 - i for i, c in enumerate(order)}
    xs, ys, tips = [], [], []
    for c in order:
        done = [(rep, s) for rep, s in t["contestants"][c]["run_scores"].items() if s is not None]
        step = min(0.12, 0.5 / max(len(done) - 1, 1))
        for k, (rep, s) in enumerate(done):
            xs.append(s)
            ys.append(y[c] + step * (k - (len(done) - 1) / 2))
            tips.append(f"{c} {rep}: {s:.1f}")
    st = [t["contestants"][c]["task_score"] for c in order]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name="run", hovertext=tips, hoverinfo="text",
                             marker={"size": 9, "color": RUN, "opacity": 0.8, "line": {"width": 2, "color": SURFACE}}))
    fig.add_trace(go.Scatter(
        x=[s["mean"] for s in st], y=[y[c] for c in order], mode="markers", name="mean ± 95 % CI", hoverinfo="text",
        hovertext=[f"{c}: mean {num(s['mean'])}, CI {interval(s)}, median {num(s['median'])}, σ {num(s['sd'])}, n {s['n']}"
                   for c, s in zip(order, st)],
        marker={"symbol": "diamond", "size": 11, "color": INK},
        error_x={"type": "data", "symmetric": False, "color": INK, "thickness": 2, "width": 6,
                 "array": [s["ci"][1] - s["mean"] if s["ci"] else 0 for s in st],
                 "arrayminus": [s["mean"] - s["ci"][0] if s["ci"] else 0 for s in st]}))
    fig.add_trace(go.Scatter(x=[s["median"] for s in st], y=[y[c] for c in order], mode="markers", name="median",
                             hoverinfo="skip", marker={"symbol": "line-ns", "size": 18, "line": {"width": 3, "color": MEDIAN}}))
    fig.update_layout(
        height=ROW_PX * len(order) + 110, margin={"l": 10, "r": 10, "t": 40, "b": 50},
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font={"family": "system-ui, sans-serif", "color": MUTED, "size": 13},
        legend={"orientation": "h", "x": 0, "y": 1, "yanchor": "bottom"},
        xaxis={"title": "Task score /10", "range": [-0.3, 10.3], "dtick": 1, "gridcolor": GRID, "zeroline": False},
        yaxis={"tickvals": list(y.values()), "ticktext": order, "range": [-0.6, len(order) - 0.4],
               "showgrid": False, "zeroline": False, "tickfont": {"color": INK}})
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})


def ranking(r: dict | None) -> str:
    if not r:
        return (f"<p class=note>Ranking: n/a, it needs {stats.SPLIT_MIN_CONTESTANTS} contestants with at least "
                f"{stats.SPLIT_MIN_RUNS} graded runs.</p>")
    left = f"; left out, fewer than {stats.SPLIT_MIN_RUNS} graded runs: {', '.join(r['left_out'])}" if r["left_out"] else ""
    return (f"<p class=note>Ranking: split-half ρ <b>{r['rho']:.2f}</b>, {r['reading']} "
            f"(ρ between halves {r['rho_half']:.2f}, {r['contestants']} contestants, at least {r['min_runs']} runs each{left}).</p>")


def judge_table(judge: dict) -> str:
    if not judge:
        return ""
    rows = [[name, str(a["n"]), num(a["rho"], 2), num(a["gap"]), a["reading"]] for name, a in judge.items()]
    return "<h3>The judge</h3>" + table(["Criterion", "Runs judged twice", "ρ between the passes", "Mean gap", "Reading"], rows)


def section(task: str, t: dict) -> str:
    rows = t["contestants"].items()
    parts = [f"<section><h2>{html.escape(task)}</h2>"]
    if t["criteria"]:
        parts += [chart(t), "<h3>Task score</h3>",
                  table(["Contestant", "Graded", "Mean", "95 % CI", "Median", "σ", "Min–max"], [score_row(c, row) for c, row in rows]),
                  ranking(t["ranking"]), "<h3>Criteria</h3>",
                  table(["Contestant", *t["criteria"]], [[c, *(cell(row["criteria"][k]) for k in t["criteria"])] for c, row in rows]),
                  judge_table(t["judge"])]
    shown = [k for k in FIGURES if any(row["figures"][k] for _, row in rows)]
    parts += ["<h3>Time and cost</h3>", table(["Contestant", *(FIGURES[k][0] for k in shown)],
                                              [[c, *(cell(row["figures"][k], FIGURES[k][1]) for k in shown)] for c, row in rows]),
              "</section>"]
    return "\n".join(parts)


CSS = f"""
:root {{ color-scheme: light; }}
body {{ background: {SURFACE}; color: {INK}; font: 14px/1.45 system-ui, sans-serif; margin: 0 auto; max-width: 1200px; padding: 16px; }}
h1 {{ font-size: 24px; }} h2 {{ margin-top: 48px; border-bottom: 1px solid {GRID}; }} h3 {{ margin-top: 24px; }}
.note, small, .m {{ color: {MUTED}; }}
.wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; font-variant-numeric: tabular-nums; margin: 8px 0; }}
th, td {{ border-bottom: 1px solid {GRID}; padding: 6px 10px; text-align: left; vertical-align: top; }}
th {{ font-weight: 600; }}
td:first-child, small span {{ white-space: nowrap; }}
"""

HOW_TO_READ = """<p class=note>Per task and contestant, over its finished runs. A run's <b>task score</b> is the
mean of its criteria, N/A left out, counted once every criterion has its grade. The <b>mean</b> comes with its
<b>95 % confidence interval</b> (Student): how precisely the mean is known, narrower with more runs; when two
intervals overlap widely, the gap between the means is not shown. <b>σ</b> is how much the runs differ from each
other, the contestant's steadiness; more runs do not shrink it. The <b>median</b> is the middle run, <b>min – max</b>
the worst and best. The <b>split-half ρ</b> says whether the ranking of the contestants would hold with another set
of runs, the judge's <b>ρ between the passes</b> whether it ranks the runs in the same order twice. ρ reads
excellent from 0.9, good from 0.75, moderate from 0.5, poor below.</p>"""


def render(report: dict) -> str:
    from plotly.offline import get_plotlyjs

    body = "\n".join(section(task, t) for task, t in report["tasks"].items()) or "<p>No finished run.</p>"
    body = body.replace("<table>", "<div class=wrap><table>").replace("</table>", "</table></div>")
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width, initial-scale=1'><title>Campaign {html.escape(report['campaign'])}</title>"
            f"<style>{CSS}</style><script>{get_plotlyjs()}</script></head><body>"
            f"<h1>Campaign {html.escape(report['campaign'])}</h1>{HOW_TO_READ}{body}</body></html>")
