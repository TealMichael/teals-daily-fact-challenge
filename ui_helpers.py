from __future__ import annotations

"""Small display helpers shared by student and teacher UI modules."""

from fact_engine import Fact
from fact_coach import coach_plan


def format_seconds(seconds: float | None) -> str:
    value = float(seconds or 0.0)
    if value < 60:
        return f"{value:.1f}s"
    minutes = int(value // 60)
    remainder = value - minutes * 60
    return f"{minutes}:{remainder:04.1f}"


def strategy_tip(fact: Fact) -> str:
    """Teacher/student text aligned to the same relationships used by Fact Coach."""
    plan = coach_plan(fact.a, fact.b)
    if plan.needs_anchor:
        anchor = f"{plan.anchor_a} × {plan.anchor_b} = {plan.anchor_answer}"
        second = f" Then use {plan.second_equation}." if plan.second_equation else ""
        return f"{plan.relationship} Start with {anchor}.{second} Put it together: {plan.combine_equation}."
    return f"{plan.relationship} {plan.direct_message or plan.combine_equation}".strip()
