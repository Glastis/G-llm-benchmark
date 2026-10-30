import pytest

from bench.config import load_pricing
from bench.pricing import UnknownPrice, Usage, request_cost

PRICING = load_pricing()


def test_opus_request_cost():
    usage = Usage(input=1_000, output=10_000, cache_read=100_000, cache_write_5m=20_000)
    expected = (1_000 * 4 + 10_000 * 20 + 100_000 * 0.20 + 20_000 * 4 * 1.25) / 1e6
    assert request_cost("claude-opus-5-5", usage, PRICING) == pytest.approx(expected)


def test_haiku_tier_depends_on_prompt_size():
    small = Usage(input=50_000, output=1_000)
    large = Usage(input=150_000, output=1_000)
    assert request_cost("claude-haiku-5-5", small, PRICING) == pytest.approx((50_000 * 0.10 + 1_000 * 0.50) / 1e6)
    assert request_cost("claude-haiku-5-5", large, PRICING) == pytest.approx((150_000 * 0.50 + 1_000 * 2.50) / 1e6)


def test_unknown_cache_price_is_an_error_not_a_zero():
    pricing = PRICING.model_copy(deep=True)
    pricing.models["claude-opus-5-5"].cache_read = None
    with pytest.raises(UnknownPrice):
        request_cost("claude-opus-5-5", Usage(input=10, output=10, cache_read=1_000), pricing)


def test_matches_claude_code_on_the_first_real_haiku_run():
    # s01_hello_haiku_r1: final usage of its two requests, and the costUSD Claude Code reported.
    requests = [Usage(input=2, output=154, cache_read=11_111, cache_write_1h=6_099),
                Usage(input=2, output=69, cache_read=17_210, cache_write_1h=185)]
    assert sum(request_cost("claude-haiku-5-5", u, PRICING) for u in requests) == pytest.approx(0.00165191, abs=1e-9)


def test_matches_claude_code_on_the_first_real_sonnet_run():
    # s01_hello_sonnet_r1: Sonnet has no prompt-size tier, so the run's totals price like one request.
    total = Usage(input=4, output=137, cache_read=27_546, cache_write_1h=5_510)
    assert request_cost("claude-sonnet-5-5", total, PRICING) == pytest.approx(0.0261726, abs=1e-9)


def test_strata_is_free():
    assert request_cost("strata", Usage(input=30_000, output=4_000, cache_read=200_000), PRICING) == 0
