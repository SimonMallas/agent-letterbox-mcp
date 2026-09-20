from letterbox_mcp.cli import parse_ring


def test_three_outcomes_and_unconfirmed_is_reason():
    submitted = parse_ring("doorbell-outcome v=1 outcome=submitted reason=- target=abc\n")
    assert submitted == {"outcome": "submitted", "reason": "-", "target": "abc"}
    pasted = parse_ring(
        "doorbell-outcome v=1 outcome=pasted_not_submitted reason=enter_failed target=pane-1\n"
    )
    assert pasted["outcome"] == "pasted_not_submitted"
    assert pasted["reason"] == "enter_failed"
    timed = parse_ring(
        "doorbell-outcome v=1 outcome=no_live_surface reason=unconfirmed target=-\n"
    )
    assert timed["outcome"] == "no_live_surface"
    assert timed["reason"] == "unconfirmed"
    assert parse_ring("doorbell-outcome v=1 outcome=unconfirmed reason=- target=-\n") is None
