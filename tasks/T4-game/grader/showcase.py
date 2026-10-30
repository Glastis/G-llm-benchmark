"""The test-mode script whose screenshots show how the game draws the map (PLAN §10.28): a road
layout with every shape, then each type of building, connected or not. Each scene starts from a
reset and fits in the starting money."""

from __future__ import annotations

from rules import SPECS


def _road(xs, ys):
    return [["place", "road", x, y] for y in ys for x in xs]


SCENES = {
    # A cross, a corner and a tee, with straight parts and dead ends.
    "roads": _road(range(8, 13), [5]) + _road([10], [3, 4, 6, 7]) + _road(range(15, 19), [3]) + _road([18], range(4, 8))
    + _road(range(1, 6), [10]) + _road([3], range(11, 14)),
    # Houses with and without a road, parks, then a few ticks so that the connected houses fill up.
    "houses": _road(range(0, 10), [8]) + [["place", "house", 1, 6], ["place", "house", 5, 9], ["place", "house", 14, 2],
                                           ["place", "park", 8, 6], ["place", "park", 18, 12], ["step", 12]],
    # A shop, a factory and a house along one road.
    "work": _road(range(0, 16), [7]) + [["place", "shop", 2, 5], ["place", "factory", 8, 8], ["place", "house", 12, 5]],
}


def script() -> tuple[list[list], dict[str, int]]:
    """The actions, with a reset before and a screenshot after each scene, and the index of each
    scene's first action."""
    actions, starts = [], {}
    for name, scene in SCENES.items():
        actions.append(["reset"])
        starts[name] = len(actions)
        actions += scene + [["screenshot", f".grade/shots/{name}.png"]]
    return actions, starts


def placed(actions: list[list], starts: dict[str, int], lines: list[str]):
    """The buildings the game accepted, per scene: (scene, type, cells), and the road cells of the
    road scene. A placement counts when its output line starts with `ok`."""
    buildings, roads = [], set()
    for name, first in starts.items():
        for i in range(first, first + len(SCENES[name])):
            kind, *args = actions[i]
            if kind != "place" or i >= len(lines) or not lines[i].startswith("ok"):
                continue
            type_, x, y = args
            w, h = SPECS[type_][:2]
            cells = [(x + dx, y + dy) for dy in range(h) for dx in range(w)]
            if type_ == "road":
                roads |= {(x, y)} if name == "roads" else set()
            else:
                buildings.append((name, type_, cells))
    return buildings, ("roads", roads)
