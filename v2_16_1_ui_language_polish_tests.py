from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from fact_engine import APP_VERSION, CHALLENGE_VERSION

ROOT = Path(__file__).resolve().parent
checks: list[str] = []


def check(name: str, condition: bool) -> None:
    assert condition, name
    checks.append(name)


check("v2.17.0 version", APP_VERSION == "2.19.5")
check("Daily challenge version unchanged", CHALLENGE_VERSION == "TDFC-DAILY-v1")
check("v2.17.0 follow-up migration is present", (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_17.sql").exists())

# The normal classroom UI should no longer expose implementation/build language.
normal_ui_files = [
    "app.py",
    "teacher_today_ui.py",
    "teacher_command_center.py",
    "teacher_daily_setup_ui.py",
    "teacher_warmup_ui.py",
    "teacher_class_history_ui.py",
    "teacher_intelligence.py",
    "teacher_intelligence_ui.py",
    "teacher_learning_ui.py",
    "student_alt_daily_ui.py",
]
normal_text = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in normal_ui_files)
old_phrases = [
    "Quick Warm-Up — Trial",
    "sandbox only",
    "SANDBOX TEST",
    "TEST STUDENT SANDBOX",
    "Teacher-only accuracy & timing",
    "Refresh data forces a new Supabase connection",
    "Student-safe display",
    "full engine view",
    "protected default generator",
    "hashed PIN cannot be recovered",
    "v2.5 database update",
    "Supabase + Streamlit Secrets",
    "independent retrieval evidence",
    "weighted accuracy",
    "historical result",
    "active roster",
]
for phrase in old_phrases:
    check(f"old developer phrase removed: {phrase}", phrase.lower() not in normal_text.lower())

# Key replacement copy should be present on the screens the teacher uses every day.
copy_expectations = {
    "teacher_warmup_ui.py": ["### 🧠 Warm-Up", "Student preview", "Today's Student Answers"],
    "teacher_learning_ui.py": ["Facts practiced", "Warm-Up Standards Tracker", "Detailed Fact Map & Focus Settings"],
    "teacher_today_ui.py": ["All Classes", "Accuracy & timing", "Preview today's 10"],
    "app.py": ["### 🧪 Test Student", "Preview class", "Teal's Daily Fact Challenge · v{APP_VERSION}"],
    "teacher_clock_ui.py": ["Clock connection", "⚙️ One-time clock setup", "Test the clock"],
}
for relative, phrases in copy_expectations.items():
    text = (ROOT / relative).read_text(encoding="utf-8")
    for phrase in phrases:
        check(f"plain-language copy present: {relative} / {phrase}", phrase in text)

# Technical clock recovery details are still available, but only inside the collapsed setup area.
clock = (ROOT / "teacher_clock_ui.py").read_text(encoding="utf-8")
setup_pos = clock.index('with st.expander("⚙️ One-time clock setup"')
check("clock technical details are tucked into one-time setup", clock.find("SUPABASE_URL", setup_pos) > setup_pos)
check("clock still exposes required setup file only in setup flow", "RUN_THIS_ONCE_IN_SUPABASE_v2_12.sql" in clock)
check("clock mapping behavior preserved", all(marker in clock for marker in [
    "get_awtrix_clock_config", "save_awtrix_clock_mapping", "rotate_awtrix_clock_token", "queue_awtrix_top10"
]))

# Protect non-copy behavior byte-for-byte from v2.16.0.
protected_hashes = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "daily_alt_component/index.html": "332ee7265c450b00d4848a059f000439dba2089c4ec765bf18f41e2bed734c4d",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "persistent_login_component/index.html": "fae94c44f25512d2c017b24e17e3be2d987f21604072ed4c061fbae1cc9f9585",
    "pin_entry_component/index.html": "18a89b45481f83f33fd93746bdf854ba0e4b216c0c1f0904e035f871d5d8c2b7",
    "student_igniter_ui.py": "043f3905b3e37a926cbae66d40de5e9ff963b2af3676f6bc4678336ca08e39ed",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "daily_modes.py": "f37b151fc44514f761f66f616434d26764df9719b0ab64d1865c9ee0d1881561",
    "warmup.py": "e9dc2faabf9234c4463f84fc02c3453b4a1f5e37376cd8461d1adccc34bb816b",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "teacher_insights.py": "4fdf3516e75a8d697747f4d92aadd3f39c51a116e5990054c5eca4c66b0094a5",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff2d68a49edc3e2" if False else "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
}
for relative, expected in protected_hashes.items():
    actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    check(f"behavior file unchanged: {relative}", actual == expected)

# For files that remain copy-only, normalize string constants and require the v2.16.0 AST.
# teacher_intelligence_ui.py intentionally gained alternate Focus visibility in v2.19.
class NormalizeStrings(ast.NodeTransformer):
    def visit_Constant(self, node: ast.Constant):  # noqa: N802
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value="<STR>"), node)
        return node


def normalized_tree_hash(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree = NormalizeStrings().visit(tree)
    ast.fix_missing_locations(tree)
    payload = ast.dump(tree, include_attributes=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


copy_only_hashes = {
    "teacher_learning_ui.py": "5c16f18787ede1feb0a46d333a0a18239047503ccfcf03000be67d77b0116085",
    "teacher_daily_setup_ui.py": "39d27f6559e7952138b29b970907eeea60452e9b10cd0fecac69a3271e608993",
    "teacher_warmup_ui.py": "974457ce13d7ae186cdd101b85d210991231eacadc4375c989745e6fb1dd266e",
    "teacher_intelligence.py": "3b4fef7ba6335e1203237e9ed6e069eebfef974eb2743de829336debd9c14d49",
}
for relative, expected in copy_only_hashes.items():
    check(f"copy-only structure unchanged: {relative}", normalized_tree_hash(ROOT / relative) == expected)

# v2.17.0 intentionally expands alternate-mode follow-up while preserving the
# cleaned classroom wording from v2.16.1.
command_center = (ROOT / "teacher_command_center.py").read_text(encoding="utf-8")
check("alternate-mode Today follow-up is explicit", all(marker in command_center for marker in [
    "def summarize_routine_for_mode", "def routine_label_for_mode", "Fix Your Misses"
]))
student_alt = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
check("alternate student follow-up uses classroom language", all(marker in student_alt for marker in [
    "Next: Fix Your Misses", "Your learning work is finished for today.", "Today's Mystery Reward"
]))
student_alt_visible_strings = "\n".join(
    node.value for node in ast.walk(ast.parse(student_alt))
    if isinstance(node, ast.Constant) and isinstance(node.value, str)
)
check("alternate student UI avoids implementation labels", "alternate_learning_events" not in student_alt_visible_strings)

# app.py combines many routes. Protect the critical student functions structurally while allowing copy edits.
app_source = (ROOT / "app.py").read_text(encoding="utf-8")
app_tree = ast.parse(app_source)
app_functions = {node.name: node for node in ast.walk(app_tree) if isinstance(node, ast.FunctionDef)}
student_function_hashes = {
    "render_student_sign_in": "e983548951cada274b495734e1451af7cd72bbfb9dc0fd93ac64e6e71125a69d",
    "render_daily": "db3ae64f454987c03ac651f97c893860b560252204aa8c8daab6ada38042958c",
    "render_practice": "c26833c2f32ea44b1faa2fa5b32f5d04bf983733fd05a8c351b4448dbc2cf8b7",
    "handle_persistent_student_login": "b94bf690025f20b491f1145b3d211bf6f67a280760b2da81fab7b38143c0737f",
    "render_header": "07e13773bc274384cf8243edcc550fda548203b41727de53632ecf093f956842",
    "render_weekly_mystery_reward": "6b7bdff47fdfa642eef3092d01ebae747b5633e3d7a879cae7e680eac466deed",
    "_render_mystery_win": "5e709c70ac076edaa156fd163b6e689f88108eb5935fc3fafb329185276bc87f",
}
for name, expected in student_function_hashes.items():
    node = app_functions[name]
    normalized = NormalizeStrings().visit(node)
    ast.fix_missing_locations(normalized)
    actual = hashlib.sha256(ast.dump(normalized, include_attributes=False).encode("utf-8")).hexdigest()
    check(f"student function behavior unchanged: {name}", actual == expected)

# Teacher-only files with f-string copy changes still must retain their core read/call contracts.
today = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")
check("Today data contracts preserved", all(marker in today for marker in [
    "store.daily_status", "store.class_learning_progress", "store.class_alternate_learning_progress",
    "store.get_warmup_set", "store.list_warmup_answers"
]))
history = (ROOT / "teacher_class_history_ui.py").read_text(encoding="utf-8")
check("Class History remains read-only over established history", all(marker in history for marker in [
    "store.teacher_daily_history", "store.get_warmup_set", "store.list_warmup_answers", "store.get_weekly_mystery"
]))
check("Class History adds no write calls", not any(marker in history for marker in ["set_app_setting(", "save_", "update_", "delete_"]))

print(f"v2.17.0 UI Language Polish: {len(checks)}/{len(checks)} checks passed")
