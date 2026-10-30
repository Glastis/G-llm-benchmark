import os

from bench.backends import strata
from bench.collect import _usage


def test_strata_cache_writes_are_kept_when_the_split_is_zero():
    # Raw usage of a Strata message from run s01_hello_strata_r1.
    u = _usage({"input_tokens": 1, "output_tokens": 471, "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 11172,
                "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}})
    assert (u.cache_write_5m, u.cache_write_1h) == (11172, 0)


def test_anthropic_cache_write_split_is_kept():
    u = _usage({"cache_creation_input_tokens": 6099,
                "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 6099}})
    assert (u.cache_write_5m, u.cache_write_1h) == (0, 6099)


def test_strata_server_log_is_the_most_recent_one(tmp_path, monkeypatch):
    runtime = tmp_path / "strata" / "runtime"
    runtime.mkdir(parents=True)
    old, new = runtime / "launch-iq3-128k.server.log", runtime / "launch-iq1_m-200k.server.log"
    old.write_text("old")
    new.write_text("new")
    os.utime(old, (1, 1))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("STRATA_SERVER_LOG", raising=False)
    assert strata.server_log() == new


def test_strata_server_log_can_be_set_explicitly(tmp_path, monkeypatch):
    log = tmp_path / "server.log"
    log.write_text("x")
    monkeypatch.setenv("STRATA_SERVER_LOG", str(log))
    assert strata.server_log() == log
