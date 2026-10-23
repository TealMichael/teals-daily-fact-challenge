"""Compact teacher Results landing page; original detailed tools remain intact."""

from datetime import date, timedelta
import html

import streamlit as st

from fact_engine import current_daily_date
from igniter_presentation import teacher_can_present
from teacher_today_overview import load_today_lessons, today_reteach
from teacher_warmup_ui import (
    _warmup_email_recipients, _warmup_grouping, _warmup_report_text,
    _warmup_outlook_url,
)


def _date_label(day: date) -> str:
    return day.strftime('%A, %B %d').replace(' 0', ' ')


def render_results_overview(store) -> None:
    if not teacher_can_present():
        st.warning('Sign in as a teacher to view class results.')
        return
    st.markdown('### Results')
    st.caption('Check who finished the Igniter or Friday Quiz, see which skills need help, and open the familiar exports.')
    try:
        classes = list(store.list_classes())
    except Exception:
        st.warning('Class results are temporarily unavailable. Try Refresh data in Today.')
        return
    if not classes:
        st.info('Add a class in Manage to see results.')
        return
    by_id = {str(record.class_id): record for record in classes}
    ids = list(by_id)
    preferred = str(st.session_state.get('teacher_today_class_id') or '')
    if st.session_state.get('teacher_results_class') not in ids:
        st.session_state['teacher_results_class'] = preferred if preferred in ids else ids[0]
    left, right = st.columns(2)
    with left:
        class_id = st.selectbox('Class', ids, format_func=lambda cid: by_id[cid].class_name,
                                key='teacher_results_class')
    with right:
        day = st.date_input('Date', value=current_daily_date(), key='teacher_results_date')
    st.caption(_date_label(day))

    try:
        lesson = load_today_lessons(store, day, [by_id[class_id]])[0]
    except Exception:
        st.warning('Could not load student completion. Refresh and try again.')
        return
    if lesson.error:
        st.warning('The assignment or results could not be read. No scores have been changed.')
        return
    if lesson.assignment is None:
        st.info('No Igniter or Friday Quiz was assigned to this block on this date.')
    else:
        name = 'Friday Quiz' if lesson.kind == 'Quiz' else 'Igniter'
        finished = lesson.complete or 0
        students = lesson.students
        left, right, third = st.columns(3)
        with left:
            st.metric(f'{name} finished', f'{finished}/{lesson.total}')
        with right:
            st.metric('Still working / absent', max(0, lesson.total - finished))
        with third:
            if finished:
                correct_count = sum(bool(row.correct) for row in lesson.rows
                                    if str(row.student_id) in lesson.completed_ids)
                max_correct = finished * lesson.question_count
                st.metric('Accuracy', f'{correct_count / max_correct:.0%}' if max_correct else '—')
            else:
                st.metric('Accuracy', '—')

        pending = sorted((student.nickname for student in students
                          if str(student.student_id) not in lesson.completed_ids), key=str.casefold)
        if pending:
            st.markdown('**Not finished yet**')
            st.write(', '.join(pending))
        elif lesson.total:
            st.success('All students finished this activity.')

        needs = today_reteach(lesson)
        st.markdown('#### Standards to check')
        if needs:
            for group in needs:
                label = html.escape(str(group['code']))
                description = html.escape(str(group.get('description') or ''))
                st.markdown(f'**{label}**' + (f' · {description}' if description else ''))
                st.caption(', '.join(group['names']))
        elif finished:
            st.success('No standard-specific reteaching needs from completed work on this date.')
        else:
            st.caption('Standards will appear as students complete the activity.')

        if lesson.kind == 'Igniter' and lesson.rows:
            try:
                primary, secondary = _warmup_email_recipients(store, class_id)
                if primary:
                    report = _warmup_report_text(by_id[class_id], day, lesson.assignment,
                                                 _warmup_grouping(lesson.students, lesson.rows))
                    subject = f"Warm-Up Results — {by_id[class_id].class_name} — {day.strftime('%b %d')}"
                    st.link_button('Prepare Warm-Up Email in Outlook',
                                   _warmup_outlook_url(primary, secondary, subject, report),
                                   type='primary')
                    st.caption('Same Outlook draft and report format as before. You review it before sending.')
            except Exception:
                st.caption('The email is temporarily unavailable here; the original Warm-Up tool is below.')

    st.divider()
    st.markdown('#### More results and exports')
    first, second = st.columns(2)
    with first:
        if st.button('Warm-Up details & weekly CSV', key='results_open_warmup', width='stretch'):
            st.session_state['teacher_warmup_class'] = by_id[class_id].class_name
            st.session_state['teacher_warmup_date'] = day
            st.session_state['teacher_results_redirect'] = 'Warm-Up Details'
            st.rerun()
    with second:
        if st.button('Quiz scores & Skyward export', key='results_open_quiz', width='stretch'):
            friday = day + timedelta(days=(4 - day.weekday()) % 7)
            st.session_state['weekly_quiz_results_date'] = friday
            st.session_state[f'weekly_quiz_results_class_{friday}'] = by_id[class_id].class_name
            st.session_state['teacher_results_redirect'] = 'Quiz & Skyward'
            st.rerun()

