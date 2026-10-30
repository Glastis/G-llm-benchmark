"""The hidden T4 scenarios: hand-written ones aimed at one rule each, plus city-like random ones.
Each is a list of actions (see scenarios.py), run from a new game; the output is compared line by
line with the oracle's."""

from __future__ import annotations

from rules import SPECS, City
from scenarios import apply, random_actions


def _road(xs, y):
    return [["place", "road", x, y] for x in xs]


def _steps(*ns):
    return [["step", n] for n in ns]


def affordable(actions: list[list]) -> list[list]:
    """Inserts the ticks needed to afford each placement, as a patient player would."""
    city, out = City(), []
    for action in actions:
        if action[0] == "place":
            waited = 0
            while city.status == "playing" and city.money < SPECS[action[1]][2] and waited < 500:
                city.step(1)
                waited += 1
            if waited:
                out.append(["step", waited])
        apply(city, action)
        out.append(action)
    return out


HAND_WRITTEN = {
    # Connection, the one-step ramp, a house far from any road, then cutting its road.
    "connection": _road(range(0, 10), 5) + [
        ["place", "house", 0, 3], ["place", "house", 4, 6], ["place", "house", 12, 10],
    ] + _steps(1, 1, 5, 3) + [["bulldoze", 1, 5], ["step", 2], ["bulldoze", 0, 5]] + _steps(1, 4, 6),
    # Park bonus and factory smoke, alone and combined, one and two factories.
    "park-and-smoke": affordable(_road(range(0, 9), 7) + _road(range(12, 22), 7) + [
        ["place", "house", 0, 5], ["place", "park", 0, 2],          # park at distance 2: capacity 12
        ["place", "house", 5, 5], ["place", "park", 10, 1],         # park at distance 4: no bonus
        ["place", "house", 12, 8], ["place", "factory", 15, 8],     # factory at distance 2: capacity 5
        ["place", "house", 19, 5],                                  # same factory at distance 2
    ] + _steps(4, 4, 4) + [["place", "factory", 21, 8]]             # second factory: capacity 2
      + _steps(2, 3, 5) + [["place", "park", 12, 10]] + _steps(6, 6)),   # park + factory: capacity 9
    # Jobs, wages and shop customers at distance 4 and 5.
    "jobs-and-shops": affordable(_road(range(0, 20), 6) + [
        ["place", "house", 0, 4], ["place", "house", 2, 4], ["place", "house", 4, 7],
        ["place", "shop", 8, 4], ["place", "house", 14, 4], ["place", "house", 15, 7],
    ] + _steps(1, 2, 3) + [["place", "factory", 17, 3]] + _steps(1, 4, 8)),
    # Taxes on ticks 10, 20 and 30.
    "taxes": _road(range(0, 12), 3) + [["place", "house", x, 1] for x in (0, 2, 4, 6)] + _steps(9, 1, 1, 8, 1, 1, 9, 1),
    # Placement refusals: overlap, off the map, not enough money; bulldozing nothing.
    "refusals": [
        ["place", "house", 3, 3], ["place", "house", 4, 4], ["place", "road", 4, 4], ["place", "road", 5, 4],
        ["place", "factory", 22, 0], ["place", "house", 23, 15], ["place", "park", -1, 0], ["place", "shop", 0, 15],
        ["place", "factory", 10, 10], ["place", "factory", 14, 10], ["place", "shop", 18, 10],
        ["place", "road", 0, 0], ["bulldoze", 20, 20], ["bulldoze", 12, 12], ["bulldoze", 12, 12], ["place", "park", 10, 10],
    ] + _steps(1),
    # Bulldozing an inhabited house lowers the population at once, a factory stops its upkeep.
    "bulldoze": _road(range(0, 12), 4) + [
        ["place", "house", 0, 2], ["place", "house", 2, 2], ["place", "factory", 5, 5],
    ] + _steps(6) + [["bulldoze", 1, 3], ["step", 1], ["bulldoze", 6, 6], ["step", 1], ["bulldoze", 3, 4]] + _steps(2, 3),
    # Restart in the middle of a game.
    "reset": _road(range(0, 6), 4) + [["place", "house", 0, 2]] + _steps(3) + [["reset"]]
    + _road(range(0, 4), 1) + [["place", "house", 0, 2]] + _steps(2),
    # Bankruptcy, then nothing changes any more.
    "bankrupt": [["place", "factory", 0, 0], ["place", "factory", 4, 0], ["place", "shop", 8, 0]] + _steps(5, 5, 20, 10)
    + [["place", "road", 3, 3], ["bulldoze", 0, 0], ["step", 5]],
    # A whole game up to the win, then nothing changes any more.
    "win": affordable(_road(range(0, 12), 7) + [["place", "house", x, 5] for x in (0, 2, 4, 6)]
                      + [["place", "factory", 8, 8]] + _road(range(12, 24), 7)
                      + [["place", "house", x, 5] for x in range(8, 24, 2)] + [["place", "park", 2, 2]]
                      + [["place", "house", x, 8] for x in (0, 2, 4, 6)] + [["place", "shop", 12, 8]]
                      + _road(range(0, 24), 12) + [["place", "house", x, 10] for x in (0, 2, 4, 6, 12, 14, 16)]
                      + [["place", "park", 18, 8]] + [["place", "house", x, 13] for x in range(0, 24, 2)]
                      + _steps(40) + [["place", "road", 0, 0], ["step", 5]]),
}

RANDOM_SEEDS = (9101, 9102, 9103, 9104)


def hidden_scenarios() -> dict[str, list[list]]:
    scenarios = dict(HAND_WRITTEN)
    for seed in RANDOM_SEEDS:
        scenarios[f"random-{seed}"] = random_actions(seed, length=150)
    return scenarios
