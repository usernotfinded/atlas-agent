from atlas_agent.agent.autonomous_paper_quality import TradingQualityThresholdPolicy


def test_default_threshold_policy_is_conservative():
    policy = TradingQualityThresholdPolicy()
    assert policy.min_bars_processed == 10
    assert policy.min_fills == 1
    assert policy.min_no_trade_decisions == 1
    assert policy.min_risk_rejections == 1
    assert policy.max_drawdown_pct == 50.0
    assert policy.max_exposure_pct == 200.0
    assert policy.max_turnover == 100.0
    assert policy.max_cost_impact_pct == 10.0
    assert policy.min_data_coverage == 0.5
    assert policy.max_invalid_metric_count == 0


def test_policy_roundtrips_through_dict():
    original = TradingQualityThresholdPolicy(min_bars_processed=42)
    restored = TradingQualityThresholdPolicy.from_dict(original.to_dict())
    assert restored == original
