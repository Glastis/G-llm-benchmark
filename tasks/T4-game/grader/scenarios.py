"""T4 scenarios: seeded random action sequences, turned into test-mode scripts and their expected
output. An action is ["place", type, x, y], ["bulldoze", x, y], ["step", n] or ["reset"]."""

from __future__ import annotations

import random

from rules import SPECS, WIDTH, HEIGHT, City


def random_actions(seed: int, length: int = 60) -> list[list]:
    """A city-like sequence: a few road lines, then mostly buildings placed along them, with
    invalid placements, bulldozing and steps mixed in."""
    rng = random.Random(seed)
    actions: list[list] = []
    rows = rng.sample(range(2, HEIGHT - 2), rng.randint(1, 3))
    for y in rows:
        actions += [["place", "road", x, y] for x in range(rng.randrange(6), rng.randrange(14, WIDTH + 1))]
    if rng.random() < 0.5:
        x = rng.randrange(WIDTH)
        actions += [["place", "road", x, y] for y in range(HEIGHT)]
    weights = {"house": 8, "road": 2, "shop": 1.5, "factory": 1, "park": 2}
    for _ in range(length):
        r = rng.random()
        if r < 0.5:
            kind = rng.choices(list(weights), list(weights.values()))[0]
            h = SPECS[kind][1]
            if rng.random() < 0.8:   # along a road: just above or just below it
                road = rng.choice(rows)
                y = rng.choice([road - h, road + 1])
            else:
                y = rng.randrange(-1, HEIGHT)
            actions.append(["place", kind, rng.randrange(-1, WIDTH), y])
        elif r < 0.56:
            actions.append(["bulldoze", rng.randrange(WIDTH), rng.randrange(HEIGHT)])
        else:
            actions.append(["step", rng.choice([1, 1, 1, 2, 3, 4, 5, 10])])
    return actions


def apply(city: City, action: list) -> bool | None:
    """Applies one action; the result of a placement or a bulldozing, None for the others."""
    kind, *args = action
    if kind == "step":
        return city.step(*args)
    if kind == "reset":
        city.__init__()
        return None
    return getattr(city, kind)(*args)


def script(actions: list[list]) -> str:
    return "".join(" ".join(map(str, action)) + "\n" for action in actions)


def expected(actions: list[list]) -> list[str]:
    """The lines the test mode must write for these actions, from a new game."""
    city = City()
    return [city.line(apply(city, action)) for action in actions]


assert set(SPECS) == {"road", "house", "shop", "factory", "park"}
