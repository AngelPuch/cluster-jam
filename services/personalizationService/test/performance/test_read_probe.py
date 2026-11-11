"""Keep the recorded p95 distinct from the mean or the maximum."""

from array import array

from test.performance.read_probe import percentiles


def test_tail_latency_uses_nearest_rank_with_a_slow_outlier() -> None:
    samples = array("d", [*range(1, 20), 10_000])
    result = percentiles(samples)
    assert result == {
        "count": 20,
        "p50_ms": 10,
        "p95_ms": 19,
        "max_ms": 10_000,
    }
    assert samples[-1] == 10_000


def test_no_samples_does_not_claim_an_observed_latency() -> None:
    assert percentiles(array("d"))["count"] == 0
