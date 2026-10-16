from __future__ import annotations

"""Interactive Fact Coach strategy plans.

The Fact Coach does not decide mastery and does not create new independent
assessment evidence. It translates a missed multiplication fact into a short,
relationship-based teaching sequence that runs in the student's browser:

    see the structure -> retrieve one familiar anchor when useful ->
    combine the parts -> retry the original fact.

Plans are deterministic so the same fact is taught consistently.  The
student's original Daily/Focus attempt remains the mastery evidence; anchor
responses inside the coach are deliberately treated as scaffolded practice.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CoachPlan:
    strategy_id: str
    groups: int
    size: int
    visual_groups: int
    visual_mode: str
    first_groups: int
    second_groups: int
    operation: str
    relationship: str
    anchor_a: int | None
    anchor_b: int | None
    anchor_answer: int | None
    anchor_prompt: str
    second_equation: str
    combine_equation: str
    final_equation: str
    direct_message: str = ""

    @property
    def needs_anchor(self) -> bool:
        return self.anchor_a is not None and self.anchor_b is not None and self.anchor_answer is not None

    def as_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "groups": self.groups,
            "size": self.size,
            "visual_groups": self.visual_groups,
            "visual_mode": self.visual_mode,
            "first_groups": self.first_groups,
            "second_groups": self.second_groups,
            "operation": self.operation,
            "relationship": self.relationship,
            "anchor_a": self.anchor_a,
            "anchor_b": self.anchor_b,
            "anchor_answer": self.anchor_answer,
            "anchor_prompt": self.anchor_prompt,
            "second_equation": self.second_equation,
            "combine_equation": self.combine_equation,
            "final_equation": self.final_equation,
            "direct_message": self.direct_message,
            "needs_anchor": self.needs_anchor,
        }


def _choose_groups_factor(a: int, b: int) -> tuple[int, int]:
    """Choose the factor whose relationship gives the clearest short strategy.

    Multiplication is commutative, so the visual may rotate a fact.  For
    example, 7 x 4 is coached as 4 groups of 7 because doubling 2 x 7 is a
    cleaner relationship than decomposing 7 groups into 5 + 2.
    """
    if a == b:
        return a, b

    # 11/12 are extension facts and should explicitly connect back to x10.
    priority = (11, 12, 2, 5, 10, 4, 3, 9, 6, 7, 8)
    factors = {a, b}
    for factor in priority:
        if factor in factors:
            return factor, b if a == factor else a
    return a, b


def _additive_plan(groups: int, size: int, first: int, second: int, strategy_id: str) -> CoachPlan:
    first_answer = first * size
    second_answer = second * size
    product = groups * size
    return CoachPlan(
        strategy_id=strategy_id,
        groups=groups,
        size=size,
        visual_groups=groups,
        visual_mode="split_add",
        first_groups=first,
        second_groups=second,
        operation="+",
        relationship=f"Break {groups} groups into {first} groups + {second} {'group' if second == 1 else 'groups'}.",
        anchor_a=first,
        anchor_b=size,
        anchor_answer=first_answer,
        anchor_prompt="Start with a fact you know",
        second_equation=f"{second} × {size} = {second_answer}" if second != 1 else f"1 × {size} = {size}",
        combine_equation=f"{first_answer} + {second_answer} = {product}",
        final_equation=f"{groups} × {size} = {product}",
    )


def _subtractive_plan(groups: int, size: int, remove: int, strategy_id: str) -> CoachPlan:
    full = 10 * size
    removed = remove * size
    product = groups * size
    return CoachPlan(
        strategy_id=strategy_id,
        groups=groups,
        size=size,
        visual_groups=10,
        visual_mode="split_subtract",
        first_groups=groups,
        second_groups=remove,
        operation="−",
        relationship=f"Think 10 groups, then take away {remove} {'group' if remove == 1 else 'groups'}.",
        anchor_a=10,
        anchor_b=size,
        anchor_answer=full,
        anchor_prompt="Start with the ×10 fact you know",
        second_equation=f"{remove} × {size} = {removed}" if remove != 1 else f"1 × {size} = {size}",
        combine_equation=f"{full} − {removed} = {product}",
        final_equation=f"{groups} × {size} = {product}",
    )


def coach_plan(a: int, b: int) -> CoachPlan:
    a = int(a); b = int(b)
    if not (2 <= a <= 12 and 2 <= b <= 12):
        raise ValueError("Fact Coach supports factors 2 through 12")

    groups, size = _choose_groups_factor(a, b)
    product = groups * size

    if groups == 11:
        plan = _additive_plan(11, size, 10, 1, "ten_plus_one")
    elif groups == 12:
        plan = _additive_plan(12, size, 10, 2, "ten_plus_two")
    elif groups == 2:
        plan = CoachPlan(
            strategy_id="double",
            groups=2, size=size, visual_groups=2, visual_mode="direct",
            first_groups=1, second_groups=1, operation="+",
            relationship=f"×2 means double {size}.",
            anchor_a=None, anchor_b=None, anchor_answer=None, anchor_prompt="",
            second_equation=f"{size} + {size} = {product}",
            combine_equation=f"{size} + {size} = {product}",
            final_equation=f"2 × {size} = {product}",
            direct_message=f"Two equal groups of {size} make {product}.",
        )
    elif groups == 5:
        plan = CoachPlan(
            strategy_id="five_anchor",
            groups=5, size=size, visual_groups=5, visual_mode="direct",
            first_groups=5, second_groups=0, operation="+",
            relationship="Five groups are an important multiplication anchor.",
            anchor_a=None, anchor_b=None, anchor_answer=None, anchor_prompt="",
            second_equation="",
            combine_equation=f"5 groups of {size} = {product}",
            final_equation=f"5 × {size} = {product}",
            direct_message=f"See five equal groups of {size}. Together they make {product}.",
        )
    elif groups == 10:
        plan = CoachPlan(
            strategy_id="ten_anchor",
            groups=10, size=size, visual_groups=10, visual_mode="direct",
            first_groups=10, second_groups=0, operation="+",
            relationship="×10 is a powerful anchor: think in tens.",
            anchor_a=None, anchor_b=None, anchor_answer=None, anchor_prompt="",
            second_equation="",
            combine_equation=f"10 groups of {size} = {product}",
            final_equation=f"10 × {size} = {product}",
            direct_message=f"Ten equal groups of {size} make {product}.",
        )
    elif groups == 4:
        anchor = 2 * size
        plan = CoachPlan(
            strategy_id="double_double",
            groups=4, size=size, visual_groups=4, visual_mode="split_add",
            first_groups=2, second_groups=2, operation="+",
            relationship="Make 4 groups by doubling 2 groups.",
            anchor_a=2, anchor_b=size, anchor_answer=anchor,
            anchor_prompt="Start with a double you know",
            second_equation=f"Another 2 × {size} = {anchor}",
            combine_equation=f"{anchor} + {anchor} = {product}",
            final_equation=f"4 × {size} = {product}",
        )
    elif groups == 3:
        plan = _additive_plan(3, size, 2, 1, "double_plus_one")
    elif groups == 9:
        plan = _subtractive_plan(9, size, 1, "ten_minus_one")
    elif groups == 6:
        plan = _additive_plan(6, size, 5, 1, "five_plus_one")
    elif groups == 7:
        plan = _additive_plan(7, size, 5, 2, "five_plus_two")
    elif groups == 8:
        plan = _subtractive_plan(8, size, 2, "ten_minus_two")
    else:
        plan = CoachPlan(
            strategy_id="array",
            groups=groups, size=size, visual_groups=groups, visual_mode="direct",
            first_groups=groups, second_groups=0, operation="+",
            relationship=f"See {groups} equal groups of {size}.",
            anchor_a=None, anchor_b=None, anchor_answer=None, anchor_prompt="",
            second_equation="", combine_equation=f"{groups} groups of {size} = {product}",
            final_equation=f"{groups} × {size} = {product}", direct_message="Use the array to see the equal groups.",
        )

    # If the clearest model rotates the original fact, teach the commutative
    # connection explicitly and finish in the exact orientation the student saw.
    if (groups, size) != (a, b):
        relationship = f"Turn it around: {a} × {b} = {groups} × {size}. {plan.relationship}"
        plan = replace(plan, relationship=relationship, final_equation=f"{a} × {b} = {a * b}")
    else:
        plan = replace(plan, final_equation=f"{a} × {b} = {a * b}")
    return plan


def coach_plan_for_fact(fact) -> dict:
    """Return a JSON-friendly plan for any object with ``a`` and ``b``."""
    return coach_plan(int(fact.a), int(fact.b)).as_dict()
