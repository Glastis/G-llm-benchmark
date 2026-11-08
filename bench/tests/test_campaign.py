from bench.campaign import plan_runs
from bench.config import load_contestants, load_tasks

CONTESTANTS = load_contestants()
TASKS = load_tasks()


def test_every_couple_runs_reps_times():
    runs = plan_runs("c01", CONTESTANTS, TASKS, reps=3)
    assert len(runs) == len(CONTESTANTS) * len(TASKS) * 3
    assert len({r.run_id for r in runs}) == len(runs)


def test_exclusive_runs_form_one_block_at_the_start():
    runs = plan_runs("c01", CONTESTANTS, TASKS, reps=3)
    flags = [r.exclusive for r in runs]
    last = flags.index(False)
    assert all(flags[:last]) and not any(flags[last:])
    assert {r.contestant for r in runs[:last]} == {"strata_coder-low", "strata_coder-medium", "strata_coder-high", "opus-strata", "sonnet-strata"}


def test_neighbours_differ_outside_the_last_runs():
    runs = [r for r in plan_runs("c01", CONTESTANTS, TASKS, reps=3) if not r.exclusive]
    same = sum(a.contestant == b.contestant for a, b in zip(runs, runs[1:]))
    assert same <= 2


def test_order_is_seeded():
    assert plan_runs("c01", CONTESTANTS, TASKS, 3, seed=7) == plan_runs("c01", CONTESTANTS, TASKS, 3, seed=7)
