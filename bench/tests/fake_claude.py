#!/usr/bin/env python3
"""Fake `claude` to test the runner without launching an agent. The behaviour is chosen by a word
in the task statement: MODE=ok, MODE=sleep or MODE=quota.

Like the real one, it prints a stream-json whose usage is a snapshot taken while streaming
(output tokens undercounted), and writes the final usage to a session journal in
$CLAUDE_CONFIG_DIR/projects/."""

import json
import os
import sys
import time
from pathlib import Path

if "--version" in sys.argv:
    print("9.9.9 (fake)")
    sys.exit(0)

prompt = sys.stdin.read()   # like the runner's `claude -p`, the statement comes on stdin
emit = lambda event: print(json.dumps(event), flush=True)


def usage(output, **extra):
    return {"input_tokens": extra.get("input", 0), "output_tokens": output,
            "cache_read_input_tokens": extra.get("cache_read", 0),
            "cache_creation_input_tokens": extra.get("cache_write", 0),
            "cache_creation": {"ephemeral_5m_input_tokens": extra.get("cache_write", 0), "ephemeral_1h_input_tokens": 0}}


def message(mid, model, u, content, parent=None):
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"id": mid, "model": model, "usage": u, "content": content}}


limits = {"type": "rate_limit_event", "rate_limit_info": {
    "status": "rejected" if "MODE=quota" in prompt else "allowed",
    "unifiedWindows": {"five_hour": {"utilization": 0.25}, "seven_day": {"utilization": 0.5}}}}

if "MODE=sleep" in prompt:
    time.sleep(30)
elif "MODE=quota" in prompt:
    emit(limits)
    emit({"type": "result", "subtype": "error", "is_error": True, "result": "API error"})
    sys.exit(1)
else:
    if "_judge/judgement.json" in prompt:   # the blind judge
        names = ["Truth", "Completeness"] if "Truth" in prompt else ["Readability", "Architecture", "Factoring", "Cleanliness", "Safety"]
        seen = "\n".join(p.read_text(errors="replace") for p in Path(".").rglob("*") if p.is_file())
        Path("_judge/judgement.json").write_text(json.dumps({"criteria": {n: {"score": 7 if "MODE=judge-low" not in seen else 3,
                                                                                "reasons": "fake"} for n in names}}))
    else:
        Path("hello.txt").write_text("hello\n")
    opus = dict(input=10, cache_read=5000, cache_write=1000)
    write = [{"type": "text", "text": "writing"}], [{"type": "tool_use", "id": "tu1", "name": "Write", "input": {}}]
    read = [{"type": "tool_use", "id": "tu3", "name": "Read", "input": {}}]
    # Stream-json: one message over two lines (same id), with snapshot usage.
    emit({"type": "system", "subtype": "init", "model": "claude-opus-5-5"})
    emit(message("m1", "claude-opus-5-5", usage(20, **opus), write[0]))
    emit(message("m1", "claude-opus-5-5", usage(20, **opus), write[1]))
    emit(limits)
    emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1", "is_error": True}]}})
    emit(message("m2", "claude-haiku-5-5", usage(10, input=3000), read, parent="tu2"))
    emit({"type": "result", "subtype": "success", "is_error": False, "result": "done",
          "duration_ms": 1234, "num_turns": 3, "total_cost_usd": 0.01039,
          "modelUsage": {"claude-opus-5-5": {"outputTokens": 200, "costUSD": 0.01004},
                         "claude-haiku-5-5": {"outputTokens": 100, "costUSD": 0.00035}}})
    # Session journals: the same messages with their final usage, the subagent in its own file.
    session = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "ws" / "session"
    (session / "subagents").mkdir(parents=True)
    session.with_suffix(".jsonl").write_text(json.dumps(message("m1", "claude-opus-5-5", usage(200, **opus), write[0] + write[1])) + "\n")
    (session / "subagents" / "agent-1.jsonl").write_text(json.dumps(message("m2", "claude-haiku-5-5", usage(100, input=3000), read, parent="tu2")) + "\n")
