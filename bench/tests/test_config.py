from bench import config
from bench.config import ROOT, load_all, load_contestants, orchestrator_preamble


def test_config_has_no_errors():
    b = load_all()
    assert b.errors == []
    assert set(b.contestants) == {"haiku", "haiku-low", "haiku-xhigh", "sonnet", "sonnet-low", "sonnet-xhigh", "strata_coder-low", "strata_coder-medium", "strata_coder-high",
                                "opus-low", "opus-haiku", "opus-strata", "sonnet-haiku", "sonnet-strata", "opus-medium", "opus-xhigh"}
    assert set(b.tasks) == {"T1-simulation", "T2-archi-summary", "T3-pr-review", "T4-game"}


def test_preamble_keeps_only_its_mechanism():
    path = ROOT / "config" / "orchestrator.md"
    sub, bash = orchestrator_preamble(path, "subagent"), orchestrator_preamble(path, "bash")
    assert "Agent tool" in sub and "bench-worker" not in sub
    assert "bench-worker" in bash and "Agent tool" not in bash
    assert sub.split("\n\n")[0] == bash.split("\n\n")[0]


def test_exclusive_follows_strata(monkeypatch):
    contestants = load_contestants()
    contestants["haiku"] = contestants["haiku"].model_copy(update={"exclusive": True})
    contestants["opus-strata"] = contestants["opus-strata"].model_copy(update={"exclusive": False})
    monkeypatch.setattr(config, "load_contestants", lambda: contestants)
    assert sorted(e for e in config.load_all().errors if "exclusive" in e) == [
        "haiku: exclusive must be false, since it does not use Strata",
        "opus-strata: exclusive must be true, since it uses Strata"]
