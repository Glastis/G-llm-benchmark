"""Python model of the T4 rules (prompt.md, "Simulation rules"), without research. The expected lines
of the hidden scenarios come from it (PLAN §10.28)."""

from __future__ import annotations

from dataclasses import dataclass, field

WIDTH, HEIGHT = 24, 16
START_MONEY = 1000
WIN_POPULATION = 150
TAX_PERIOD = 10

# type: (width, height, cost, upkeep per tick)
SPECS = {
    "road": (1, 1, 10, 0),
    "house": (2, 2, 100, 0),
    "shop": (2, 2, 250, 2),
    "factory": (3, 2, 400, 5),
    "park": (2, 2, 60, 1),
}
BASE_CAP, PARK_BONUS, PARK_RANGE, SMOKE_MALUS, SMOKE_RANGE = 8, 4, 3, 3, 2
FACTORY_JOBS, SHOP_JOBS, WAGE, SHOP_RANGE, SHOP_PER_HOUSE = 10, 4, 2, 4, 3


@dataclass
class Building:
    type: str
    x: int
    y: int
    residents: int = 0

    @property
    def w(self) -> int:
        return SPECS[self.type][0]

    @property
    def h(self) -> int:
        return SPECS[self.type][1]

    def cells(self):
        return [(self.x + dx, self.y + dy) for dy in range(self.h) for dx in range(self.w)]


def distance(a: Building, b: Building) -> int:
    """Chebyshev distance between two footprints: 1 when they touch, even diagonally."""
    gap_x = max(0, b.x - (a.x + a.w - 1), a.x - (b.x + b.w - 1))
    gap_y = max(0, b.y - (a.y + a.h - 1), a.y - (b.y + b.h - 1))
    return max(gap_x, gap_y)


@dataclass
class City:
    money: int = START_MONEY
    tick: int = 0
    status: str = "playing"
    buildings: list[Building] = field(default_factory=list)

    def grid(self) -> list[list[str | None]]:
        g: list[list[str | None]] = [[None] * WIDTH for _ in range(HEIGHT)]
        for b in self.buildings:
            for x, y in b.cells():
                g[y][x] = b.type
        return g

    def at(self, x: int, y: int) -> Building | None:
        return next((b for b in self.buildings if (x, y) in b.cells()), None)

    @property
    def population(self) -> int:
        return sum(b.residents for b in self.buildings if b.type == "house")

    def place(self, type_: str, x: int, y: int) -> bool:
        if self.status != "playing" or type_ not in SPECS:
            return False
        b = Building(type_, x, y)
        if any(not (0 <= cx < WIDTH and 0 <= cy < HEIGHT) or self.at(cx, cy) for cx, cy in b.cells()):
            return False
        cost = SPECS[type_][2]
        if self.money < cost:
            return False
        self.money -= cost
        self.buildings.append(b)
        return True

    def bulldoze(self, x: int, y: int) -> bool:
        b = self.at(x, y) if self.status == "playing" else None
        if b is None:
            return False
        self.buildings.remove(b)
        return True

    def connected(self, b: Building) -> bool:
        inside = set(b.cells())
        roads = {(r.x, r.y) for r in self.buildings if r.type == "road"}
        return any((cx + dx, cy + dy) in roads and (cx + dx, cy + dy) not in inside
                   for cx, cy in inside for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))

    def capacity(self, house: Building) -> int:
        cap = BASE_CAP
        if any(p.type == "park" and distance(house, p) <= PARK_RANGE for p in self.buildings):
            cap += PARK_BONUS
        cap -= SMOKE_MALUS * sum(1 for f in self.buildings if f.type == "factory" and distance(house, f) <= SMOKE_RANGE)
        return max(cap, 0)

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            if self.status != "playing":
                return
            self._tick()

    def _tick(self) -> None:
        self.tick += 1
        houses = [b for b in self.buildings if b.type == "house"]
        for h in houses:
            target = self.capacity(h) if self.connected(h) else 0
            h.residents += (h.residents < target) - (h.residents > target)
        population = self.population
        connected = [b for b in self.buildings if b.type in ("factory", "shop") and self.connected(b)]
        jobs = sum(FACTORY_JOBS if b.type == "factory" else SHOP_JOBS for b in connected)
        income = WAGE * min(population, jobs)
        for shop in (b for b in connected if b.type == "shop"):
            income += SHOP_PER_HOUSE * sum(1 for h in houses if h.residents > 0 and distance(shop, h) <= SHOP_RANGE)
        if self.tick % TAX_PERIOD == 0:
            income += population
        self.money += income - sum(SPECS[b.type][3] for b in self.buildings)
        if population >= WIN_POPULATION:
            self.status = "won"
        elif self.money < 0:
            self.status = "bankrupt"

    def line(self, result: bool | None) -> str:
        """The test mode's line after a command (prompt.md, "Test mode")."""
        word = "-" if result is None else "ok" if result else "refused"
        return f"{word} {self.tick} {self.money} {self.population} {self.status}"
