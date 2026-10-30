"""Campaign plan: the ordered list of runs, without executing anything (ARCHITECTURE §5)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from bench.config import Contestant, Task


@dataclass(frozen=True)
class RunSpec:
    campaign: str
    task: str
    contestant: str
    rep: int
    exclusive: bool

    @property
    def run_id(self) -> str:
        return f"{self.campaign}_{self.task}_{self.contestant}_r{self.rep}"


def plan_runs(
    campaign: str,
    contestants: dict[str, Contestant],
    tasks: dict[str, Task],
    reps: int,
    seed: int = 0,
) -> list[RunSpec]:
    """Seeded order. Exclusive runs (Strata) form a single block at the end of the campaign, for a
    single model load. Elsewhere, two consecutive runs of the same contestant are avoided, so that
    the prompt cache is uniformly cold."""
    rng = random.Random(seed)
    runs = [
        RunSpec(campaign, t, c.id, r, c.exclusive)
        for t in tasks
        for c in contestants.values()
        for r in range(1, reps + 1)
    ]
    shared = [r for r in runs if not r.exclusive]
    exclusive = [r for r in runs if r.exclusive]
    rng.shuffle(shared)
    rng.shuffle(exclusive)
    return _spread(shared) + _spread(exclusive)


def _spread(runs: list[RunSpec]) -> list[RunSpec]:
    """Reorders so that neighbouring runs have different contestants whenever possible."""
    pending, ordered = list(runs), []
    while pending:
        last = ordered[-1].contestant if ordered else None
        pick = next((r for r in pending if r.contestant != last), pending[0])
        pending.remove(pick)
        ordered.append(pick)
    return ordered
