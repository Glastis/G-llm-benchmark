"""Python implementation of the T1 rules (prompt.md). The hidden expected traces come from it, and the
C++ reference must produce the same output on random scenarios (grader/crosscheck.py)."""

from __future__ import annotations

import heapq
import re
from dataclasses import dataclass, field

UP, DOWN, IDLE = 1, -1, 0
HEADER = ("floors", "elevators", "capacity", "travel", "door")
INT64 = 2**63
MAX_TIME = 10**15
INTEGER = re.compile(r"-?[0-9]+")


class InputError(ValueError):
    pass


@dataclass
class Passenger:
    id: int
    time: int
    src: int
    dst: int
    elevator: int = -1
    board: int = -1
    exit: int = -1

    @property
    def dir(self) -> int:
        return UP if self.dst > self.src else DOWN


@dataclass
class Scenario:
    floors: int
    elevators: int
    capacity: int
    travel: int
    door: int
    start: list[int]
    passengers: list[Passenger] = field(default_factory=list)


def _int(token: str, line: int) -> int:
    if not INTEGER.fullmatch(token):
        raise InputError(f"line {line}: not an integer: {token}")
    value = int(token)
    if not -INT64 <= value < INT64:
        raise InputError(f"line {line}: out of the 64-bit range: {token}")
    return value


def parse(text: str) -> Scenario:
    header: dict[str, int] = {}
    start: list[int] | None = None
    passengers: list[Passenger] = []
    for n, raw in enumerate(text.splitlines(), 1):
        tokens = raw.split("#", 1)[0].split()
        if not tokens:
            continue
        key, values = tokens[0], [_int(t, n) for t in tokens[1:]]
        if key in HEADER or key == "start":
            if passengers:
                raise InputError(f"line {n}: {key} after a passenger line")
            if key in header or (key == "start" and start is not None):
                raise InputError(f"line {n}: repeated {key}")
            if key == "start":
                start = values
            elif len(values) != 1:
                raise InputError(f"line {n}: {key} takes one value")
            else:
                header[key] = values[0]
        elif key == "passenger":
            if len(values) != 4:
                raise InputError(f"line {n}: passenger takes four values")
            passengers.append(Passenger(*values))
        else:
            raise InputError(f"line {n}: unknown directive {key}")
    if missing := [k for k in HEADER if k not in header]:
        raise InputError(f"missing {', '.join(missing)}")
    floors, elevators = header["floors"], header["elevators"]
    if not (2 <= floors <= 10**6 and 1 <= elevators <= 1000) \
            or not all(1 <= header[k] <= 10**6 for k in ("capacity", "travel", "door")):
        raise InputError("header value out of range")
    start = [0] * elevators if start is None else start
    if len(start) != elevators or any(not 0 <= f < floors for f in start):
        raise InputError("bad start")
    seen = set()
    for p in passengers:
        if p.id < 0 or p.id in seen or not 0 <= p.time <= MAX_TIME or p.src == p.dst \
                or not (0 <= p.src < floors and 0 <= p.dst < floors):
            raise InputError(f"bad passenger {p.id}")
        seen.add(p.id)
    return Scenario(floors, elevators, header["capacity"], header["travel"], header["door"], start, passengers)


class Elevator:
    def __init__(self, floor: int):
        self.floor = floor
        self.dir = IDLE
        self.free = True
        self.moving = False
        self.riders: list[Passenger] = []
        self.waiting: list[Passenger] = []   # assignment order, which is (arrival tick, ID)


def _cost(e: Elevator, s: int, floors: int) -> int:
    behind = (e.dir == UP and s < e.floor) or (e.dir == DOWN and s > e.floor)
    return abs(e.floor - s) + len(e.riders) + len(e.waiting) + (floors if behind else 0)


def simulate(sc: Scenario) -> list[str]:
    cars = [Elevator(f) for f in sc.start]
    arrivals = sorted(sc.passengers, key=lambda p: (p.time, p.id))
    ends: list[tuple[int, int]] = []   # (tick, elevator) of the actions under way
    stops: list[str] = []
    i = delivered = 0

    def serve(e: Elevator, d: int) -> bool:
        return any(p.dst == e.floor for p in e.riders) or (
            len(e.riders) < sc.capacity and any(p.src == e.floor and p.dir == d for p in e.waiting))

    def ahead(e: Elevator, d: int) -> bool:
        return any((p.dst - e.floor) * d > 0 for p in e.riders) or any((p.src - e.floor) * d > 0 for p in e.waiting)

    def stop(k: int, e: Elevator, t: int) -> None:
        nonlocal delivered
        out = sorted((p for p in e.riders if p.dst == e.floor), key=lambda p: p.id)
        for p in out:
            p.exit = t
        e.riders = [p for p in e.riders if p.dst != e.floor]
        delivered += len(out)
        boarding = []
        for p in e.waiting:
            if p.src == e.floor and p.dir == e.dir and len(e.riders) < sc.capacity:
                p.board = t
                e.riders.append(p)
                boarding.append(p)
        e.waiting = [p for p in e.waiting if p.board < 0]
        ids = lambda ps: ",".join(str(p.id) for p in ps) or "-"
        stops.append(f"{t} {k} {e.floor} {'up' if e.dir == UP else 'down'} out={ids(out)} in={ids(boarding)}")
        e.free, e.moving = False, False
        heapq.heappush(ends, (t + sc.door, k))

    def decide(k: int, e: Elevator, t: int) -> None:
        if not e.riders and not e.waiting:
            e.dir = IDLE
            return
        if e.dir == IDLE:
            here = [p for p in e.waiting if p.src == e.floor]
            first = here[0] if here else e.waiting[0]
            e.dir = first.dir if here else (UP if first.src > e.floor else DOWN)
        if not serve(e, e.dir) and not ahead(e, e.dir):
            e.dir = -e.dir
        if serve(e, e.dir):
            stop(k, e, t)
        else:
            e.free, e.moving = False, True
            heapq.heappush(ends, (t + sc.travel, k))

    while delivered < len(arrivals):
        t = min(([arrivals[i].time] if i < len(arrivals) else []) + ([ends[0][0]] if ends else []))
        ready: set[int] = set()
        while ends and ends[0][0] == t:
            _, k = heapq.heappop(ends)
            e = cars[k]
            if e.moving:
                e.floor += e.dir
            e.free = True
            ready.add(k)
        while i < len(arrivals) and arrivals[i].time == t:
            p = arrivals[i]
            i += 1
            p.elevator = min(range(len(cars)), key=lambda k: (_cost(cars[k], p.src, sc.floors), k))
            cars[p.elevator].waiting.append(p)
            ready.add(p.elevator)
        # Only the elevators freed at t or given a passenger at t can act: the others are busy, or
        # idle with nothing to do.
        for k in sorted(ready):
            if cars[k].free:
                decide(k, cars[k], t)

    lines = stops + [f"passenger {p.id} elevator {p.elevator} wait {p.board - p.time} ride {p.exit - p.board}"
                     for p in sorted(sc.passengers, key=lambda p: p.id)]
    n = len(sc.passengers)
    waits = [p.board - p.time for p in sc.passengers]
    rides = [p.exit - p.board for p in sc.passengers]
    makespan = max((p.exit for p in sc.passengers), default=0)
    avg = lambda xs: "%.2f" % (sum(xs) / n if n else 0.0)
    lines.append(f"summary passengers {n} makespan {makespan} avg_wait {avg(waits)} "
                 f"max_wait {max(waits, default=0)} avg_ride {avg(rides)}")
    return lines


def run(text: str) -> str:
    return "\n".join(simulate(parse(text))) + "\n"


if __name__ == "__main__":
    import sys
    sys.stdout.write(run(open(sys.argv[1], encoding="utf-8").read()))
