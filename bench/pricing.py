"""API-equivalent cost: tokens × the dated prices of config/pricing.yaml (ARCHITECTURE §8)."""

from __future__ import annotations

from dataclasses import dataclass

from bench.config import Pricing


@dataclass
class Usage:
    """The usage of one request, as reported by an assistant message of the stream-json."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0

    @property
    def prompt_tokens(self) -> int:
        return self.input + self.cache_read + self.cache_write_5m + self.cache_write_1h


class UnknownPrice(ValueError):
    pass


def request_cost(model: str, usage: Usage, pricing: Pricing) -> float:
    """Cost of one request in $. The tier is chosen request by request (Haiku above 100K)."""
    if model not in pricing.models:
        raise UnknownPrice(f"model {model} missing from pricing.yaml")
    tier = pricing.models[model].tier(usage.prompt_tokens)
    if tier.input is None or tier.output is None:
        raise UnknownPrice(f"unknown input or output price for {model}: fill it in pricing.yaml")
    if tier.cache_read is None and usage.cache_read:
        raise UnknownPrice(f"unknown cache read price for {model}: fill it in pricing.yaml")
    mult = pricing.cache_write_multiplier
    per_mtok = (
        usage.input * tier.input
        + usage.output * tier.output
        + usage.cache_read * (tier.cache_read or 0)
        + usage.cache_write_5m * tier.input * mult.ttl_5m
        + usage.cache_write_1h * tier.input * mult.ttl_1h
    )
    return per_mtok / 1_000_000
