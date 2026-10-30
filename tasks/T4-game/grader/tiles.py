"""Which provided tiles a screenshot of the map shows, cell by cell (PLAN §10.28), and the checks on
how the game uses them. Pixels are compared exactly, in RGB.

A cell matches an opaque tile drawn at twice its size; or transparent tiles drawn over it, found by
their opaque pixels, with the opaque tile behind recognised on the rows they leave free; or, failing
that, tiles drawn at their own size in each quarter of the cell.
"""

from __future__ import annotations

import hashlib
from itertools import combinations
from pathlib import Path

from png import read

CELL, MAP_W, MAP_H = 32, 24, 16


def _rgb(rows: list[bytes]) -> list[bytes]:
    return [b"".join(row[i:i + 3] for i in range(0, len(row), 4)) for row in rows]


def _double(rows: list[bytes]) -> list[bytes]:
    doubled = [b"".join(row[i:i + 3] * 2 for i in range(0, len(row), 3)) for row in rows]
    return [row for row in doubled for _ in range(2)]


class Tile:
    def __init__(self, name: str, rgba: list[bytes], scale: int):
        rows = _rgb(rgba)
        alpha = [[row[i] for i in range(3, len(row), 4)] for row in rgba]
        if scale == 2:
            rows, alpha = _double(rows), [[a for a in row for _ in range(2)] for row in alpha for _ in range(2)]
        self.name, self.rows = name, rows
        # The runs of fully opaque pixels, per row: (row, first pixel, their RGB bytes).
        self.runs = []
        for y, row in enumerate(alpha):
            x = 0
            while x < len(row):
                if row[x] == 255:
                    end = x
                    while end < len(row) and row[end] == 255:
                        end += 1
                    self.runs.append((y, x, rows[y][3 * x:3 * end]))
                    x = end
                else:
                    x += 1

    def drawn_in(self, cell: list[bytes]) -> bool:
        return bool(self.runs) and all(cell[y][3 * x:3 * x + len(px)] == px for y, x, px in self.runs)


class Tiles:
    def __init__(self, assets: Path):
        self.by_scale: dict[int, tuple[dict[bytes, str], list[Tile], list[Tile]]] = {}
        files = sorted(assets.glob("*/*.png"))
        for scale in (1, 2):
            tiles = [Tile(f"{p.parent.name}/{p.stem}", read(p).rows, scale) for p in files]
            opaque = [t for t in tiles if t.name.startswith("opaque/")]
            exact = {}
            for t in opaque:
                exact.setdefault(b"".join(t.rows), t.name)
            self.by_scale[scale] = (exact, opaque, [t for t in tiles if t.name.startswith("transparent/")])

    def _match(self, cell: list[bytes], scale: int) -> list[str]:
        """The tiles this square shows, at this scale: [] when it shows none."""
        exact, opaque, overlays = self.by_scale[scale]
        if name := exact.get(b"".join(cell)):
            return [name]
        found = [t for t in overlays if t.drawn_in(cell)]
        if not found:
            return []
        covered = {y for t in found for y, _, _ in t.runs}
        free = [y for y in range(len(cell)) if y not in covered]
        base = max(opaque, key=lambda t: sum(cell[y] == t.rows[y] for y in free), default=None)
        if base is not None and free and sum(cell[y] == base.rows[y] for y in free) * 2 >= len(free):
            return [base.name] + [t.name for t in found]
        return [t.name for t in found]

    def cell(self, cell: list[bytes]) -> list[str]:
        """The tiles shown by a 32 × 32 cell (RGB rows)."""
        if names := self._match(cell, 2):
            return names
        half = CELL // 2
        quarters = [[row[3 * x:3 * (x + half)] for row in cell[y:y + half]] for y in (0, half) for x in (0, half)]
        return sorted({name for q in quarters for name in self._match(q, 1)})


class Shot:
    """The map of one screenshot: the tiles of each cell, and a hash of its pixels."""

    def __init__(self, path: Path, tiles: Tiles):
        image = read(path)
        if image.width < MAP_W * CELL or image.height < MAP_H * CELL:
            raise ValueError(f"{path.name}: {image.width} × {image.height}, smaller than the map")
        self.cells: dict[tuple[int, int], list[str]] = {}
        self.looks: dict[tuple[int, int], str] = {}
        for y in range(MAP_H):
            for x in range(MAP_W):
                rows = _rgb(image.crop(CELL * x, CELL * y, CELL, CELL))
                self.cells[x, y] = tiles.cell(rows)
                self.looks[x, y] = hashlib.sha1(b"".join(rows)).hexdigest()[:12]

    def signature(self, cell: tuple[int, int]) -> str:
        """What a cell shows: its tiles, or its pixels when it shows none."""
        return "+".join(self.cells[cell]) or f"pixels:{self.looks[cell]}"


def footprint(x: int, y: int, w: int, h: int) -> list[tuple[int, int]]:
    return [(x + dx, y + dy) for dy in range(h) for dx in range(w)]


def road_shape(cell: tuple[int, int], roads: set[tuple[int, int]]) -> tuple[str, frozenset]:
    x, y = cell
    sides = frozenset(side for side, (dx, dy) in {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}.items()
                      if (x + dx, y + dy) in roads)
    shape = {0: "single", 1: "end", 3: "tee", 4: "cross"}.get(len(sides))
    if shape is None:
        shape = "horizontal" if sides == {"E", "W"} else "vertical" if sides == {"N", "S"} else "corner"
    return shape, sides


def checks(shots: dict[str, Shot], buildings: list[tuple[str, str, list[tuple[int, int]]]],
           roads: tuple[str, set[tuple[int, int]]]) -> tuple[dict, dict]:
    """`buildings`: (screenshot, type, cells) of each building placed; `roads`: the screenshot of the
    road layout and its cells. Returns the checks and the figures."""
    covered = sum(bool(s.cells[c]) for s in shots.values() for c in s.cells)
    total = sum(len(s.cells) for s in shots.values())
    by_type: dict[str, set[str]] = {}
    composed = {}
    for shot, kind, cells in buildings:
        signatures = {shots[shot].signature(c) for c in cells}
        by_type.setdefault(kind, set()).update(signatures)
        composed[kind] = composed.get(kind, True) and len(signatures) >= 2
    same = [f"{a}={b}" for a, b in combinations(sorted(by_type), 2) if by_type[a] == by_type[b]]
    shot, cells = roads
    looks: dict[str, set[str]] = {}
    groups: dict[frozenset, set[str]] = {}
    for c in cells:
        shape, sides = road_shape(c, cells)
        looks.setdefault(shape, set()).add(shots[shot].looks[c])
        groups.setdefault(sides, set()).add(shots[shot].looks[c])
    main = [s for s in ("horizontal", "vertical", "corner", "cross") if s in looks]
    shared = [f"{a}~{b}" for a, b in combinations(main, 2) if looks[a] & looks[b]]
    consistent = sum(len(v) == 1 for v in groups.values())
    return {
        "tiles-used": covered * 2 >= total,
        "buildings-composed": bool(composed) and all(composed.values()),
        "types-distinct": not same,
        "roads-join": not shared and consistent == len(groups),
    }, {
        "tile_share": round(covered / total, 3) if total else None,
        "composed": composed,
        "same_tiles": same,
        "road_shapes_sharing_a_look": shared,
        "road_layouts_drawn_alike": f"{consistent}/{len(groups)}",
    }
