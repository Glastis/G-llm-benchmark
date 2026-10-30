"""From raw transcripts to metrics.json (ARCHITECTURE §8).

Token usage comes from the session journals Claude Code writes in the run's CLAUDE_CONFIG_DIR
(claude-home/projects/**.jsonl): they carry each message's final usage, for the main session,
its subagents and every Strata worker session. The stream-json printed on stdout only carries a
snapshot taken while the message streams, so its `output_tokens` undercounts (hidden thinking is
missing): it is used for events only (tool calls, result, rate limits), and as a fallback.

A message spans several lines, one per content block, repeating the same `message.id`: usage is
deduplicated by id, keeping the largest output count. Each subagent call has its own journal under
<session>/subagents/; the stream-json only shows part of a subagent's messages.
"""

from __future__ import annotations

import json
import os
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from bench.config import ROOT, Bundle, Pricing
from bench.energy import energy_wh
from bench.pricing import UnknownPrice, Usage, request_cost
from bench.runner import FINAL, RUNS_ROOT, strata_side

STRATA_PRICE = "strata"
ALERT_COST_FACTOR = 3   # alert when a run costs more than 3 × its contestant's median (PLAN §10.7)
FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
SHEET = ROOT / "GRADING-SHEET.md"


@dataclass
class StreamStats:
    requests: dict[str, tuple[str, Usage]] = field(default_factory=dict)   # message.id -> (model, usage)
    stop_reasons: dict[str, str] = field(default_factory=dict)             # message.id -> stop_reason
    tool_uses: set[str] = field(default_factory=set)
    tool_errors: set[str] = field(default_factory=set)
    subagent_messages: int = 0
    rate_limit: dict | None = None
    result: dict | None = None


def _usage(u: dict) -> Usage:
    split = u.get("cache_creation") or {}
    w5, w1 = split.get("ephemeral_5m_input_tokens") or 0, split.get("ephemeral_1h_input_tokens") or 0
    # The total is authoritative: Strata reports it with a zero split. What the split does not
    # cover counts as a 5-minute write.
    w5 += max(0, (u.get("cache_creation_input_tokens") or 0) - w5 - w1)
    return Usage(input=u.get("input_tokens") or 0, output=u.get("output_tokens") or 0,
                 cache_read=u.get("cache_read_input_tokens") or 0,
                 cache_write_5m=w5, cache_write_1h=w1)


def parse_stream(path: Path, s: StreamStats | None = None) -> StreamStats:
    """Parses a stream-json transcript or a session journal; both share the message format.
    Passing `s` merges several files, deduplicating messages across them."""
    s = s or StreamStats()
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "assistant":
            msg = event.get("message") or {}
            mid = msg.get("id") or f"{path.name}-no-id-{n}"
            usage = _usage(msg.get("usage") or {})
            known = s.requests.get(mid)
            if known is None or usage.output >= known[1].output:
                s.requests[mid] = (msg.get("model") or "?", usage)
                if msg.get("stop_reason"):
                    s.stop_reasons[mid] = msg["stop_reason"]
            if known is None and event.get("parent_tool_use_id"):
                s.subagent_messages += 1
            s.tool_uses |= {b["id"] for b in msg.get("content") or [] if b.get("type") == "tool_use" and "id" in b}
        elif kind == "user":
            content = (event.get("message") or {}).get("content")
            if isinstance(content, list):
                s.tool_errors |= {b.get("tool_use_id") for b in content
                                  if b.get("type") == "tool_result" and b.get("is_error")}
        elif kind == "rate_limit_event":
            s.rate_limit = event.get("rate_limit_info")
        elif kind == "result":
            s.result = event
    return s


def session_journals(run_dir: Path) -> list[Path]:
    projects = run_dir / "claude-home" / "projects"
    return sorted(projects.rglob("*.jsonl")) if projects.is_dir() else []


def _empty_row() -> dict:
    return dict.fromkeys((*FIELDS, "requests", "usd"), 0)


def metrics_for(run_dir: Path, bundle: Bundle) -> dict:
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    c = bundle.contestants[record["contestant"]]
    side = strata_side(c, bundle)
    main = parse_stream(run_dir / "transcript.jsonl")
    workers = sorted((run_dir / "workers").glob("*.jsonl")) if (run_dir / "workers").is_dir() else []
    tool_uses, tool_errors = set(main.tool_uses), set(main.tool_errors)
    for path in workers:
        w = parse_stream(path)
        tool_uses |= {f"{path.stem}:{t}" for t in w.tool_uses}
        tool_errors |= {f"{path.stem}:{t}" for t in w.tool_errors}

    warnings = []
    usage = StreamStats()
    journals = session_journals(run_dir)
    for path in journals:
        parse_stream(path, usage)
    if not journals:
        warnings.append("no session journal: usage taken from the stream-json, output tokens undercounted")
        for path in [run_dir / "transcript.jsonl", *workers]:
            parse_stream(path, usage)
    subagent_journals = [path for path in journals if "subagents" in path.parts]
    subagent_requests = set().union(*(parse_stream(path).requests for path in subagent_journals))

    by_model: dict[str, dict] = defaultdict(_empty_row)
    unpriced: set[str] = set()
    for model, u in usage.requests.values():
        row = by_model[model]
        for key in FIELDS:
            row[key] += getattr(u, key)
        row["requests"] += 1
        # Strata reports its own model name (for example qwen…-coder-iq1_m): it is priced at $0.
        price_as = model if model in bundle.pricing.models else (STRATA_PRICE if side else None)
        try:
            row["usd"] += request_cost(price_as or model, u, bundle.pricing)
        except UnknownPrice:
            unpriced.add(model)
    for row in by_model.values():
        row["usd"] = round(row["usd"], 6)

    if unpriced:
        warnings.append(f"models without a price (incomplete cost): {', '.join(sorted(unpriced))}")
    if main.result is None:
        warnings.append("no result event in the transcript")
    reported = (main.result or {}).get("modelUsage") or {}
    warnings += _check_against_claude_code(by_model, reported, bundle.pricing, strata_main=c.backend == "strata")

    return {
        "run_id": record["run_id"],
        "status": record["status"],
        "wall_s": record["wall_s"],
        "duration_ms": (main.result or {}).get("duration_ms"),
        "turns": (main.result or {}).get("num_turns"),
        "tool_calls": len(tool_uses),
        "tool_errors": len(tool_errors),
        "worker_calls": len(workers),
        "subagent_calls": len(subagent_journals) if journals else None,
        "subagent_requests": len(subagent_requests) if journals else main.subagent_messages,
        "by_model": dict(by_model),
        "usd_total": None if unpriced else round(sum(r["usd"] for r in by_model.values()), 6),
        "gpu_energy_wh": energy_wh(run_dir / "energy.csv") if side else None,
        "truncated_responses": sum(1 for reason in usage.stop_reasons.values() if reason == "max_tokens"),
        "strata_server": strata_log_stats(run_dir / "strata-server.log"),
        "subscription": _subscription(main.rate_limit),
        "reported": {"model_usage": reported or None, "total_cost_usd": (main.result or {}).get("total_cost_usd")},
        "warnings": warnings,
    }


TOKEN_CHECKS = {"input": "inputTokens", "output": "outputTokens", "cache_read": "cacheReadInputTokens",
                "cache_write": "cacheCreationInputTokens"}


def _check_against_claude_code(by_model: dict, reported: dict, pricing: Pricing, strata_main: bool) -> list[str]:
    """Claude Code counts tokens per model for the main session, and prices Anthropic models at list
    price. Our figures must match; a gap means a counting or pricing problem. Strata renames its
    model (`strata` for Claude Code, its own name in the journals): for the Strata contestant, its
    single reported model is compared with all our rows."""
    warnings = []
    for model, theirs in reported.items():
        if model in by_model:
            ours = by_model[model]
        elif strata_main and len(reported) == 1:
            ours = {key: sum(row[key] for row in by_model.values()) for key in (*FIELDS, "usd")}
        else:
            warnings.append(f"model seen by Claude Code but not in the journals: {model}")
            continue
        ours = {**ours, "cache_write": ours["cache_write_5m"] + ours["cache_write_1h"]}
        for key, their_key in TOKEN_CHECKS.items():
            if their_key in theirs and ours[key] != theirs[their_key]:
                warnings.append(f"{model}: {ours[key]} {key} tokens counted, Claude Code reports {theirs[their_key]}")
        cost = theirs.get("costUSD")
        if model in pricing.models and model != STRATA_PRICE and cost is not None \
                and abs(ours["usd"] - cost) > max(1e-6, 0.01 * cost):
            warnings.append(f"{model}: cost {ours['usd']:.6f} $ computed, Claude Code reports {cost:.6f} $")
    return warnings


STRATA_THINKING = re.compile(r"\[strata\] thinking: (\d+) of (?:budget \d+ \(max (\d+)\)|max (\d+)) tokens")
STRATA_DONE = re.compile(r"\[strata\] done: (\d+) tokens in [\d.]+ s \(([\d.]+) tok/s\) \((\w+), cancel=")


def strata_log_stats(path: Path) -> dict | None:
    """Per-run totals from the Strata server log excerpt. Each response logs its thinking progress,
    then one `done` line with its total tokens, throughput and finish reason (`length` = cut at the
    output cap)."""
    if not path.is_file():
        return None
    responses, thinking, total, rates, reasons, budget_hits, cap = 0, 0, 0, [], {}, 0, None
    current = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if m := STRATA_THINKING.search(line):
            current = int(m.group(1))
            cap = int(m.group(2) or m.group(3))
        elif "thinking budget reached" in line or "reached max tokens while still thinking" in line:
            budget_hits += 1
        elif m := STRATA_DONE.search(line):
            responses += 1
            thinking += current
            total += int(m.group(1))
            rates.append(float(m.group(2)))
            reasons[m.group(3)] = reasons.get(m.group(3), 0) + 1
            current = 0
    if not responses:
        return None
    return {"responses": responses, "thinking_tokens": thinking, "total_tokens": total,
            "thinking_share": round(thinking / total, 3) if total else None, "max_tokens": cap,
            "finish_reasons": reasons, "thinking_cut": budget_hits,
            "median_tok_s": statistics.median(rates)}


def _subscription(info: dict | None) -> dict | None:
    """Subscription utilization seen at the end of the run (`rate_limit_event`)."""
    if not info:
        return None
    windows = info.get("unifiedWindows") or {}
    return {"status": info.get("status"),
            **{f"{name}_utilization": w.get("utilization") for name, w in windows.items()}}


def write_grade_sheet(run_dir: Path, m: dict, pricing: Pricing, template: Path = SHEET) -> None:
    """Drops the blank grading sheet into the run's folder as grade.md, with what the harness
    already knows filled in. An existing sheet holds the author's grades: it is never touched."""
    sheet = run_dir / "grade.md"
    if sheet.exists():
        return
    wh, rate = m["gpu_energy_wh"], pricing.electricity_eur_per_kwh
    usd = None if m["usd_total"] is None else f"{m['usd_total']:.4f} $"
    eur = f"{wh / 1000 * rate:.4f} €" if wh is not None and rate else None
    filled = {
        "Task": run_dir.parent.parent.name,
        "Contestant": run_dir.parent.name,
        "Rep": run_dir.name.removeprefix("r"),
        "Time (s)": f"{m['wall_s']:.0f}",
        "Cost ($ API equivalent · € electricity, Strata only)": " · ".join(filter(None, (usd, eur))),
    }
    text = template.read_text(encoding="utf-8")
    for label, value in filled.items():
        text = text.replace(f"| {label} | |", f"| {label} | {value} |")
    text = text.replace("](GRADING.md)", f"]({os.path.relpath(ROOT / 'GRADING.md', run_dir)})")
    sheet.write_text(text, encoding="utf-8")


def collect(campaign: str, bundle: Bundle, runs_root: Path = RUNS_ROOT) -> list[dict]:
    """Writes metrics.json for every finished run of the campaign, then flags runs that cost more
    than `ALERT_COST_FACTOR` × their contestant's median (PLAN §10.7). Tasks with `grading_sheet`
    also get a grading sheet per finished run."""
    all_metrics = []
    for record in sorted((runs_root / campaign).glob("*/*/r*/run.json")):
        m = metrics_for(record.parent, bundle)
        all_metrics.append((record.parent, m))
    by_contestant = defaultdict(list)
    for run_dir, m in all_metrics:
        if m["usd_total"] is not None:
            by_contestant[run_dir.parent.name].append(m["usd_total"])
    for run_dir, m in all_metrics:
        costs = by_contestant[run_dir.parent.name]
        median = statistics.median(costs) if costs else None
        m["cost_alert"] = bool(median and m["usd_total"] is not None and m["usd_total"] > ALERT_COST_FACTOR * median)
        (run_dir / "metrics.json").write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        task = bundle.tasks.get(run_dir.parent.parent.name)
        if task and task.grading_sheet and m["status"] in FINAL:
            write_grade_sheet(run_dir, m, bundle.pricing)
    return [m for _, m in all_metrics]
