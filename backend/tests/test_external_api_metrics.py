from backend.services.external_api_metrics import ExternalApiMetrics


def test_external_api_metrics_counts_by_provider() -> None:
    metrics = ExternalApiMetrics(window_seconds=60)
    metrics.record("numlookup", True)
    metrics.record("numlookup", False)
    metrics.record("numverify", True)

    snap = metrics.snapshot()
    assert snap["total_per_minute"] == 3
    assert snap["providers"]["numlookup"]["total"] == 2
    assert snap["providers"]["numlookup"]["ok"] == 1
    assert snap["providers"]["numlookup"]["errors"] == 1
    assert snap["providers"]["numverify"]["total"] == 1


def test_external_api_metrics_prunes_old_samples() -> None:
    metrics = ExternalApiMetrics(window_seconds=0)
    metrics.record("sirene", False)
    snap = metrics.snapshot()
    assert snap["total_per_minute"] == 0
    assert snap["providers"] == {}
