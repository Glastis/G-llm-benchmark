"""Statistics over the repetitions of a campaign (PLAN §10.33): how good a contestant is, how steady
it is from one run to the next, how sure the ranking of the contestants is and how steady the judge is."""

from __future__ import annotations

import math
import random
import statistics

# Student's t at 97.5 %, by degrees of freedom, for the 95 % confidence interval of a mean. Beyond 30
# degrees of freedom, the value at 30, slightly wide.
T975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
        2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]
SPLIT_MIN_RUNS = 4      # two halves of two runs at least
SPLIT_MIN_CONTESTANTS = 3
SPLITS = 1000
READINGS = [(0.9, "excellent"), (0.75, "good"), (0.5, "moderate")]


def clip(value: float, low: float | None, high: float | None) -> float:
    if low is not None:
        value = max(low, value)
    return value if high is None else min(high, value)


def describe(values: list[float], low: float | None = 0.0, high: float | None = None) -> dict | None:
    """n, mean, the mean's 95 % confidence interval (Student, kept within `low` and `high`), median,
    standard deviation, min and max. The deviation and the interval need two values."""
    if not values:
        return None
    n, mean = len(values), statistics.fmean(values)
    sd = statistics.stdev(values) if n > 1 else None
    ci = None
    if sd is not None:
        half = T975[min(n - 1, len(T975)) - 1] * sd / math.sqrt(n)
        ci = [clip(mean - half, low, high), clip(mean + half, low, high)]
    return {"n": n, "mean": mean, "ci": ci, "median": statistics.median(values), "sd": sd,
            "min": min(values), "max": max(values)}


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman's ρ, tied values sharing their mean rank. None below three pairs or when a side is constant."""
    if len(x) < 3:
        return None
    try:
        return statistics.correlation(x, y, method="ranked")
    except statistics.StatisticsError:
        return None


def reading(rho: float | None) -> str:
    if rho is None:
        return "n/a"
    return next((label for floor, label in READINGS if rho >= floor), "poor")


def agreement(pairs: list[tuple[float, float]]) -> dict:
    """How steady the judge is on a criterion: ρ between its first and second pass over the runs, which
    only looks at the order, and the mean gap between the two grades of a run, which a judge more
    generous the second time would show."""
    first, second = [a for a, _ in pairs], [b for _, b in pairs]
    rho = spearman(first, second)
    return {"n": len(pairs), "rho": rho, "reading": reading(rho),
            "gap": statistics.fmean(abs(a - b) for a, b in pairs) if pairs else None}


def split_half(scores: dict[str, list[float]], splits: int = SPLITS, seed: int = 0) -> dict | None:
    """How sure the ranking of the contestants is: each contestant's runs cut at random into two halves
    of the same size, ρ between the rankings by the mean of each half, the median over `splits` cuts,
    then the Spearman-Brown estimate for all the runs. Contestants with fewer than `SPLIT_MIN_RUNS` runs
    are left out."""
    kept = {k: v for k, v in scores.items() if len(v) >= SPLIT_MIN_RUNS}
    if len(kept) < SPLIT_MIN_CONTESTANTS:
        return None
    rng, rhos = random.Random(seed), []
    for _ in range(splits):
        first, second = [], []
        for values in kept.values():
            drawn, half = rng.sample(values, len(values)), len(values) // 2
            first.append(statistics.fmean(drawn[:half]))
            second.append(statistics.fmean(drawn[half:2 * half]))
        if (rho := spearman(first, second)) is not None:
            rhos.append(rho)
    if not rhos:
        return None
    half_rho = statistics.median(rhos)
    full = 2 * half_rho / (1 + half_rho) if half_rho > -1 else -1.0
    return {"contestants": len(kept), "left_out": sorted(set(scores) - set(kept)),
            "min_runs": min(len(v) for v in kept.values()), "rho_half": half_rho, "rho": full, "reading": reading(full)}
