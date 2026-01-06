from app import rules


def test_rules_priority_to_severity_and_notify():
    payload = {"ticket_id": 123, "type": "billing", "priority": "low"}
    decision = rules.evaluate(payload)
    assert decision.severity == "low"
    assert decision.notify is False

    payload_high = {"ticket_id": 123, "type": "billing", "priority": "high"}
    decision_high = rules.evaluate(payload_high)
    assert decision_high.severity == "high"
    assert decision_high.notify is True

