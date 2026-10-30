"""Contestant served by Strata locally. Same environment as the strata-agent script, without
depending on it: the Strata installation stays outside the sandbox. This module never starts a
model, since loading one can freeze the PC for 1 to 3 minutes."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from bench.backends.anthropic import COMMON_ENV, base_argv
from bench.config import Contestant

URL = os.environ.get("STRATA_URL", "http://127.0.0.1:8080")


def health(url: str = URL) -> dict | None:
    """The /health response, or None if nothing is serving on `url`."""
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=5) as r:
            return json.load(r)
    except OSError:
        return None


class NotServing(RuntimeError):
    pass


def ensure_ready(c: Contestant, url: str = URL) -> dict:
    """Checks, outside the clock, that the right Strata model is loaded. Does not start it."""
    h = health(url)
    if not h or not h.get("loaded"):
        raise NotServing(f"no Strata model is serving on {url}: start strata-coder first")
    if c.strata_model not in h.get("model", ""):
        raise NotServing(f"Strata is serving {h.get('model')}, not {c.strata_model}: switch with strata-coder")
    return h


def server_log() -> Path | None:
    """The log of the Strata server currently serving: $STRATA_SERVER_LOG if set, otherwise the most
    recently written *.server.log in Strata's runtime folder ($XDG_STATE_HOME/strata/runtime). Only
    one model serves at a time, so the latest log is the current one."""
    if explicit := os.environ.get("STRATA_SERVER_LOG"):
        path = Path(explicit)
        return path if path.is_file() else None
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    logs = sorted((state / "strata" / "runtime").glob("*.server.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def command(c: Contestant, claude_home: Path, max_context: int, url: str = URL) -> tuple[list[str], dict[str, str]]:
    argv = base_argv(c.model, c.effort)
    env = {
        **COMMON_ENV,
        "CLAUDE_CONFIG_DIR": str(claude_home),
        "ANTHROPIC_BASE_URL": url,
        "ANTHROPIC_AUTH_TOKEN": os.environ.get("STRATA_API_KEY", "strata-local"),
        "ANTHROPIC_MODEL": c.model,
        "ANTHROPIC_SMALL_FAST_MODEL": c.model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": c.model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": c.model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": c.model,
        "CLAUDE_CODE_MAX_CONTEXT_TOKENS": str(max_context),
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(c.max_output_tokens or 4096),
    }
    return argv, env   # the runner's minimal base environment carries neither ANTHROPIC_API_KEY nor the subscription token
