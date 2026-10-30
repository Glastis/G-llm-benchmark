"""T1 scenario generation: random scenarios for the cross-check and the hidden set, and the performance
scenario. Generation is seeded, so every file can be rebuilt identically."""

from __future__ import annotations

import random


def random_scenario(seed: int, *, floors: int | None = None, elevators: int | None = None,
                    passengers: int | None = None, span: int | None = None, start: bool | None = None) -> str:
    rng = random.Random(seed)
    floors = floors or rng.randint(2, 20)
    elevators = elevators or rng.randint(1, 4)
    capacity = rng.randint(1, 8)
    travel, door = rng.randint(1, 5), rng.randint(1, 6)
    count = rng.randint(0, 60) if passengers is None else passengers
    span = span or rng.choice([10, 50, 200, 1000])
    lines = [f"# random scenario, seed {seed}"]
    header = [f"floors {floors}", f"elevators {elevators}", f"capacity {capacity}", f"travel {travel}", f"door {door}"]
    if start if start is not None else rng.random() < 0.5:
        header.append("start " + " ".join(str(rng.randrange(floors)) for _ in range(elevators)))
    rng.shuffle(header)
    lines += header
    ids = rng.sample(range(count * 3 + 1), count)
    rows = []
    for pid in ids:
        src = rng.randrange(floors)
        dst = rng.choice([f for f in range(floors) if f != src])
        rows.append(f"passenger {pid} {rng.randint(0, span)} {src} {dst}")
    rng.shuffle(rows)
    return "\n".join(lines + rows) + "\n"


def perf_scenario(seed: int = 2026) -> str:
    """200,000 passengers, 16 elevators, 100 floors. Arrivals come in bursts separated by huge gaps,
    up to 10^15: a tick-by-tick clock cannot finish."""
    rng = random.Random(seed)
    lines = ["floors 100", "elevators 16", "capacity 12", "travel 2", "door 5"]
    t, pid = 0, 0
    while pid < 200_000:
        t += rng.randint(1, 1_000_000_000_000)
        for _ in range(rng.randint(50, 400)):
            if pid == 200_000:
                break
            src = rng.randrange(100)
            dst = rng.choice([0, rng.randrange(100)]) if src else rng.randrange(1, 100)
            if dst == src:
                dst = (src + 1) % 100
            lines.append(f"passenger {pid} {t + rng.randint(0, 3_000)} {src} {dst}")
            pid += 1
    return "\n".join(lines) + "\n"
