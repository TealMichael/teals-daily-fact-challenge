from __future__ import annotations

"""One continuous teacher planning sheet, followed by an explicit review page."""

from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
import html
import json
from time import monotonic
from uuid import uuid4

import streamlit as st

from fact_engine import current_daily_date
from igniter_presentation import teacher_can_present, question_html, answer_text, math_text, question_image_url
from indiana_math_standards import BY_CODE
from indiana_question_bank import standard_codes_for
from question_images import maybe_cleanup_question_images, upload_question_image
from planning_question_images import question_for_date
from teacher_planning import monday_for
from weekly_planning import (new_plan, plan_repository, suggest_questions, normalize_question,
                             validate_plan, duplicate_slots, content, state_label)
from weekly_planning_editor import (PLANNER_CSS, render_question_card, mark_edited,
                                    standard_picker_label, standard_skill_name,
                                    standard_matches_search, remember_recent_standards)
from weekly_planning_bulk import preview_targets, publish_targets


def _message(exc):
    message = str(getattr(exc, 'message', '') or exc)
    if any(token in message for token in ('PGRST202', 'PGRST205', 'schema cache', 'does not exist')):
        return 'Weekly Planning needs the v2.25.1 SQL update. Existing classroom activities and Display Igniter remain available.'
    return message if len(message) < 650 else 'The draft could not save. Your edits are still here; try saving again.'


def _accept_record(state, record):
    state['plan'] = deepcopy(record['plan'])
    state['saved_plan'] = deepcopy(record['plan'])
    state['revision'] = record['revision']
    state.pop('save_error', None)


def _canonical_draft(plan):
    result = deepcopy(plan)
    for day in result['days']:
        for slot, q in enumerate(day['questions'], 1):
            try:
                day['questions'][slot-1] = normalize_question(q, day['kind'], slot)
            except (ValueError, TypeError):
                # Incomplete edits are valid drafts, but can never be published.
                pass
    return result


def _save_draft(repository, state, *, force=False):
    plan = _canonical_draft(state['plan'])
    if not force and plan == state['saved_plan']:
        return not state.get('save_error')
    try:
        record = repository.save(plan, state['revision'])
    except Exception as exc:
        # A timeout can follow a committed write. Recover only an identical plan;
        # a different concurrent draft must never be silently overwritten.
        try:
            current = repository.load(plan['class_id'], plan['week_start'])
        except Exception:
            current = None
        if current and current['plan'] == plan and current['revision'] > state['revision']:
            _accept_record(state, current)
            return True
        state['save_error'] = _message(exc)
        return False
    _accept_record(state, record)
    return True


def _upload_pending_images(store, state):
    pending = state.setdefault('pending_images', {})
    for (day_index, slot_index), data in list(pending.items()):
        item = state['plan']['days'][day_index]
        try:
            path = upload_question_image(store, BytesIO(data), question_date=date.fromisoformat(item['date']),
                                         kind=item['kind'], slot=slot_index+1)
        except Exception as exc:
            state['image_error'] = _message(exc)
            return False
        item['questions'][slot_index]['image_path'] = path
        del pending[(day_index, slot_index)]
    state.pop('image_error', None)
    return True


def _flush_working_drafts(store, repository):
    # A text-field blur and a classroom/week change can arrive in one request.
    # Persist the departing sheet too, before rendering the newly selected one.
    failed = []
    for key in list(st.session_state):
        if not key.startswith('weekly_planner::'):
            continue
        state = st.session_state[key]
        if not isinstance(state, dict) or 'plan' not in state or 'saved_plan' not in state:
            continue
        if _upload_pending_images(store, state) and not state.get('save_error'):
            _save_draft(repository, state)
        if state.get('save_error') or state.get('image_error'):
            failed.append(key)
    return failed


def _setting_changed(state, field, key):
    state['plan'][field] = st.session_state[key]
    if field in ('standards', 'quiz_standards'):
        remember_recent_standards(state, st.session_state[key])
    mark_edited(state)


def _add_recent_standard(state, field, code, widget_key):
    selected = state['plan'][field]
    if code not in BY_CODE or code in selected:
        return
    chosen = [*selected, code]
    state['plan'][field] = chosen
    st.session_state[widget_key] = chosen
    remember_recent_standards(state, [code])
    mark_edited(state)


def _day_changed(state, index, key):
    state['plan']['days'][index]['enabled'] = not st.session_state[key]
    mark_edited(state)


def _quiz_setting(state, field, key):
    state['plan']['days'][4][field] = st.session_state[key]
    mark_edited(state)


def _change_view(state, view):
    state['view'] = view
    state['scroll_to_top'] = uuid4().hex


def _fill_week(state):
    previous = deepcopy(state['plan'])
    proposed, warnings = suggest_questions(previous)
    state['plan'] = proposed
    epochs = state.setdefault('question_epochs', {})
    for i, (old, new) in enumerate(zip(previous['days'], proposed['days'])):
        for j, (before, after) in enumerate(zip(old['questions'], new['questions'])):
            if before != after:
                epochs[(i, j)] = epochs.get((i, j), 0) + 1
    state['suggestion_warnings'] = warnings
    mark_edited(state)


def _readonly_days(store, state):
    stamp = (current_daily_date().isoformat(), tuple(x['id'] if x else None for x in state['plan']['baseline']))
    cache = state.get('lock_cache')
    if cache and cache['stamp'] == stamp and monotonic() - cache['time'] < 20:
        return cache['reasons']
    reasons = {}
    for index, item in enumerate(state['plan']['days']):
        if date.fromisoformat(item['date']) < current_daily_date():
            reasons[index] = 'Past date · published work is kept'
        elif baseline := state['plan']['baseline'][index]:
            try:
                locked = store.warmup_set_locked(baseline['id']) if index < 4 else store.weekly_quiz_locked(baseline['id'])
                if locked:
                    reasons[index] = 'Student work started · published questions are locked'
            except Exception:
                reasons[index] = 'Assignment status unavailable · reload to try again'
    state['lock_cache'] = {'stamp': stamp, 'time': monotonic(), 'reasons': reasons}
    return reasons


def _swap_questions(store, state, source_key, target_key):
    source, target = st.session_state[source_key], st.session_state[target_key]
    if source == target:
        return
    # Check again at the action boundary; the publish RPC remains authoritative.
    state.pop('lock_cache', None)
    locked = _readonly_days(store, state)
    if source[0] in locked or target[0] in locked:
        state['notice'] = 'These questions are locked. Choose an unstarted activity.'
        return
    a, b = state['plan']['days'][source[0]], state['plan']['days'][target[0]]
    if a['kind'] != b['kind']:
        return
    try:
        here = question_for_date(store, b['questions'][target[1]], date.fromisoformat(a['date']), a['kind'], source[1]+1)
        there = question_for_date(store, a['questions'][source[1]], date.fromisoformat(b['date']), b['kind'], target[1]+1)
    except Exception:
        state['notice'] = 'The image could not move. Both questions are unchanged; retry or replace the image.'
        return
    a['questions'][source[1]], b['questions'][target[1]] = here, there
    epochs = state.setdefault('question_epochs', {})
    for pair in (source, target):
        epochs[pair] = epochs.get(pair, 0) + 1
    mark_edited(state)


def _save_problem_controls(repository, state, prefix):
    error = state.get('image_error') or state.get('save_error')
    if not error:
        return
    st.error('Draft not saved. ' + error)
    a, b = st.columns(2)
    with a:
        if st.button('Retry saving draft', key=prefix+'retry'):
            state.pop('save_error', None)
            st.rerun()
    with b:
        st.download_button('Keep a copy of my edits', json.dumps(state['plan'], indent=2),
                           file_name=f"weekly-plan-{state['plan']['week_start']}.json", mime='application/json', key=prefix+'copy')
    discard = st.checkbox('Discard my edits and load the saved draft', key=prefix+'discard')
    if st.button('Load saved draft', disabled=not discard, key=prefix+'reload'):
        try:
            record = repository.load(state['plan']['class_id'], state['plan']['week_start'])
            if record:
                _accept_record(state, record)
                state['editor_epoch'] = state.get('editor_epoch', 0)+1
                state['pending_images'] = {}
                state.pop('image_error', None)
                state.pop('publish_request', None)
                st.rerun()
        except Exception as exc:
            st.error(_message(exc))


def _render_standards(state, prefix):
    plan = state['plan']
    left, right = st.columns(2, gap='large')
    for column, grade_field, codes_field, title, label in (
        (left, 'grade', 'standards', 'Monday–Thursday · Igniters', "This week's standards"),
        (right, 'quiz_grade', 'quiz_standards', 'Friday · Quiz of the Week', 'Previously taught standards')):
        with column:
            st.markdown('#### '+title)
            grade_key = prefix + grade_field
            st.selectbox('Igniter grade' if grade_field == 'grade' else 'Quiz grade', [5, 6, 7],
                         index=[5, 6, 7].index(plan.get(grade_field, 5)), key=grade_key,
                         on_change=_setting_changed, args=(state, grade_field, grade_key))
            query = st.text_input('Search skills or codes', key=prefix + codes_field + '::find',
                                  placeholder='e.g. order of operations, PEMDAS, 6.NS.5',
                                  help='Search all Grades 5–7 by skill name, official description, synonym, or standard code.')
            selected_codes = plan[codes_field]
            recent = [c for c in state.get('recent_standard_codes', [])
                      if c in BY_CODE and BY_CODE[c].grade == plan[grade_field]]
            if query.strip():
                # Look across all three grades so advanced classes can search
                # without first knowing which grade owns the standard.
                matches = [code for grade in (5, 6, 7) for code in standard_codes_for(grade)
                           if standard_matches_search(code, query)]
                options = list(dict.fromkeys([*selected_codes, *matches]))
                if not matches:
                    st.caption('No bank standards match yet. Try another skill word or code.')
            else:
                options = list(dict.fromkeys([*selected_codes, *recent,
                                              *standard_codes_for(plan[grade_field])]))
            code_key = prefix + codes_field
            st.multiselect(label, options, default=selected_codes,
                           format_func=standard_picker_label, key=code_key,
                           placeholder='Type to search and select skills',
                           filter_mode='contains',
                           on_change=_setting_changed, args=(state, codes_field, code_key))
            if not query.strip():
                suggestions = [code for code in recent if code not in selected_codes][:2]
                if suggestions:
                    st.caption('Recently used in this block · click to add')
                    for col, code in zip(st.columns(len(suggestions)), suggestions):
                        with col:
                            st.button('↻ ' + standard_skill_name(code),
                                      help=standard_picker_label(code),
                                      key=prefix + codes_field + '::recent::' + code,
                                      on_click=_add_recent_standard,
                                      args=(state, codes_field, code, code_key),
                                      use_container_width=True)
    st.caption(f"Friday starts with skills taught the week of {date.fromisoformat(plan['prior_week']):%b %d}. Choose them here if no prior week is available.")
    st.button('Fill week with questions', type='primary', key=prefix+'fill', on_click=_fill_week, args=(state,))
    for warning in state.get('suggestion_warnings', []):
        st.warning(warning)


def _render_sheet(store, state, repository, prefix):
    plan = state['plan']
    _render_standards(state, prefix)
    readonly = _readonly_days(store, state)
    st.divider()
    for i, item in enumerate(plan['days']):
        day = date.fromisoformat(item['date'])
        header, availability = st.columns([3, 1], vertical_alignment='center')
        with header:
            st.markdown(f"#### {day:%A} · {day:%b %d}")
            status = state_label(item, plan['baseline'][i])
            st.caption(readonly.get(i) or status)
        with availability:
            if i not in readonly:
                skip_key = f'{prefix}skip{i}'
                st.checkbox('No class', value=not item.get('enabled', True), key=skip_key,
                            on_change=_day_changed, args=(state, i, skip_key))
        disabled = i in readonly or not item.get('enabled', True)
        if i == 4:
            a, b, c = st.columns([3, 1, 1])
            with a:
                key = prefix+'assignment_name'
                st.text_input('Quiz name', value=item['assignment_name'], key=key, disabled=disabled,
                              on_change=_quiz_setting, args=(state, 'assignment_name', key), max_chars=120)
            with b:
                key = prefix+'category_code'
                st.selectbox('Category', ['SUMM', 'FORM'], index=['SUMM', 'FORM'].index(item['category_code']),
                             key=key, disabled=disabled, on_change=_quiz_setting, args=(state, 'category_code', key))
            with c:
                key = prefix+'max_score'
                st.number_input('Points', min_value=.01, max_value=100., value=float(item['max_score']), key=key, disabled=disabled,
                                on_change=_quiz_setting, args=(state, 'max_score', key))
        for start in range(0, len(item['questions']), 2):
            columns = st.columns(2, gap='medium')
            for offset, column in enumerate(columns):
                slot = start + offset
                if slot < len(item['questions']):
                    with column:
                        render_question_card(store, state, i, slot, prefix, disabled=disabled)
        st.write('')

    destinations = [(i, j) for i, item in enumerate(plan['days']) if i not in readonly and item.get('enabled', True)
                    for j in range(len(item['questions']))]
    if len(destinations) > 1:
        st.divider()
        a, b, c = st.columns([2, 2, 1], vertical_alignment='bottom')
        label = lambda pair: f"{date.fromisoformat(plan['days'][pair[0]]['date']):%A} · Question {pair[1]+1}"
        with a:
            source_key = prefix+'swap_from'
            source = st.selectbox('Rearrange · swap', destinations, format_func=label, key=source_key)
        targets = [x for x in destinations if x != source and plan['days'][x[0]]['kind'] == plan['days'][source[0]]['kind']]
        with b:
            target_key = prefix+'swap_to'+str(source)
            st.selectbox('With', targets or [source], format_func=label, key=target_key)
        with c:
            st.button('Swap questions', key=prefix+'swap', disabled=not targets or bool(state.get('pending_images')),
                      on_click=_swap_questions, args=(store, state, source_key, target_key))
    st.divider()
    st.caption('Edits save as a draft. Review the week before publishing to students.')
    if st.button('Preview current week', type='primary', key=prefix+'preview', disabled=bool(state.get('save_error') or state.get('image_error'))):
        if state['revision'] == 0 and not _save_draft(repository, state, force=True):
            st.rerun()
        _change_view(state, 'preview')
        st.rerun()


def _changes(plan):
    return [i for i, (item, old) in enumerate(zip(plan['days'], plan['baseline']))
            if item.get('enabled', True) and (old is None or content(item) != {k: v for k, v in old.items() if k != 'id'})]


def _reload_published_week(store, repository, state):
    # Called only after explicit confirmation. Never changes live assignments.
    # Keep the current edit buffer intact unless the fresh draft saves safely.
    plan = state['plan']
    fresh = new_plan(store, plan['class_id'], date.fromisoformat(plan['week_start']))
    record = repository.save(fresh, state['revision'])
    _accept_record(state, record)
    state['editor_epoch'] = state.get('editor_epoch', 0) + 1
    state['pending_images'] = {}
    _change_view(state, 'edit')
    for key in ('publish_error', 'publish_request', 'image_error', 'lock_cache', 'suggestion_warnings'):
        state.pop(key, None)


def _preview(store, plan):
    for i, item in enumerate(plan['days']):
        day = date.fromisoformat(item['date'])
        st.markdown(f"#### {day:%A, %b %d} · {'Igniter' if i<4 else 'Quiz of the Week'}")
        if not item.get('enabled', True):
            st.caption('No updates for this date. Existing published work stays in place.')
            baseline = plan['baseline'][i]
            questions = baseline['questions'] if baseline else []
        else:
            questions = item['questions']
            st.caption(state_label(item, plan['baseline'][i]))
        if i == 4 and questions:
            st.caption(f"{item['assignment_name']} · {item['max_score']:g} points · {item['category_code']}")
        body = []
        for slot, q in enumerate(questions, 1):
            body.append('<div class="wp-question"><strong>Question '+str(slot)+'</strong> · '+html.escape(q.get('standard_code') or 'No standard')+
                        question_html(q, question_image_url(store, q))+
                        '<div class="wp-answer"><strong>Answer:</strong> '+math_text(answer_text(q))+'</div></div>')
        if body:
            st.markdown('<div class="wp-summary">'+''.join(body)+'</div>', unsafe_allow_html=True)


def _render_multi_block_publish(store, state, repository, prefix, class_ids, class_names):
    st.markdown(f'#### Publish to {len(class_ids)} blocks')
    st.caption('The questions will be identical. Each block keeps its own saved plan, student work, and future editing.')
    try:
        preview = preview_targets(store, repository, state['plan'], class_ids,
                                  source_revision=state['revision'])
    except Exception as exc:
        st.error('Cannot verify the selected blocks right now. '+_message(exc))
        return
    for item in preview:
        name = class_names[item['class_id']]
        count = len(item['changes'])
        st.write(f"**{name}:** {count} activity update{'s' if count != 1 else ''}" if count else
                 f'**{name}:** Already matches this week · no changes needed')
        for reason in item['blockers']:
            st.error(f'{name} · {reason}')
    blocked = any(item['blockers'] for item in preview)
    existing_drafts = [class_names[item['class_id']] for item in preview if item['draft_conflict']]
    confirm_drafts = not existing_drafts
    if existing_drafts:
        st.warning('These blocks already have different saved planning drafts: '+', '.join(existing_drafts)+'.')
        confirm_drafts = st.checkbox('Replace those saved drafts with the shared questions',
                                     key=prefix+'bulk_confirm_drafts')
    replacements = [class_names[item['class_id']] for item in preview if item['needs_confirmation']]
    confirm_replacements = not replacements
    if replacements:
        st.caption('Published or today’s assignments would change in: '+', '.join(replacements)+'.')
        confirm_replacements = st.checkbox('Confirm changes to unstarted published or today’s assignments',
                                            key=prefix+'bulk_confirm_published')
    if any(item['changes'] for item in preview) and st.button(
        f'Publish to {len(class_ids)} blocks', type='primary', key=prefix+'bulk_publish',
        disabled=blocked or not confirm_drafts or not confirm_replacements or bool(state.get('save_error')),
    ):
        results = publish_targets(repository, preview, confirm_replacements=confirm_replacements,
                                  confirm_drafts=confirm_drafts)
        for result in results:
            if result['class_id'] == state['plan']['class_id'] and result['status'] == 'published':
                _accept_record(state, result['draft'])
                state.pop('lock_cache', None)
        state['bulk_results'] = [{k: v for k, v in result.items() if k != 'draft'} for result in results]
        if all(result['status'] != 'failed' for result in results):
            _change_view(state, 'edit')
            state['notice'] = 'Shared week published. Each selected block can now be edited independently.'
        st.rerun()
    if state.get('bulk_results'):
        st.markdown('**Last publish attempt**')
        for result in state['bulk_results']:
            name = class_names.get(result['class_id'], 'A selected block')
            if result['status'] == 'published':
                st.success(f"{name}: Published {result['changed']} activity(s).")
            elif result['status'] == 'unchanged':
                st.caption(f'{name}: Already up to date.')
            elif result['status'] == 'failed':
                st.error(f"{name}: Not published — {_message(result['error'])}")
            else:
                st.warning(f'{name}: Not attempted because the editing block could not publish.')
        if any(result['status'] == 'failed' for result in state['bulk_results']):
            st.caption('Other successful blocks are safe. Resolve the error and preview again to publish only what remains.')


def _render_review(store, state, repository, prefix, class_ids, class_names):
    if st.button('← Back to editing', key=prefix+'back'):
        _change_view(state, 'edit')
        st.rerun()
    st.markdown('### Review your week')
    plan = state['plan']
    _preview(store, plan)
    duplicates = duplicate_slots(plan)
    if duplicates:
        st.warning('Repeated questions: '+ '; '.join(duplicates) + '. Keep them only if the repetition is intentional.')
    valid = True
    try:
        validate_plan(plan)
    except (ValueError, TypeError, KeyError) as exc:
        st.warning('Finish these questions before publishing: '+str(exc))
        valid = False
    if len(class_ids) > 1:
        if valid:
            _render_multi_block_publish(store, state, repository, prefix, class_ids, class_names)
        return
    changes = _changes(plan)
    confirm_needed = any(plan['baseline'][i] or plan['days'][i]['date'] == current_daily_date().isoformat() for i in changes)
    confirmed = False
    if confirm_needed:
        confirmed = st.checkbox('Confirm updates to published questions or today’s assignments', key=prefix+'confirm')
    if not changes:
        st.success('This week matches the published assignments. Go back to editing whenever you need to change an unstarted activity.')
    label = 'Publish changes' if any(plan['baseline']) else 'Publish week'
    if st.button(label, type='primary', key=prefix+'publish',
                 disabled=not valid or not changes or bool(state.get('save_error')) or (confirm_needed and not confirmed)):
        try:
            request_id = state.setdefault('publish_request', uuid4().hex)
            result = repository.publish(plan, state['revision'], request_id, confirm=confirmed)
            _accept_record(state, result['draft'])
            state.pop('publish_request', None)
            state.pop('publish_error', None)
            state.pop('lock_cache', None)
            _change_view(state, 'edit')
            state['notice'] = f"Week published. {result['changed']} activity(s) updated. You can return here to edit unstarted activities."
            st.rerun()
        except Exception as exc:
            state.pop('lock_cache', None)
            state['publish_error'] = _message(exc)
    if state.get('publish_error'):
        st.error(state['publish_error'])
        st.caption('Publication could not be confirmed. Retrying after a connection error is safe. If assignments changed elsewhere, reload the published week.')
        st.download_button('Keep a copy of my edits', json.dumps(plan, indent=2),
                           file_name=f"weekly-plan-{plan['week_start']}.json", mime='application/json', key=prefix+'publish_copy')
        discard = st.checkbox('Discard this draft and reload the published week', key=prefix+'publish_discard')
        if st.button('Reload published week', key=prefix+'reload_published', disabled=not discard):
            try:
                _reload_published_week(store, repository, state)
                st.rerun()
            except Exception as exc:
                st.error(_message(exc))


def render_weekly_planning(store):
    if not teacher_can_present():
        st.warning('Sign in as a teacher to plan assignments.')
        return
    st.markdown(PLANNER_CSS, unsafe_allow_html=True)
    with st.container(key='weekly-planner'):
        st.markdown('### Weekly Planning Center')
        st.caption('Choose the skills. Fill the week. Edit every question below.')
        maybe_cleanup_question_images(store, current_daily_date())
        try:
            classes = list(store.list_classes())
        except Exception as exc:
            st.error(_message(exc))
            return
        if not classes:
            st.info('Create a class first.')
            return
        names = {str(c.class_id): c.class_name for c in classes}
        selection = st.session_state.get('weekly_planner_selection', {})
        ids = list(names)
        defaults = [cid for cid in selection.get('target_ids', [selection.get('class_id', ids[0])]) if cid in names]
        if not defaults:
            defaults = [ids[0]]
        a, b = st.columns(2)
        with a:
            class_ids = st.multiselect('Plan for these blocks', ids, default=defaults,
                                       format_func=names.get, key='weekly_planner_targets')
        with b:
            selected = st.date_input('Instructional week', selection.get('day', current_daily_date()), key='weekly_planner_week')
        if not class_ids:
            st.info('Select at least one classroom block to plan the week.')
            return
        class_id = class_ids[0]
        st.session_state['weekly_planner_selection'] = {'class_id': class_id, 'target_ids': class_ids, 'day': selected}
        week = monday_for(selected)
        if len(class_ids) > 1:
            st.caption(f"Editing {names[class_id]} for all {len(class_ids)} selected blocks · {week:%b %d}–{week+timedelta(days=4):%b %d}. The first selected block is the editing copy.")
        else:
            st.caption(f"{names[class_id]} · {week:%b %d}–{week+timedelta(days=4):%b %d}")
        session_key = f'weekly_planner::{class_id}::{week}'
        repository = plan_repository(store)
        failed_drafts = _flush_working_drafts(store, repository)
        try:
            if session_key not in st.session_state:
                record = repository.load(class_id, week)
                plan = record['plan'] if record else new_plan(store, class_id, week)
                st.session_state[session_key] = {'plan': deepcopy(plan), 'saved_plan': deepcopy(plan),
                                                'revision': record['revision'] if record else 0, 'view': 'edit'}
        except Exception as exc:
            st.error(_message(exc))
            return
        state = st.session_state[session_key]
        if 'recent_standard_codes' not in state:
            previous = st.session_state.get('weekly_planner_recent_by_class', {}).get(str(class_id), [])
            current = state['plan']
            from_questions = [q.get('standard_code') for day in current['days'] for q in day['questions']]
            # Current class's saved plan and previously taught quiz standards
            # provide useful recents across sessions without extra database reads.
            state['recent_standard_codes'] = list(dict.fromkeys(
                code for code in [*previous, *current['standards'], *current['quiz_standards'],
                                  *from_questions] if code in BY_CODE))[:8]
        prefix = f"{session_key}::sheet252::{state.get('editor_epoch', 0)}::"
        for failed_key in failed_drafts:
            if failed_key != session_key:
                pending = st.session_state[failed_key]['plan']
                st.warning(f"A draft for {names.get(pending['class_id'], 'another class')} · week of {pending['week_start']} could not save. Return to that week to retry; its edits are still in this session.")
        if _upload_pending_images(store, state) and not state.get('save_error'):
            _save_draft(repository, state)
        if state.get('notice'):
            st.success(state['notice'])
        _save_problem_controls(repository, state, prefix)
        if not state.get('save_error') and not state.get('image_error'):
            st.caption('Draft saved automatically' if state['revision'] else 'Your questions will save here as you work.')
        if state.get('view') == 'preview':
            _render_review(store, state, repository, prefix, class_ids, names)
        else:
            _render_sheet(store, state, repository, prefix)
        if token := state.pop('scroll_to_top', None):
            # A new summary should open at Monday, not retain the footer's
            # scroll position. Run only for explicit view changes, never typing.
            st.html('<!-- '+token+' --><script>requestAnimationFrame(() => requestAnimationFrame(() => {'
                    'document.querySelector(\'[data-testid="stMain"]\')?.scrollTo(0,0);'
                    'window.scrollTo(0,0); }));</script>', unsafe_allow_javascript=True)
