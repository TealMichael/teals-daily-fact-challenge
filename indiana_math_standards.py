from __future__ import annotations

"""Curated 2023 Indiana Academic Standards for Mathematics, Grades 4–7.

The app uses concise teacher-facing skill summaries so the standards picker stays
readable on a classroom dashboard.  Codes/domain/grade are the official 2023
Indiana Mathematics content-standard identifiers; Process Standards are kept
separate and intentionally are not included in the Warm-Up picker.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndianaMathStandard:
    grade: int
    code: str
    domain: str
    description: str

    @property
    def label(self) -> str:
        return f"Grade {self.grade} · {self.code} — {self.description}"


S = IndianaMathStandard

STANDARDS: tuple[IndianaMathStandard, ...] = (
    # Grade 4 — Number Sense
    S(4, "4.NS.1", "Number Sense", "Read, write, and represent whole numbers through 1,000,000."),
    S(4, "4.NS.2", "Number Sense", "Model mixed numbers and improper fractions and connect them to equivalent forms."),
    S(4, "4.NS.3", "Number Sense", "Recognize and generate equivalent fractions using visual models and reasoning."),
    S(4, "4.NS.4", "Number Sense", "Compare fractions with different numerators and denominators and justify the comparison."),
    S(4, "4.NS.5", "Number Sense", "Represent tenths and hundredths as fractions and decimals and connect equivalent forms."),
    S(4, "4.NS.6", "Number Sense", "Compare decimals through hundredths and justify the comparison."),
    S(4, "4.NS.7", "Number Sense", "Round multi-digit whole numbers to any place."),
    # Grade 4 — Computation and Algebraic Thinking
    S(4, "4.CA.1", "Computation & Algebraic Thinking", "Multiply multi-digit whole numbers using place value and properties of operations."),
    S(4, "4.CA.2", "Computation & Algebraic Thinking", "Find whole-number quotients and remainders with up to four-digit dividends and one-digit divisors."),
    S(4, "4.CA.3", "Computation & Algebraic Thinking", "Use the commutative, associative, and distributive properties of multiplication."),
    S(4, "4.CA.4", "Computation & Algebraic Thinking", "Find factor pairs and recognize factors and multiples within 100."),
    S(4, "4.CA.5", "Computation & Algebraic Thinking", "Solve multiplicative-comparison problems."),
    S(4, "4.CA.6", "Computation & Algebraic Thinking", "Add and subtract fractions with common denominators and decompose fractions."),
    S(4, "4.CA.7", "Computation & Algebraic Thinking", "Add and subtract mixed numbers with common denominators."),
    S(4, "4.CA.8", "Computation & Algebraic Thinking", "Solve real-world problems involving addition and subtraction of fractions with common denominators."),
    S(4, "4.CA.9", "Computation & Algebraic Thinking", "Generate and analyze number patterns and relationships between terms."),
    # Grade 4 — Geometry
    S(4, "4.G.1", "Geometry", "Identify and describe parallelograms, rhombuses, and trapezoids."),
    S(4, "4.G.2", "Geometry", "Identify rays, angle types, and parallel and perpendicular lines."),
    S(4, "4.G.3", "Geometry", "Classify triangles and quadrilaterals by properties of lines and angles."),
    # Grade 4 — Measurement
    S(4, "4.M.1", "Measurement", "Measure length to fractional inches and millimeters."),
    S(4, "4.M.2", "Measurement", "Convert larger measurement units to smaller units within customary, metric, and time systems."),
    S(4, "4.M.3", "Measurement", "Solve real-world measurement problems using the four operations."),
    S(4, "4.M.4", "Measurement", "Find area and perimeter of rectangles and area of composite rectilinear figures."),
    S(4, "4.M.5", "Measurement", "Understand angle measure in degrees."),
    S(4, "4.M.6", "Measurement", "Measure and sketch angles in whole-number degrees."),
    # Grade 4 — Data Analysis
    S(4, "4.DA.1", "Data Analysis", "Collect, organize, graph, and analyze data using appropriate displays."),
    S(4, "4.DA.2", "Data Analysis", "Use line plots with fractional measurements to solve addition and subtraction problems."),

    # Grade 5 — Number Sense
    S(5, "5.NS.1", "Number Sense", "Compare and order fractions, mixed numbers, and decimals through thousandths."),
    S(5, "5.NS.2", "Number Sense", "Interpret fractions as part-whole relationships, sets, and division."),
    S(5, "5.NS.3", "Number Sense", "Use powers of 10 and explain decimal place-value patterns."),
    S(5, "5.NS.4", "Number Sense", "Model percents as parts of 100 and connect percents to equivalent fractions."),
    S(5, "5.NS.5", "Number Sense", "Round decimals through thousandths."),
    # Grade 5 — Computation and Algebraic Thinking
    S(5, "5.CA.1", "Computation & Algebraic Thinking", "Divide whole numbers with up to four-digit dividends and two-digit divisors."),
    S(5, "5.CA.2", "Computation & Algebraic Thinking", "Solve real-world whole-number multiplication and division problems, including remainders."),
    S(5, "5.CA.3", "Computation & Algebraic Thinking", "Add and subtract fractions and mixed numbers with unlike denominators."),
    S(5, "5.CA.4", "Computation & Algebraic Thinking", "Solve real-world fraction addition and subtraction problems and assess reasonableness."),
    S(5, "5.CA.5", "Computation & Algebraic Thinking", "Use visual models to multiply fractions by fractions and whole numbers."),
    S(5, "5.CA.6", "Computation & Algebraic Thinking", "Use visual models to divide fractions by fractions and whole numbers."),
    S(5, "5.CA.7", "Computation & Algebraic Thinking", "Solve real-world problems involving multiplication of fractions and mixed numbers."),
    S(5, "5.CA.8", "Computation & Algebraic Thinking", "Solve real-world problems involving division of fractions and mixed numbers."),
    S(5, "5.CA.9", "Computation & Algebraic Thinking", "Add, subtract, multiply, and divide decimals through hundredths using place value and properties."),
    S(5, "5.CA.10", "Computation & Algebraic Thinking", "Solve real-world decimal-operation problems, including money."),
    S(5, "5.CA.11", "Computation & Algebraic Thinking", "Use ordered pairs in the first quadrant to represent and solve real-world problems."),
    # Grade 5 — Geometry
    S(5, "5.G.1", "Geometry", "Classify triangles and circles and use the relationship between radius and diameter."),
    S(5, "5.G.2", "Geometry", "Classify polygons in a hierarchy based on their properties."),
    # Grade 5 — Measurement
    S(5, "5.M.1", "Measurement", "Convert measurement units within a system to solve multi-step problems."),
    S(5, "5.M.2", "Measurement", "Find areas of rectangles with fractional side lengths using models and multiplication."),
    S(5, "5.M.3", "Measurement", "Use area formulas for triangles, parallelograms, and trapezoids."),
    S(5, "5.M.4", "Measurement", "Understand volume of right rectangular prisms using unit cubes and edge lengths."),
    S(5, "5.M.5", "Measurement", "Use volume formulas for right rectangular prisms."),
    S(5, "5.M.6", "Measurement", "Find volume of composite figures made of right rectangular prisms."),
    # Grade 5 — Data Analysis
    S(5, "5.DA.1", "Data Analysis", "Formulate questions and collect, organize, graph, and analyze categorical and numerical data."),
    S(5, "5.DA.2", "Data Analysis", "Find and interpret mean, median, and mode and choose an appropriate measure of center."),

    # Grade 6 — Number Sense
    S(6, "6.NS.1", "Number Sense", "Use positive and negative numbers to represent quantities in real-world contexts."),
    S(6, "6.NS.2", "Number Sense", "Understand opposites and locate rational numbers on a number line."),
    S(6, "6.NS.3", "Number Sense", "Compare and order rational numbers and interpret comparisons in context."),
    S(6, "6.NS.4", "Number Sense", "Solve real-world problems with positive fractions and decimals using one or two operations."),
    S(6, "6.NS.5", "Number Sense", "Use order of operations and properties with nonnegative rational numbers and exponents."),
    S(6, "6.NS.6", "Number Sense", "Find greatest common factors and least common multiples and use the distributive property."),
    S(6, "6.NS.7", "Number Sense", "Create and justify equivalent linear expressions using properties of operations."),
    S(6, "6.NS.8", "Number Sense", "Evaluate positive rational numbers raised to whole-number exponents."),
    # Grade 6 — Ratios and Proportional Relationships
    S(6, "6.RP.1", "Ratios & Proportional Relationships", "Convert among fractions, decimals, and percents."),
    S(6, "6.RP.2", "Ratios & Proportional Relationships", "Understand and calculate unit rates."),
    S(6, "6.RP.3", "Ratios & Proportional Relationships", "Use tables and graphs to represent equivalent ratios."),
    S(6, "6.RP.4", "Ratios & Proportional Relationships", "Solve rate and ratio problems using models and strategies."),
    S(6, "6.RP.5", "Ratios & Proportional Relationships", "Represent proportional relationships with variables, equations, tables, and graphs."),
    # Grade 6 — Algebra and Functions
    S(6, "6.AF.1", "Algebra & Functions", "Write and evaluate expressions with multiple variables."),
    S(6, "6.AF.2", "Algebra & Functions", "Use substitution to determine whether values make equations or inequalities true."),
    S(6, "6.AF.3", "Algebra & Functions", "Solve one-step equations and related real-world problems."),
    S(6, "6.AF.4", "Algebra & Functions", "Write, solve, and graph one-variable inequalities."),
    S(6, "6.AF.5", "Algebra & Functions", "Use rational-number coordinates and find distances between points sharing an x- or y-coordinate."),
    # Grade 6 — Geometry and Measurement
    S(6, "6.GM.1", "Geometry & Measurement", "Convert between customary and metric measurement units in real-world problems."),
    S(6, "6.GM.2", "Geometry & Measurement", "Use angle-sum relationships in triangles and quadrilaterals."),
    S(6, "6.GM.3", "Geometry & Measurement", "Find area of complex polygonal figures by decomposing them into simpler shapes."),
    S(6, "6.GM.4", "Geometry & Measurement", "Find volume of right rectangular prisms with fractional edge lengths."),
    # Grade 6 — Data and Statistics
    S(6, "6.DS.1", "Data & Statistics", "Select, create, and interpret line plots, histograms, and box plots."),
    S(6, "6.DS.2", "Data & Statistics", "Pose statistical questions and collect, organize, display, and interpret data."),
    S(6, "6.DS.3", "Data & Statistics", "Summarize numerical data using center, spread, shape, and context."),

    # Grade 7 — Number Sense
    S(7, "7.NS.1", "Number Sense", "Add rational numbers and interpret sums using additive inverses."),
    S(7, "7.NS.2", "Number Sense", "Find distance between rational numbers using absolute difference."),
    S(7, "7.NS.3", "Number Sense", "Multiply signed numbers using properties of operations."),
    S(7, "7.NS.4", "Number Sense", "Divide signed numbers and interpret equivalent forms of negative fractions."),
    S(7, "7.NS.5", "Number Sense", "Write prime factorizations using exponents."),
    S(7, "7.NS.6", "Number Sense", "Evaluate squares and square roots of perfect squares."),
    S(7, "7.NS.7", "Number Sense", "Compute fluently with rational numbers."),
    # Grade 7 — Ratios and Proportional Relationships
    S(7, "7.RP.1", "Ratios & Proportional Relationships", "Determine unit rates and constants of proportionality."),
    S(7, "7.RP.2", "Ratios & Proportional Relationships", "Solve multistep ratio and percent problems, including markup, discount, tax, and percent change."),
    S(7, "7.RP.3", "Ratios & Proportional Relationships", "Represent proportional relationships with equations and graphs, including y = mx."),
    # Grade 7 — Algebra and Functions
    S(7, "7.AF.1", "Algebra & Functions", "Create equivalent linear expressions, including by factoring."),
    S(7, "7.AF.2", "Algebra & Functions", "Solve real-world problems with rational numbers using one or two operations."),
    S(7, "7.AF.3", "Algebra & Functions", "Solve linear equations of the forms px + q = r and p(x + q) = r."),
    S(7, "7.AF.4", "Algebra & Functions", "Solve and graph linear inequalities."),
    S(7, "7.AF.5", "Algebra & Functions", "Interpret slope and distinguish constant and varying rates of change."),
    S(7, "7.AF.6", "Algebra & Functions", "Graph a line from a slope and point and determine slope from a graph."),
    # Grade 7 — Geometry and Measurement
    S(7, "7.GM.1", "Geometry & Measurement", "Use scale drawings and proportional reasoning to solve problems."),
    S(7, "7.GM.2", "Geometry & Measurement", "Use formulas for circumference and area of circles."),
    S(7, "7.GM.3", "Geometry & Measurement", "Find volume of cylinders and composite three-dimensional figures."),
    # Grade 7 — Data, Statistics, and Probability
    S(7, "7.DSP.1", "Data, Statistics & Probability", "Use representative and random samples to draw conclusions about populations."),
    S(7, "7.DSP.2", "Data, Statistics & Probability", "Use measures of center and spread to compare populations."),
    S(7, "7.DSP.3", "Data, Statistics & Probability", "Compare distributions and describe the effect of overlap and outliers."),
    S(7, "7.DSP.4", "Data, Statistics & Probability", "Interpret probability from 0 to 1 and describe likelihood."),
    S(7, "7.DSP.5", "Data, Statistics & Probability", "Develop probability models and sample spaces for chance events."),
)

BY_CODE = {standard.code: standard for standard in STANDARDS}
CUSTOM_CODE = "__CUSTOM__"


def standard_by_code(code: str) -> IndianaMathStandard | None:
    return BY_CODE.get(str(code or "").strip())


def grade_from_standard_code(code: str) -> int | None:
    standard = standard_by_code(code)
    if standard is not None:
        return standard.grade
    text = str(code or "").strip()
    try:
        grade = int(text.split(".", 1)[0])
    except (ValueError, IndexError):
        return None
    return grade if grade in (4, 5, 6, 7) else None


def ordered_standard_codes(recent_codes=()) -> list[str]:
    recent = []
    seen = set()
    for code in recent_codes or ():
        code = str(code or "").strip()
        if code in BY_CODE and code not in seen:
            recent.append(code)
            seen.add(code)
    return recent + [standard.code for standard in STANDARDS if standard.code not in seen]


def display_label(code: str, recent_codes=()) -> str:
    if code == CUSTOM_CODE:
        return "Other / Custom standard"
    standard = standard_by_code(code)
    if standard is None:
        return str(code)
    prefix = "★ Recently used · " if code in set(recent_codes or ()) else ""
    return prefix + standard.label
