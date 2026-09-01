from pathlib import Path

from fact_engine import APP_VERSION

APP = Path('app.py').read_text()
TODAY_UI = Path('teacher_today_ui.py').read_text()


def section(start: str, end: str) -> str:
    a = APP.index(f'def {start}')
    b = APP.index(f'def {end}', a)
    return APP[a:b]

request = section('_request_teacher_refresh', '_finish_teacher_refresh')
finish = section('_finish_teacher_refresh', '_teacher_refresh_control')
control = section('_teacher_refresh_control', 'render_teacher_projector')
projector = section('render_teacher_projector', 'render_teacher_today')
def today_section() -> str:
    a = TODAY_UI.index('def render_teacher_today_command_center')
    return TODAY_UI[a:]

today = today_section()

checks = {
    'version 2.10.0': APP_VERSION == '2.16.2',
    'refresh clears cached Supabase store': 'load_store.clear()' in request,
    'refresh marks fresh read pending': 'teacher_refresh_pending' in request,
    'button uses pre-rerun callback': 'on_click=_request_teacher_refresh' in control,
    'refresh control no longer manually reruns page': 'st.rerun()' not in control,
    'timestamp is set only after fresh reads finish': '_set_teacher_refresh_stamp()' in finish and '_set_teacher_refresh_stamp()' not in request,
    'pending flag clears only on successful finish': 'pop("teacher_refresh_pending", False)' in finish,
    'Today finishes refresh after status read': 'learning_stats = store.class_learning_stats' in today and 'finish_refresh()' in today and today.index('finish_refresh()') > today.index('learning_stats = store.class_learning_stats'),
    'Projector finishes refresh after board read': 'board = _leaderboard_from_status' in projector and '_finish_teacher_refresh()' in projector and projector.index('_finish_teacher_refresh()') > projector.index('board = _leaderboard_from_status'),
    'selected class state key preserved': 'key="teacher_today_class"' in today,
    'teacher auth is not cleared by refresh': 'teacher_authed = False' not in request + finish + control,
    'button keeps familiar label': '🔄 Refresh data' in control,
    'successful refresh label is explicit': '✅ Data updated' in control,
}

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError('Failed checks: ' + ', '.join(failed))

print(f'v2.10.0 teacher refresh hotfix regression: {len(checks)}/{len(checks)} checks passed')
