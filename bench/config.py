"""Loading and validating the config files: contestants, prices and tasks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parent.parent

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Workers(Strict):
    contestant: str
    via: Literal["subagent", "bash"]


class Contestant(Strict):
    id: str = ""
    label: str
    backend: Literal["anthropic", "strata"]
    model: str
    effort: Effort
    strata_model: str | None = None
    max_output_tokens: int | None = None
    preamble: Path | None = None
    workers: Workers | None = None
    exclusive: bool = False


class Tier(Strict):
    max_prompt_tokens: int | None = None
    input: float
    output: float
    cache_read: float | None = None


class ModelPrice(Strict):
    input: float | None = None
    output: float | None = None
    cache_read: float | None = None
    tiers: list[Tier] | None = None

    def tier(self, prompt_tokens: int) -> Tier:
        """The price that applies to a request, depending on its prompt size."""
        if not self.tiers:
            return Tier.model_construct(input=self.input, output=self.output, cache_read=self.cache_read)
        for tier in self.tiers:
            if tier.max_prompt_tokens is None or prompt_tokens <= tier.max_prompt_tokens:
                return tier
        return self.tiers[-1]

    def unknown(self) -> list[str]:
        """The prices left null in pricing.yaml."""
        tiers = self.tiers or [self.tier(0)]
        rates = {"input": [t.input for t in tiers], "output": [t.output for t in tiers],
                 "cache_read": [t.cache_read for t in tiers]}
        return [name for name, values in rates.items() if None in values]


class CacheWrite(Strict):
    ttl_5m: float
    ttl_1h: float


class Pricing(Strict):
    as_of: str
    unit: Literal["usd_per_mtok"]
    models: dict[str, ModelPrice]
    cache_write_multiplier: CacheWrite
    electricity_eur_per_kwh: float | None = None


class Task(Strict):
    id: str
    title: str
    timeout_min: float
    prompt: Path
    fixture: Path
    deliverables: list[str]
    grading_sheet: bool = False   # graded with GRADING.md: `bench collect` drops a sheet into each finished run
    grader: Path | None = None    # a file with a grade(tree) function, run by `bench grade` (bench/grade.py)
    judge: Literal["code", "summary"] | None = None   # what `bench judge` grades (bench/judge.py)
    dir: Path = Path()

    def prompt_text(self) -> str:
        return (self.dir / self.prompt).read_text(encoding="utf-8")


@dataclass
class Bundle:
    contestants: dict[str, Contestant]
    pricing: Pricing
    tasks: dict[str, Task]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_contestants(path: Path = ROOT / "config" / "contestants.yaml") -> dict[str, Contestant]:
    return {cid: Contestant(id=cid, **data) for cid, data in _yaml(path).items()}


def load_pricing(path: Path = ROOT / "config" / "pricing.yaml") -> Pricing:
    data = _yaml(path)
    data["as_of"] = str(data["as_of"])
    return Pricing(**data)


def load_tasks(tasks_dir: Path = ROOT / "tasks") -> dict[str, Task]:
    tasks = {}
    for path in sorted(tasks_dir.glob("*/task.yaml")):
        task = Task(**_yaml(path), dir=path.parent)
        tasks[task.id] = task
    return tasks


def orchestrator_preamble(path: Path, via: str) -> str:
    """The common core of the preamble, followed only by the paragraph specific to the `via` mechanism."""
    core, *sections = path.read_text(encoding="utf-8").split("<!-- mechanism: ")
    by_mechanism = {s.split(" -->", 1)[0]: s.split(" -->", 1)[1].strip() for s in sections}
    return f"{core.strip()}\n\n{by_mechanism[via]}"


def subagents_json(path: Path = ROOT / "config" / "agents" / "haiku-worker.json") -> str:
    return json.dumps(json.loads(path.read_text(encoding="utf-8")))


def load_all(tasks_dir: Path = ROOT / "tasks") -> Bundle:
    b = Bundle(load_contestants(), load_pricing(), load_tasks(tasks_dir))
    for c in b.contestants.values():
        if c.model not in b.pricing.models:
            b.errors.append(f"{c.id}: model {c.model} missing from pricing.yaml")
        if c.backend == "strata" and not c.strata_model:
            b.errors.append(f"{c.id}: strata_model missing")
        if c.preamble and not (ROOT / c.preamble).is_file():
            b.errors.append(f"{c.id}: preamble {c.preamble} not found")
        if c.workers:
            if c.workers.contestant not in b.contestants:
                b.errors.append(f"{c.id}: unknown worker {c.workers.contestant}")
            if not c.preamble:
                b.errors.append(f"{c.id}: an orchestrated contestant needs a preamble")
            else:
                try:
                    orchestrator_preamble(ROOT / c.preamble, c.workers.via)
                except KeyError:
                    b.errors.append(f"{c.id}: no '{c.workers.via}' paragraph in {c.preamble}")
    for model, price in b.pricing.models.items():
        for what in price.unknown():
            b.warnings.append(f"unknown price: {model} {what}")
    if b.pricing.electricity_eur_per_kwh is None:
        b.warnings.append("electricity rate not set (Strata GPU energy shown without €)")
    for t in b.tasks.values():
        if not (t.dir / t.prompt).is_file():
            b.errors.append(f"{t.id}: task statement {t.prompt} not found")
        elif "TODO" in t.prompt_text():
            b.warnings.append(f"{t.id}: task statement not written yet")
        if t.grader and not (t.dir / t.grader).is_file():
            b.errors.append(f"{t.id}: grader {t.grader} not found")
        fixture = t.dir / t.fixture
        if not fixture.is_dir() or not any(p.name != ".gitkeep" for p in fixture.iterdir()):
            b.warnings.append(f"{t.id}: empty fixture")
    return b
