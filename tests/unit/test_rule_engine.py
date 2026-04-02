from __future__ import annotations

from sentinel_shared.schemas.decision import RuleSeverity
from rule_engine.main import app, evaluate_expression


def test_safe_rule_expression_evaluates() -> None:
    result = evaluate_expression(
        "event.amount > 1000 and features.new_device_flag",
        {
            "event": {"amount": 1250},
            "features": {"new_device_flag": True},
        },
    )
    assert result is True


def test_default_rules_include_critical_deny() -> None:
    rules = app.state.container.repository.rules
    assert any(rule.severity == RuleSeverity.CRITICAL for rule in rules)
