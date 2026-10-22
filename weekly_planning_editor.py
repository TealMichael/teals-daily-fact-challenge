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

        standard_col, bank_col = st.columns([1, 1.6])
        with standard_col:
            code = q.get('standard_code') or ''
            selected_codes = state['plan']['standards'] if day_index < 4 else state['plan']['quiz_standards']
            codes = list(dict.fromkeys(['', *selected_codes, *[c for c, s in BY_CODE.items() if s.grade in (5, 6, 7)], code]))
            standard_key = base + '::standard_code'
            st.selectbox('Standard', codes, index=codes.index(code), format_func=lambda value: value or 'Choose skill',
                         key=standard_key, disabled=disabled, help=BY_CODE[code].description if code in BY_CODE else 'Choose the skill assessed by this question.',
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
