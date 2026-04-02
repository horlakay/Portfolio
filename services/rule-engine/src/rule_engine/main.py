from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sentinel_shared.auth import Role, require_roles
from sentinel_shared.config import get_common_settings
from sentinel_shared.logging import get_logger
from sentinel_shared.schemas.decision import (
    DecisionOutcome,
    RuleEvaluationRequest,
    RuleEvaluationResponse,
    RuleHit,
    RuleSeverity,
)
from sentinel_shared.telemetry import get_tracer, rule_hits_total
from sentinel_shared.utils.fastapi import build_app

logger = get_logger(__name__)
RULE_FILE = Path(__file__).resolve().parents[2] / "rules" / "default_rules.yaml"
tracer = get_tracer(__name__)


class RuleDefinition(BaseModel):
    rule_id: str
    name: str
    description: str
    severity: RuleSeverity
    decision: DecisionOutcome
    condition: str


class RuleRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.rules: list[RuleDefinition] = []
        self.reload()

    def reload(self) -> None:
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self.rules = [RuleDefinition.model_validate(item) for item in data.get("rules", [])]


class SafeEvaluator(ast.NodeVisitor):
    ALLOWED_NODES = {
        ast.Expression,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.Compare,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
        ast.In,
        ast.NotIn,
        ast.Name,
        ast.Load,
        ast.Attribute,
        ast.Constant,
        ast.UnaryOp,
        ast.Not,
    }

    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context

    def visit(self, node: ast.AST) -> Any:
        if type(node) not in self.ALLOWED_NODES:
            raise ValueError(f"Unsupported node in rule expression: {type(node).__name__}")
        return super().visit(node)

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Name(self, node: ast.Name) -> Any:
        return self.context[node.id]

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        value = self.visit(node.value)
        if isinstance(value, dict):
            return value.get(node.attr)
        return getattr(value, node.attr)

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        return not self.visit(node.operand)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [self.visit(value) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            right = self.visit(comparator)
            if isinstance(operator, ast.Gt) and not (left > right):
                return False
            if isinstance(operator, ast.GtE) and not (left >= right):
                return False
            if isinstance(operator, ast.Lt) and not (left < right):
                return False
            if isinstance(operator, ast.LtE) and not (left <= right):
                return False
            if isinstance(operator, ast.Eq) and left != right:
                return False
            if isinstance(operator, ast.NotEq) and left == right:
                return False
            if isinstance(operator, ast.In) and left not in right:
                return False
            if isinstance(operator, ast.NotIn) and not (left not in right):
                return False
            left = right
        return True


class AppState:
    def __init__(self) -> None:
        self.repository = RuleRepository(RULE_FILE)


app = build_app(get_common_settings())
app.state.container = AppState()


def evaluate_expression(expression: str, context: dict[str, Any]) -> bool:
    parsed = ast.parse(expression, mode="eval")
    return bool(SafeEvaluator(context).visit(parsed))


@app.post("/v1/rules/evaluate", response_model=RuleEvaluationResponse)
async def evaluate_rules(payload: RuleEvaluationRequest) -> RuleEvaluationResponse:
    with tracer.start_as_current_span("rule_engine.evaluate") as span:
        span.set_attribute("app.event_id", str(payload.event.event_id))
        span.set_attribute("app.account_id", payload.event.account_id)
        context = {
            "event": payload.event.model_dump(mode="python"),
            "features": payload.features.model_dump(mode="python"),
        }
        hits: list[RuleHit] = []
        for rule in app.state.container.repository.rules:
            if evaluate_expression(rule.condition, context):
                hit = RuleHit(
                    rule_id=rule.rule_id,
                    name=rule.name,
                    severity=rule.severity,
                    decision=rule.decision,
                    explanation=rule.description,
                )
                hits.append(hit)
                rule_hits_total.labels(rule.name, rule.decision).inc()
        span.set_attribute("app.rule_hits.count", len(hits))
        return RuleEvaluationResponse(hits=hits)


@app.get("/v1/rules")
async def list_rules(_: object = Depends(require_roles(Role.ANALYST, Role.ADMIN))) -> dict:
    return {"rules": [rule.model_dump() for rule in app.state.container.repository.rules]}


@app.post("/v1/admin/rules/reload")
async def reload_rules(_: object = Depends(require_roles(Role.ADMIN))) -> dict:
    try:
        app.state.container.repository.reload()
    except Exception as exc:
        logger.exception("rule_reload_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to reload rules") from exc
    return {"reloaded": True, "count": len(app.state.container.repository.rules)}
