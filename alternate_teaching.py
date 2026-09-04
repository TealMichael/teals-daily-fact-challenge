from __future__ import annotations

"""Deterministic teaching models for alternate Daily Fix Your Misses.

Multiplication remains the gold-standard source of truth.  This module reads the
existing multiplication Fact Coach plan for multiplication items that appear in
Mixed, but it never imports or writes the multiplication mastery engine.
"""

from dataclasses import dataclass
import re
from typing import Mapping

from alternate_followup import skill_identity_for_question
from fact_coach import coach_plan


@dataclass(frozen=True)
class TeachingPlan:
    domain: str
    strategy_id: str
    title: str
    relationship: str
    steps: tuple[str, ...]
    recap: str
    final_equation: str
    visual_type: str
    visual: dict

    def as_dict(self) -> dict:
        return {
            "domain": self.domain,
            "strategy_id": self.strategy_id,
            "title": self.title,
            "relationship": self.relationship,
            "steps": list(self.steps),
            "recap": self.recap,
            "final_equation": self.final_equation,
            "visual_type": self.visual_type,
            "visual": dict(self.visual),
        }


def _prompt(question: Mapping) -> str:
    return re.sub(r"\s+", " ", str(question.get("prompt") or "").strip())


def _addition_plan(a: int, b: int) -> TeachingPlan:
    total = a + b
    if a == 0 or b == 0:
        other = b if a == 0 else a
        return TeachingPlan(
            "Addition Facts", "add_zero", "Adding zero keeps the number the same",
            f"Zero does not add any more objects, so the total stays {other}.",
            (f"Start with {other}.", "Add 0 more.", f"You still have {other}."),
            f"Adding 0 keeps {other} the same.", f"{a} + {b} = {total}",
            "counters", {"groups": [other, 0], "total": total},
        )
    if a == b:
        return TeachingPlan(
            "Addition Facts", "double", "Use a double you know",
            f"{a} + {b} is two equal groups of {a}.",
            (f"See one group of {a}.", f"Match it with another {a}.", f"Together they make {total}."),
            f"Double {a} is {total}.", f"{a} + {b} = {total}",
            "double", {"value": a, "total": total},
        )
    # Near doubles are especially efficient for neighboring addends that do not cross 10.
    if abs(a - b) == 1 and min(a, b) <= 6:
        small = min(a, b)
        return TeachingPlan(
            "Addition Facts", "near_double", "Use a near double",
            f"Double {small}, then add 1 more.",
            (f"{small} + {small} = {small * 2}.", "One addend is 1 bigger.", f"{small * 2} + 1 = {total}."),
            f"Double {small}, then add 1: {small * 2} + 1 = {total}.", f"{a} + {b} = {total}",
            "near_double", {"base": small, "extra": 1, "total": total},
        )
    # Make-10 is the preferred strategy whenever the sum crosses ten.
    if total > 10:
        target = max(a, b)
        source = min(a, b)
        need = 10 - target
        if 0 < need <= source:
            remainder = source - need
            return TeachingPlan(
                "Addition Facts", "make_ten", "Make a 10",
                f"Move {need} from {source} to {target}. That makes 10, with {remainder} left.",
                (f"{target} needs {need} to make 10.", f"Break {source} into {need} and {remainder}.", f"10 + {remainder} = {total}."),
                f"Make 10 first: 10 + {remainder} = {total}.", f"{a} + {b} = {total}",
                "ten_frame", {"target": target, "source": source, "move": need, "remainder": remainder, "total": total},
            )
    large, small = max(a, b), min(a, b)
    return TeachingPlan(
        "Addition Facts", "count_on", "Start big and count on",
        f"Start at {large}. Add {small} more.",
        (f"Start at {large}.", f"Move {small} steps to the right.", f"Land on {total}."),
        f"Start at {large} and count on {small} to land on {total}.", f"{a} + {b} = {total}",
        "number_line", {"start": large, "delta": small, "end": total},
    )


def _subtraction_plan(total: int, sub: int) -> TeachingPlan:
    answer = total - sub
    if sub == 0:
        return TeachingPlan(
            "Subtraction Facts", "subtract_zero", "Taking away zero changes nothing",
            f"You start with {total} and take away none.",
            (f"Start with {total}.", "Take away 0.", f"{total} are still left."),
            f"Subtracting 0 keeps {total} the same.", f"{total} − {sub} = {answer}",
            "part_whole", {"total": total, "known": 0, "unknown": answer},
        )
    if answer == 0:
        return TeachingPlan(
            "Subtraction Facts", "take_all", "Take away the whole amount",
            f"You have {total} and take away all {total} of them.",
            (f"Start with {total}.", f"Take away {sub}.", "Nothing is left."),
            f"A number minus itself is 0.", f"{total} − {sub} = 0",
            "part_whole", {"total": total, "known": sub, "unknown": 0},
        )
    return TeachingPlan(
        "Subtraction Facts", "missing_addend", "Think addition",
        f"Ask: {sub} + what makes {total}?",
        (f"The whole is {total}.", f"One part is {sub}.", f"The missing part is {answer}."),
        f"{sub} + {answer} = {total}, so {total} − {sub} = {answer}.",
        f"{total} − {sub} = {answer}",
        "part_whole", {"total": total, "known": sub, "unknown": answer},
    )


def _division_plan(dividend: int, divisor: int) -> TeachingPlan:
    quotient = dividend // divisor
    return TeachingPlan(
        "Division Facts", "think_multiplication", "Think multiplication",
        f"Division asks how many are in each equal group. Think: {divisor} × ? = {dividend}.",
        (f"Make {divisor} equal groups.", f"Put {quotient} in each group.", f"{divisor} × {quotient} = {dividend}."),
        f"{divisor} × {quotient} = {dividend}, so {dividend} ÷ {divisor} = {quotient}.",
        f"{dividend} ÷ {divisor} = {quotient}",
        "equal_groups", {"groups": divisor, "size": quotient, "total": dividend},
    )


def _integer_plan(a: int, operation: str, b: int) -> TeachingPlan:
    delta = b if operation == "+" else -b
    end = a + delta
    direction = "right" if delta > 0 else ("left" if delta < 0 else "stay")
    amount = abs(delta)
    if b == 0:
        if operation == "−":
            relationship = "Subtracting 0 does not change your position on the number line."
            title = "Subtract zero: stay put"
        else:
            relationship = "Adding 0 does not change your position on the number line."
            title = "Add zero: stay put"
    elif operation == "−" and b < 0:
        relationship = f"Subtracting {b} means move the opposite direction: {amount} spaces right."
        title = "Subtract a negative: move right"
    elif operation == "−":
        relationship = f"Subtracting {b} means move {amount} spaces left."
        title = "Subtract: move left"
    elif b < 0:
        relationship = f"Adding {b} means move {amount} spaces left."
        title = "Add a negative: move left"
    else:
        relationship = f"Adding {b} means move {amount} spaces right."
        title = "Add a positive: move right"
    move_text = "Stay where you are." if amount == 0 else f"Move {amount} space{'s' if amount != 1 else ''} {direction}."
    return TeachingPlan(
        "Integers", f"integer_{'add' if operation == '+' else 'subtract'}_{direction}", title,
        relationship,
        (f"Start at {a}.", move_text, f"Land on {end}."),
        f"Start at {a}, move {amount} {direction}, and land on {end}.",
        f"{a} {operation} {'(' + str(b) + ')' if b < 0 else b} = {end}",
        "integer_line", {"start": a, "delta": delta, "end": end, "operation": operation, "operand": b},
    )


def _multiplication_plan(a: int, b: int) -> TeachingPlan:
    # Read the exact proven multiplication strategy plan without touching its code or mastery path.
    p = coach_plan(a, b)
    steps: list[str] = [p.relationship]
    if p.anchor_answer is not None:
        steps.append(f"Start with {p.anchor_a} × {p.anchor_b} = {p.anchor_answer}.")
    if p.second_equation:
        steps.append(p.second_equation)
    if p.combine_equation:
        steps.append(p.combine_equation)
    titles = {
        "ten_plus_one": "Use ×10, then add one group",
        "ten_plus_two": "Use ×10, then add two groups",
        "double": "Double it",
        "five_anchor": "Use the ×5 anchor",
        "ten_anchor": "Use the ×10 anchor",
        "double_double": "Double a double",
        "double_plus_one": "Double, then add one group",
        "ten_minus_one": "Use ×10, then take one group away",
        "five_plus_one": "Use ×5, then add one group",
        "five_plus_two": "Use ×5, then add two groups",
        "ten_minus_two": "Use ×10, then take two groups away",
        "array": "See the equal groups",
    }
    return TeachingPlan(
        "Multiplication", f"mixed_{p.strategy_id}", titles.get(p.strategy_id, "See the equal groups"),
        p.relationship,
        tuple(steps[:4]),
        p.combine_equation or p.final_equation,
        p.final_equation,
        "multiplication_array",
        {
            "groups": p.groups,
            "size": p.size,
            "visual_groups": p.visual_groups,
            "visual_mode": p.visual_mode,
            "first_groups": p.first_groups,
            "second_groups": p.second_groups,
            "anchor_a": p.anchor_a,
            "anchor_b": p.anchor_b,
            "anchor_answer": p.anchor_answer,
            "second_equation": p.second_equation,
            "combine_equation": p.combine_equation,
            "direct_message": p.direct_message,
        },
    )


def teaching_plan_for_question(question: Mapping, default_domain: str | None = None) -> TeachingPlan:
    """Return the deterministic model used by alternate Fix Your Misses."""
    prompt = _prompt(question)
    identity = skill_identity_for_question(question, default_domain)
    domain = identity.domain

    if domain == "Addition Facts":
        match = re.fullmatch(r"\s*(\d+)\s*\+\s*(\d+)\s*", prompt)
        if not match:
            raise ValueError(f"Could not build addition model for {prompt!r}")
        return _addition_plan(int(match.group(1)), int(match.group(2)))

    if domain == "Subtraction Facts":
        match = re.fullmatch(r"\s*(\d+)\s*[−-]\s*(\d+)\s*", prompt)
        if not match:
            raise ValueError(f"Could not build subtraction model for {prompt!r}")
        return _subtraction_plan(int(match.group(1)), int(match.group(2)))

    if domain == "Division Facts":
        match = re.fullmatch(r"\s*(\d+)\s*[÷/]\s*(\d+)\s*", prompt)
        if not match:
            raise ValueError(f"Could not build division model for {prompt!r}")
        return _division_plan(int(match.group(1)), int(match.group(2)))

    if domain == "Multiplication":
        match = re.fullmatch(r"\s*(\d+)\s*[×xX*]\s*(\d+)\s*", prompt)
        if not match:
            raise ValueError(f"Could not build multiplication model for {prompt!r}")
        return _multiplication_plan(int(match.group(1)), int(match.group(2)))

    match = re.fullmatch(r"\s*([−-]?\d+)\s*([+−-])\s*(?:\(([−-]?\d+)\)|([−-]?\d+))\s*", prompt)
    if not match:
        raise ValueError(f"Could not build integer model for {prompt!r}")
    a = int(match.group(1).replace("−", "-"))
    operation = "+" if match.group(2) == "+" else "−"
    b_raw = match.group(3) if match.group(3) is not None else match.group(4)
    b = int(str(b_raw).replace("−", "-"))
    return _integer_plan(a, operation, b)
