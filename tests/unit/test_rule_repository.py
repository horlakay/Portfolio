from __future__ import annotations

from pathlib import Path

from rule_engine.main import RuleRepository


def test_rule_repository_loads_default_rules() -> None:
    repository = RuleRepository(
        Path(__file__).resolve().parents[2]
        / "services"
        / "rule-engine"
        / "rules"
        / "default_rules.yaml",
    )
    assert len(repository.rules) >= 8
