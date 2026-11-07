"""Anonymous offline regressions for Friday Quiz publishing after missed Igniters.

Run: python3 -B v2_29_3_past_day_quiz_publish_tests.py
"""

import ast
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).parent


def _load_functions(filename, names, scope):
    source = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    nodes = [node for node in source.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), scope)


def _validate_question(question, kind, slot):
    if not question.get('prompt'):
        raise ValueError('Each Warm-Up question needs a prompt.')
    if not question.get('correct_answer'):
        raise ValueError('Each question needs an answer.')
    return deepcopy(question)


scope = {'date': date, 'timedelta': timedelta, 'deepcopy': deepcopy,
         'normalize_question': _validate_question,
         'mark_edited': lambda state: state.pop('publish_request', None)}
_load_functions('teacher_weekly_planning_ui.py',
                {'_exclude_past_days_from_publish', '_changes'}, scope)
_load_functions('weekly_planning.py', {'validate_plan', 'content'}, scope)
exclude = scope['_exclude_past_days_from_publish']
validate = scope['validate_plan']
changes = scope['_changes']


def _question(prompt='', answer=''):
    return {'question_type': 'Number', 'prompt': prompt, 'correct_answer': answer}


def _plan():
    monday = date(2026, 11, 2)
    days = []
    for index in range(5):
        quiz = index == 4
        days.append({
            'date': (monday + timedelta(days=index)).isoformat(),
            'kind': 'quiz' if quiz else 'igniter', 'enabled': True,
            'questions': [_question(f'Quiz {slot}', str(slot)) for slot in range(1, 6)]
                         if quiz else [_question(), _question()],
            **({'assignment_name': 'Friday Quiz', 'category_code': 'SUMM',
                'max_score': 5.0} if quiz else {}),
        })
    return {'week_start': monday.isoformat(), 'days': days, 'baseline': [None] * 5}


def test_missing_thursday_does_not_block_complete_friday_quiz():
    plan = _plan()
    friday_before = deepcopy(plan['days'][4])
    state = {'plan': plan, 'publish_request': 'obsolete'}
    excluded = exclude(state, today=date(2026, 11, 6))
    assert excluded == [f'2026-11-0{i}' for i in range(2, 6)]
    assert all(not day['enabled'] for day in plan['days'][:4])
    assert plan['days'][4] == friday_before
    assert validate(plan)['days'][4]['questions'] == friday_before['questions']
    assert changes(plan) == [4]  # Publish Friday only.
    assert state.get('publish_request') is None
    assert exclude(state, today=date(2026, 11, 6)) == []


def test_published_past_activity_and_question_data_are_retained():
    plan = _plan()
    plan['days'][0]['questions'][0] = _question('Past draft remains', '10')
    original = deepcopy(plan['days'][0]['questions'])
    plan['baseline'][0] = {'id': 'anonymous', 'questions':
                           [_question('Published Q1', '7'), _question('Published Q2', '8')]}
    state = {'plan': plan}
    exclude(state, today=date(2026, 11, 6))
    assert plan['days'][0]['questions'] == original
    assert plan['baseline'][0]['questions'][0]['prompt'] == 'Published Q1'
    assert changes(plan) == [4]
    assert validate(plan)['days'][0]['enabled'] is False


def test_today_and_future_are_still_validated():
    plan = _plan()
    exclude({'plan': plan}, today=date(2026, 11, 5))
    assert plan['days'][3]['enabled'] is True
    assert plan['days'][4]['enabled'] is True
    try:
        validate(plan)
    except ValueError as error:
        assert 'prompt' in str(error)
    else:
        raise AssertionError('Current unfinished Igniter was incorrectly bypassed')


def test_server_skips_disabled_dates_and_version_is_updated():
    sql = (ROOT / 'RUN_THIS_ONCE_IN_SUPABASE_v2_25_1.sql').read_text()
    assert "if not coalesce((item->>'enabled')::boolean,false) then continue; end if;" in sql
    assert 'APP_VERSION = "2.29.3"' in (ROOT / 'fact_engine.py').read_text()


if __name__ == '__main__':
    test_missing_thursday_does_not_block_complete_friday_quiz()
    test_published_past_activity_and_question_data_are_retained()
    test_today_and_future_are_still_validated()
    test_server_skips_disabled_dates_and_version_is_updated()
    print('v2.29.3 Friday publishing: 4 offline checks passed')
