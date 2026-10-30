from bench.config import ROOT, load_all, orchestrator_preamble


def test_config_has_no_errors():
    b = load_all()
    assert b.errors == []
    assert set(b.contestants) == {"haiku", "haiku-low", "haiku-xhigh", "sonnet", "sonnet-low", "sonnet-xhigh", "strata", "opus-low",
                                "opus-haiku", "opus-strata", "sonnet-haiku", "sonnet-strata", "opus-medium", "opus-xhigh"}
    assert set(b.tasks) == {"T1-simulation", "T2-archi-summary", "T3-pr-review", "T4-game"}


def test_preamble_keeps_only_its_mechanism():
    path = ROOT / "config" / "orchestrator.md"
    sub, bash = orchestrator_preamble(path, "subagent"), orchestrator_preamble(path, "bash")
    assert "Agent tool" in sub and "bench-worker" not in sub
    assert "bench-worker" in bash and "Agent tool" not in bash
    assert sub.split("\n\n")[0] == bash.split("\n\n")[0]
