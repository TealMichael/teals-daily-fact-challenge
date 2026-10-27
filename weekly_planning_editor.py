from __future__ import annotations

"""Compact, always-open weekly question cards. Shared validators still own math."""

import random
import streamlit as st

from curriculum_question_types import comparison_symbol, sorted_order_items, order_display, ORDER_DIRECTIONS
from indiana_math_standards import BY_CODE
from indiana_question_bank import editor_question, questions_for_standard, question_by_id
from igniter_presentation import question_image_url
from warmup import QUESTION_TYPES
from weekly_quiz import QUIZ_QUESTION_TYPES
from weekly_planning import normalize_question, question_signature


# Teacher-facing names are intentionally shorter than the official summaries.
# The code and grade always remain visible; the stored value is still the code.
STANDARD_SKILL_NAMES = {
    '5.NS.1': 'Compare & Order Fractions and Decimals',
    '5.NS.2': 'Fractions as Division',
    '5.NS.3': 'Powers of 10 & Decimal Place Value',
    '5.NS.4': 'Percents & Equivalent Fractions',
    '5.NS.5': 'Rounding Decimals',
    '5.CA.1': 'Long Division with Two-Digit Divisors',
    '5.CA.2': 'Multiplication & Division Word Problems',
    '5.CA.3': 'Add & Subtract Unlike Fractions',
    '5.CA.4': 'Fraction Addition & Subtraction Problems',
    '5.CA.5': 'Multiply Fractions with Models',
    '5.CA.6': 'Divide Fractions with Models',
    '5.CA.7': 'Multiplying Fractions in Word Problems',
    '5.CA.8': 'Dividing Fractions in Word Problems',
    '5.CA.9': 'Decimal Operations',
    '5.CA.10': 'Decimal Word Problems',
    '5.CA.11': 'Ordered Pairs & Coordinate Plane',
    '5.G.1': 'Triangles, Circles, Radius & Diameter',
    '5.G.2': 'Classifying Polygons',
    '5.M.1': 'Measurement Conversions',
    '5.M.2': 'Area with Fractional Side Lengths',
    '5.M.3': 'Triangle, Parallelogram & Trapezoid Area',
    '5.M.4': 'Volume Using Unit Cubes',
    '5.M.5': 'Volume Formulas for Rectangular Prisms',
    '5.M.6': 'Composite Rectangular Prism Volume',
    '5.DA.1': 'Collecting, Graphing & Analyzing Data',
    '5.DA.2': 'Mean, Median & Mode',
    '6.NS.1': 'Positive & Negative Numbers in Context',
    '6.NS.2': 'Opposites & Rational Number Lines',
    '6.NS.3': 'Compare & Order Rational Numbers',
    '6.NS.4': 'Rational Number Word Problems',
    '6.NS.5': 'Order of Operations (PEMDAS/GEMDAS)',
    '6.NS.6': 'Greatest Common Factor & Least Common Multiple',
    '6.NS.7': 'Equivalent Linear Expressions',
    '6.NS.8': 'Exponents with Rational Numbers',
    '6.RP.1': 'Fractions, Decimals & Percents',
    '6.RP.2': 'Unit Rates',
    '6.RP.3': 'Equivalent Ratios with Tables & Graphs',
    '6.RP.4': 'Ratio & Rate Word Problems',
    '6.RP.5': 'Proportional Relationships',
    '6.AF.1': 'Expressions with Variables',
    '6.AF.2': 'Testing Equations & Inequalities',
    '6.AF.3': 'One-Step Equations',
    '6.AF.4': 'One-Variable Inequalities',
    '6.AF.5': 'Coordinates & Distances',
    '6.GM.1': 'Measurement Unit Conversions',
    '6.GM.2': 'Angle Sums in Triangles & Quadrilaterals',
    '6.GM.3': 'Area of Composite Polygons',
    '6.GM.4': 'Volume with Fractional Edge Lengths',
    '6.DS.1': 'Histograms, Box Plots & Line Plots',
    '6.DS.2': 'Statistical Questions & Data',
    '6.DS.3': 'Data Center, Spread & Shape',
    '7.NS.1': 'Adding Rational Numbers',
    '7.NS.2': 'Distance Between Rational Numbers',
    '7.NS.3': 'Multiplying Signed Numbers',
    '7.NS.4': 'Dividing Signed Numbers',
    '7.NS.5': 'Prime Factorization with Exponents',
    '7.NS.6': 'Squares & Square Roots',
    '7.NS.7': 'Rational Number Operations',
    '7.RP.1': 'Unit Rates & Constants of Proportionality',
    '7.RP.2': 'Multistep Percent Problems',
    '7.RP.3': 'Graphs & Equations of Proportions',
    '7.AF.1': 'Equivalent Linear Expressions & Factoring',
    '7.AF.2': 'Rational Number Word Problems',
    '7.AF.3': 'Two-Step Linear Equations',
    '7.AF.4': 'Linear Inequalities',
    '7.AF.5': 'Slope & Rate of Change',
    '7.AF.6': 'Graphing Lines with Slope',
    '7.GM.1': 'Scale Drawings',
    '7.GM.2': 'Circle Area & Circumference',
    '7.GM.3': 'Cylinder & Composite Figure Volume',
    '7.DSP.1': 'Random Samples & Populations',
    '7.DSP.2': 'Comparing Populations',
    '7.DSP.3': 'Distributions & Outliers',
    '7.DSP.4': 'Probability Scale',
    '7.DSP.5': 'Probability Models & Sample Spaces',
}

# Question cards have less space than the main search. Keep these labels
# short and distinctive; the full skill names remain in the weekly picker.
STANDARD_CARD_SKILL_NAMES = {
    '5.NS.1': 'Order Fractions & Decimals',
    '5.NS.3': 'Powers of 10 & Place Value',
    '5.NS.4': 'Percents & Fractions',
    '5.CA.1': 'Long Division (2-Digit)',
    '5.CA.2': 'Mult./Division Word Problems',
    '5.CA.3': 'Unlike-Fraction Add/Subtract',
    '5.CA.4': 'Fraction Add/Subtract Problems',
    '5.CA.7': 'Multiply Fractions: Problems',
    '5.CA.8': 'Divide Fractions: Problems',
    '5.CA.11': 'Coordinate Plane & Pairs',
    '5.G.1': 'Triangles & Circles',
    '5.M.2': 'Fractional Side-Length Area',
    '5.M.3': 'Polygon Area Formulas',
    '5.M.5': 'Volume Formulas',
    '5.M.6': 'Composite Prism Volume',
    '5.DA.1': 'Data Graphs & Analysis',
    '6.NS.1': 'Signed Numbers in Context',
    '6.NS.2': 'Opposites & Number Lines',
    '6.NS.3': 'Order Rational Numbers',
    '6.NS.5': 'Order of Operations (PEMDAS)',
    '6.NS.6': 'GCF & LCM',
    '6.NS.8': 'Rational Number Exponents',
    '6.RP.3': 'Ratio Tables & Graphs',
    '6.AF.2': 'Check Equations & Inequalities',
    '6.GM.2': 'Triangle & Quadrilateral Angles',
    '6.GM.4': 'Fractional-Edge Volume',
    '6.DS.1': 'Histograms & Box/Line Plots',
    '7.NS.2': 'Rational Number Distance',
    '7.NS.5': 'Prime Factorization',
    '7.RP.1': 'Unit Rates & Constants',
    '7.RP.3': 'Graph Proportions',
    '7.AF.1': 'Linear Expressions & Factoring',
    '7.GM.3': 'Cylinder & Composite Volumes',
    '7.DSP.5': 'Probability Models',
}

STANDARD_SEARCH_ALIASES = {
    '5.CA.1': ('division algorithm', 'long division', 'divide by two digit numbers'),
    '5.CA.2': ('multistep word problems', 'multiplication problems', 'remainder'),
    '5.NS.3': ('place value', 'multiply decimals by 10', 'divide decimals by 10'),
    '5.M.4': ('rectangular prism volume', 'unit cubes'),
    '5.M.5': ('rectangular prism volume', 'length times width times height'),
    '6.NS.5': ('PEMDAS', 'GEMDAS', 'BEDMAS', 'evaluate numerical expressions', 'parentheses', 'exponents'),
    '6.NS.6': ('GCF', 'LCM', 'factors and multiples'),
    '6.NS.7': ('distributive property', 'combine like terms'),
    '6.AF.1': ('substitution', 'evaluate algebraic expressions'),
    '7.NS.1': ('integer addition', 'adding integers'),
    '7.NS.3': ('integer multiplication', 'multiply integers'),
    '7.NS.4': ('integer division', 'divide integers'),
    '7.NS.7': ('integer operations', 'positive negative operations'),
    '7.AF.3': ('solving equations', 'two-step equations'),
}


def standard_skill_name(code):
    standard = BY_CODE.get(code)
    return STANDARD_SKILL_NAMES.get(code, standard.description.rstrip('.') if standard else str(code))


def standard_picker_label(code):
    if not code:
        return 'Choose skill'
    standard = BY_CODE.get(code)
    if standard is None:
        return str(code)  # Preserve previously saved unknown or legacy codes.
    return f'{standard_skill_name(code)} · Grade {standard.grade} · {code}'


def standard_question_card_label(code):
    if not code:
        return 'Choose skill'
    if code not in BY_CODE:
        return str(code)  # Previously saved custom codes must stay available.
    return f'{STANDARD_CARD_SKILL_NAMES.get(code, standard_skill_name(code))} · {code}'


def standard_matches_search(code, query):
    if not str(query or '').strip():
        return True
    standard = BY_CODE.get(code)
    if standard is None:
        return str(query).casefold().strip() in str(code).casefold()
    searchable = ' '.join((code, standard.domain, standard.description,
                           standard_skill_name(code), *STANDARD_SEARCH_ALIASES.get(code, ())))
    words = str(query).casefold().split()
    return all(word in searchable.casefold() for word in words)


def remember_recent_standards(state, codes):
    valid = [code for code in codes if code in BY_CODE]
    if not valid:
        return
    recent = list(dict.fromkeys([*valid, *state.get('recent_standard_codes', [])]))[:8]
    state['recent_standard_codes'] = recent
    # Session-local, isolated by block. Saved plans also retain current and
    # previous-week standards, so nothing new is written to Supabase.
    by_class = st.session_state.setdefault('weekly_planner_recent_by_class', {})
    by_class[str(state['plan']['class_id'])] = recent


PLANNER_CSS = '''<style>
/* Wider only while this teacher workspace is mounted. */
.block-container:has(.st-key-weekly-planner) {max-width:1180px!important}
.st-key-weekly-planner [data-testid="stVerticalBlock"] {gap:0.65rem}
.st-key-weekly-planner [data-testid="stWidgetLabel"] p {font-size:0.82rem}
.st-key-weekly-planner h3 {margin-bottom:.1rem}
.st-key-weekly-planner h4 {font-size:1.25rem;padding:.1rem 0}
.st-key-weekly-planner .wp-card-title {font-size:1rem;line-height:1.4;font-weight:700;color:#17564e;padding-bottom:4px}
.st-key-weekly-planner .stMarkdown [data-testid="stMarkdownContainer"]:has(h3,h4,.wp-card-title) {margin-bottom:0}
.st-key-weekly-planner [class*="st-key-wp_card"] {border-color:#d9e5df;border-radius:12px;background:#fff;padding:1rem}
.st-key-weekly-planner [data-testid="stFileUploaderDropzone"] {min-height:40px;padding:4px 8px;justify-content:flex-end}
.st-key-weekly-planner [data-testid="stFileUploaderDropzoneInstructions"] {display:none}
.st-key-weekly-planner [data-testid="stFileUploaderDropzone"] button {min-height:30px;padding:2px 12px}
.st-key-weekly-planner [data-testid="stCaptionContainer"] p {font-size:.8rem}
.wp-summary {border:1px solid #d9e5df;border-radius:12px;padding:18px 22px;margin:8px 0 18px;background:#fff}
.wp-summary .wp-question {font-size:1.05rem;line-height:1.5;padding:12px 0}
.wp-summary .wp-answer {color:#17564e;background:#f0f6f2;padding:8px 12px;border-radius:6px;margin-top:8px}
.wp-summary img {display:block;max-width:100%;max-height:190px;object-fit:contain;margin:10px 0}
.wp-summary .compare {display:flex;gap:1em;align-items:center;padding:8px 0}
.wp-summary .tiles {display:flex;gap:.5em;flex-wrap:wrap;padding:8px 0}
.wp-summary .tiles>span {border:1px solid #d9e5df;border-radius:5px;padding:4px 8px}
.wp-summary .fraction {display:inline-flex;flex-direction:column;text-align:center;vertical-align:middle;line-height:1.1;margin:0 .15em}
.wp-summary .fraction>span:first-child {border-bottom:1px solid currentColor}
@media(max-width:700px) {.st-key-weekly-planner [data-testid="stHorizontalBlock"] {flex-wrap:wrap}}
</style>'''


def mark_edited(state):
    state.pop('publish_request', None)
    state.pop('publish_error', None)
    state.pop('notice', None)


def question_changed(state, day_index, slot_index, field, key, parser=None):
    value = st.session_state[key]
    question = state['plan']['days'][day_index]['questions'][slot_index]
    old_type = question.get('question_type')
    question[field] = parser(value) if parser else value
    if field == 'standard_code':
        standard = BY_CODE.get(value)
        question['standard_description'] = standard.description if standard else ''
        remember_recent_standards(state, [value])
    if field == 'question_type' and old_type in {'Compare Values', 'Order Tiles'} and value != old_type:
        question['correct_answer'] = ''
        state.setdefault('question_epochs', {})[(day_index, slot_index)] = state.get('question_epochs', {}).get((day_index, slot_index), 0) + 1
    mark_edited(state)


def _lines(value):
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _alternates(value):
    return [part.strip() for part in str(value).split(';') if part.strip()]


def replace_question(state, day_index, slot_index, key):
    choice = st.session_state.get(key)
    if not choice:
        return
    day = state['plan']['days'][day_index]
    current = day['questions'][slot_index]
    if choice == '__random__':
        used = {question_signature(q) for activity in state['plan']['days'] for q in activity['questions'] if q.get('prompt')}
        types = QUESTION_TYPES if day['kind'] == 'igniter' else QUIZ_QUESTION_TYPES
        candidates = [row for row in questions_for_standard(current.get('standard_code', ''))
                      if row.get('question_type') in types and question_signature(editor_question(row)) not in used]
        if not candidates:
            state['notice'] = 'Every available question for this standard is already in the week. Choose a bank question explicitly or edit the text.'
            return
        selected = random.SystemRandom().choice(candidates)
    else:
        selected = question_by_id(choice)
    if not selected:
        return
    day['questions'][slot_index] = normalize_question(editor_question(selected), day['kind'], slot_index + 1)
    state.setdefault('pending_images', {}).pop((day_index, slot_index), None)
    epochs = state.setdefault('question_epochs', {})
    epochs[(day_index, slot_index)] = epochs.get((day_index, slot_index), 0) + 1
    mark_edited(state)


def image_changed(state, day_index, slot_index, key):
    upload = st.session_state.get(key)
    if upload is not None:
        state.setdefault('pending_images', {})[(day_index, slot_index)] = upload.getvalue()
        mark_edited(state)


def remove_image(state, day_index, slot_index):
    question = state['plan']['days'][day_index]['questions'][slot_index]
    question.update(image_path='', bank_image_path='', image_alt='Question diagram', bank_image_alt='Built-in question diagram')
    state.setdefault('pending_images', {}).pop((day_index, slot_index), None)
    epochs = state.setdefault('question_epochs', {})
    epochs[(day_index, slot_index)] = epochs.get((day_index, slot_index), 0) + 1
    mark_edited(state)


def render_question_card(store, state, day_index, slot_index, prefix, *, disabled=False):
    day = state['plan']['days'][day_index]
    q = day['questions'][slot_index]
    epoch = state.get('question_epochs', {}).get((day_index, slot_index), 0)
    base = f'{prefix}::q{day_index}_{slot_index}::{epoch}'
    types = list(QUESTION_TYPES if day['kind'] == 'igniter' else QUIZ_QUESTION_TYPES)
    qtype = q.get('question_type') or 'Number'

    def text(field, label, *, area=False, parser=None, value=None, **kwargs):
        key = f'{base}::{field}'
        current = q.get(field, '') if value is None else value
        widget = st.text_area if area else st.text_input
        return widget(label, value=str(current or ''), key=key, disabled=disabled,
                      on_change=question_changed, args=(state, day_index, slot_index, field, key, parser), **kwargs)

    with st.container(border=True, key=f'wp_card_{day_index}_{slot_index}'):
        st.markdown(f'<div class="wp-card-title" role="heading" aria-level="5">Question {slot_index + 1}</div>', unsafe_allow_html=True)
        text('prompt', 'Question', area=True, height=88, label_visibility='collapsed', placeholder='Write a question, or choose one from the bank below.')
        type_col, answer_col = st.columns([1, 1.25])
        with type_col:
            type_key = base + '::question_type'
            st.selectbox('Answer type', types, index=types.index(qtype) if qtype in types else types.index('Number'),
                         key=type_key, disabled=disabled, on_change=question_changed,
                         args=(state, day_index, slot_index, 'question_type', type_key))
        with answer_col:
            if qtype == 'Compare Values':
                st.caption('Correct answer')
                symbol = comparison_symbol(q.get('compare_left', ''), q.get('compare_right', ''))
                st.write(f"{q.get('compare_left', '')} {symbol or '?'} {q.get('compare_right', '')}")
            elif qtype == 'Order Tiles':
                direction_key = base + '::order_direction'
                direction = q.get('order_direction') or ORDER_DIRECTIONS[0]
                st.selectbox('Order', ORDER_DIRECTIONS, index=ORDER_DIRECTIONS.index(direction), key=direction_key,
                             disabled=disabled, on_change=question_changed,
                             args=(state, day_index, slot_index, 'order_direction', direction_key))
            else:
                text('correct_answer', 'Answer · Part 1' if qtype == 'Multi-Part — 2 answers' else 'Correct answer')
        if qtype == 'Compare Values':
            a, b = st.columns(2)
            with a: text('compare_left', 'Left value')
            with b: text('compare_right', 'Right value')
        elif qtype == 'Order Tiles':
            text('order_items', 'Tiles · separate with semicolons', value='; '.join(q.get('order_items') or []), parser=_alternates)
            try:
                st.caption('Answer: ' + order_display(sorted_order_items(q.get('order_items') or [], q.get('order_direction') or ORDER_DIRECTIONS[0]), q.get('order_direction') or ORDER_DIRECTIONS[0]))
            except ValueError:
                if q.get('order_items'): st.caption('Use 3–6 valid numbers, fractions, or decimals.')
        elif qtype == 'Multiple choice':
            text('options', 'Choices · one per line', value='\n'.join(q.get('options') or []), area=True, height=100, parser=_lines)
        elif qtype == 'Number + Label':
            a, b = st.columns(2)
            with a: text('correct_label', 'Correct unit')
            with b: text('label_options', 'Unit choices · separate with semicolons', value='; '.join(q.get('label_options') or []), parser=_alternates)
        elif qtype == 'Multi-Part — 2 answers':
            text('correct_answer_two', 'Answer · Part 2')

        standard_col, bank_col = st.columns([1.5, 1])
        with standard_col:
            code = q.get('standard_code') or ''
            selected_codes = state['plan']['standards'] if day_index < 4 else state['plan']['quiz_standards']
            recent_codes = state.get('recent_standard_codes', [])
            codes = list(dict.fromkeys(['', *selected_codes, *recent_codes,
                                         *[c for c, s in BY_CODE.items() if s.grade in (5, 6, 7)], code]))
            standard_key = base + '::standard_code'
            st.selectbox('Standard', codes, index=codes.index(code), format_func=standard_question_card_label,
                         key=standard_key, disabled=disabled,
                         help='Search by skill name or standard code. ' + (BY_CODE[code].description if code in BY_CODE else 'Choose the skill assessed by this question.'),
                         on_change=question_changed, args=(state, day_index, slot_index, 'standard_code', standard_key))
        with bank_col:
            rows = [row for row in questions_for_standard(code) if row.get('question_type') in types]
            labels = {str(row['id']): f"Q{row.get('question_number', '')} · {row['prompt']}" for row in rows}
            options = ['', '__random__', *labels] if rows else ['']
            bank_key = base + '::bank::' + code
            st.selectbox('Replace from bank', options, format_func=lambda value: labels.get(value, 'Another random question' if value else 'Keep this question'),
                         key=bank_key, disabled=disabled or not rows,
                         on_change=replace_question, args=(state, day_index, slot_index, bank_key))

        if qtype not in {'Compare Values', 'Order Tiles', 'Multiple choice'}:
            a, b = st.columns([1.5, 1])
            with a:
                text('accepted_answers', 'Also accept · optional', value='; '.join(q.get('accepted_answers') or []), parser=_alternates,
                     placeholder='Separate answers with semicolons', help='Equivalent numbers and fractions already match automatically.')
            image_column = b
        else:
            image_column = st.container()
        with image_column:
            image_key = base + '::image'
            st.file_uploader('Image · optional', type=['png', 'jpg', 'jpeg', 'webp'], key=image_key, disabled=disabled,
                             on_change=image_changed, args=(state, day_index, slot_index, image_key))
        if qtype == 'Multi-Part — 2 answers':
            text('accepted_answers_two', 'Also accept for Part 2 · optional', value='; '.join(q.get('accepted_answers_two') or []), parser=_alternates)
        if q.get('image_path') or q.get('bank_image_path'):
            image = question_image_url(store, q)
            if image: st.image(image, width=230)
            else: st.caption('Image unavailable. Choose a replacement before class.')
            a, b = st.columns([2, 1], vertical_alignment='bottom')
            with a: text('image_alt', 'Image description', value=q.get('image_alt') or q.get('bank_image_alt') or 'Question diagram')
            with b:
                st.button('Remove image', key=base+'::remove_image', disabled=disabled,
                          on_click=remove_image, args=(state, day_index, slot_index))
