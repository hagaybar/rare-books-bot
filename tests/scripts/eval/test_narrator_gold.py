from scripts.eval.narrator_gold import estimate_request_cost, estimate_batch_cost, PRICING

def test_pricing_table_has_slate_and_judge():
    for m in ["gpt-4.1", "gpt-4.1-mini", "gpt-5-mini", "gpt-5.4-mini", "gpt-5.4"]:
        assert m in PRICING

def test_estimate_request_cost_standard():
    # gpt-4.1: $2/1M in, $8/1M out
    cost = estimate_request_cost("gpt-4.1", input_tokens=1000, max_output_tokens=1000, batch=False)
    assert abs(cost - (1000 * 2.0 / 1e6 + 1000 * 8.0 / 1e6)) < 1e-9

def test_estimate_request_cost_batch_is_half():
    full = estimate_request_cost("gpt-4.1", 1000, 1000, batch=False)
    half = estimate_request_cost("gpt-4.1", 1000, 1000, batch=True)
    assert abs(half - full / 2) < 1e-9

def test_estimate_batch_cost_sums_requests():
    reqs = [("gpt-4.1", 1000, 1000), ("gpt-5-mini", 1000, 1000)]
    total = estimate_batch_cost(reqs, batch=True)
    expected = (estimate_request_cost("gpt-4.1", 1000, 1000, batch=True)
                + estimate_request_cost("gpt-5-mini", 1000, 1000, batch=True))
    assert abs(total - expected) < 1e-9
