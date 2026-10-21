from __future__ import annotations

"""Teacher planning workspace. All edits are drafts until explicit publication."""

from copy import deepcopy
from datetime import date, timedelta
import json
from uuid import uuid4

import streamlit as st

from fact_engine import current_daily_date
from igniter_presentation import open_igniter_presentation, teacher_can_present, answer_text, question_image_url
from indiana_math_standards import BY_CODE
from indiana_question_bank import standard_codes_for
from question_images import upload_question_image, maybe_cleanup_question_images
from planning_question_images import question_for_date
from teacher_planning import monday_for
from teacher_question_editor import render_answer_editor
from teacher_warmup_ui import _warmup_form_question
from teacher_weekly_quiz_ui import _question_editor
from weekly_planning import (duplicate_slots, new_plan, normalize_question, plan_repository,
                             state_label, suggest_questions, validate_plan, load_published_week)


def _label(code):
    standard = BY_CODE.get(code)
    return standard.label if standard else code


def _reset_editors(state):
    state["epoch"] = state.get("epoch", 0) + 1
    state.pop("publish_request", None)


def _set_record(state, record):
    state["plan"] = deepcopy(record["plan"])
    state["saved_plan"] = deepcopy(record["plan"])
    state["revision"] = record["revision"]
    _reset_editors(state)


def _error(exc):
    message = str(getattr(exc, "message", "") or exc)
    if any(token in message for token in ("PGRST202", "PGRST205", "schema cache", "does not exist")):
        st.error("The Weekly Planning Center needs the v2.25.1 SQL update. Existing classroom activities and Display Igniter remain available.")
    else:
        st.error(message if len(message) < 650 else "The draft could not be saved or published. Reload the saved draft and try again.")


def _prepare_editor_image(store, edited, *, day, kind, slot):
    result = dict(edited)
    if result.pop("_remove_image", False):
        result["image_path"] = ""
    upload = result.pop("_image_upload", None)
    # Upload only with the explicit Apply question button, never on a rerun.
    if upload is not None:
        result["image_path"] = upload_question_image(store, upload, question_date=day, kind=kind, slot=slot)
    return normalize_question(result, kind, slot)


def _preview(store, plan):
    for index, item in enumerate(plan["days"]):
        day = date.fromisoformat(item["date"])
        with st.expander(f"{day:%A, %b %d} · {state_label(item, plan['baseline'][index])}", expanded=True):
            if not item.get("enabled", True):
                st.caption("Publishing will leave this date unchanged.")
                continue
            for slot, q in enumerate(item["questions"], 1):
                st.markdown(f"**{slot}. {q.get('prompt') or '(Question not yet written)'}**")
                if q.get("question_type") == "Compare Values":
                    st.write(f"{q.get('compare_left','')}  [ < = > ]  {q.get('compare_right','')}")
                elif q.get("question_type") == "Order Tiles":
                    st.write(" · ".join(q.get("order_items") or []))
                    st.caption(q.get("order_direction") or "Least to greatest")
                elif q.get("question_type") == "Multiple choice":
                    st.write(" · ".join(q.get("options") or []))
                elif q.get("question_type") == "Number + Label":
                    st.write("Unit choices: " + " · ".join(q.get("label_options") or []))
                image = question_image_url(store, q)
                if image:
                    st.image(image, width=400)
                elif q.get("image_path") or q.get("bank_image_path"):
                    st.warning("Question image unavailable. Replace or remove it before class.")
                st.caption(f"{q.get('standard_code','')} · Answer: {answer_text(q)}")


def render_weekly_planning(store):
    if not teacher_can_present():
        st.warning("Sign in as a teacher to plan assignments.")
        return
    st.markdown("### Weekly Planning Center")
    st.caption("Plan once. Review together. Publish when ready.")
    maybe_cleanup_question_images(store, current_daily_date())
    try:
        classes = list(store.list_classes())
    except Exception as exc:
        _error(exc)
        return
    if not classes:
        st.info("Create a class first.")
        return
    names = {str(c.class_id): c.class_name for c in classes}
    selection = st.session_state.get("weekly_planner_selection", {})
    class_ids = list(names)
    a, b = st.columns(2)
    with a:
        class_id = st.selectbox("Classroom", class_ids, format_func=names.get,
            index=class_ids.index(selection["class_id"]) if selection.get("class_id") in class_ids else 0,
            key="weekly_planner_class")
    with b:
        selected_date = st.date_input("Instructional week", selection.get("day", current_daily_date()), key="weekly_planner_week")
    # Keep this outside widget state; Streamlit cleans hidden widgets while the
    # teacher presents or opens another dashboard section.
    st.session_state["weekly_planner_selection"] = {"class_id": class_id, "day": selected_date}
    week = monday_for(selected_date)
    st.caption(f"Monday {week:%b %d} – Friday {week+timedelta(days=4):%b %d} · Daily 10 keeps its existing settings.")
    session_key = f"weekly_planner::{class_id}::{week}"
    repository = plan_repository(store)
    try:
        if session_key not in st.session_state:
            record = repository.load(class_id, week)
            plan = record["plan"] if record else new_plan(store, class_id, week)
            st.session_state[session_key] = {"plan": deepcopy(plan), "saved_plan": deepcopy(plan),
                                           "revision": record["revision"] if record else 0, "epoch": 0}
    except Exception as exc:
        _error(exc)
        return
    state = st.session_state[session_key]
    plan = state["plan"]
    prefix = f"wp::{class_id}::{week}::{state['epoch']}"
    if message := state.pop("notice", None):
        st.success(message)
    mode = st.radio("Planning step", ["Standards", "Edit questions", "Preview & publish"],
                    horizontal=True, key=f"{session_key}::step")
    if mode == "Standards":
        left, right = st.columns(2)
        with left:
            st.markdown("#### Monday–Thursday Igniters")
            plan["grade"] = st.selectbox("Igniter grade", [5, 6, 7], index=[5,6,7].index(plan.get("grade",5)), key=prefix+"grade")
            options = list(dict.fromkeys([*standard_codes_for(plan["grade"]), *plan.get("standards", [])]))
            plan["standards"] = st.multiselect("This week's standards / skills", options,
                default=plan.get("standards", []), format_func=_label, key=prefix+"standards")
        with right:
            st.markdown("#### Friday's Quiz of the Week")
            st.caption(f"Defaults to instruction from the week of {date.fromisoformat(plan['prior_week']):%b %d}.")
            plan["quiz_grade"] = st.selectbox("Quiz grade", [5, 6, 7], index=[5,6,7].index(plan.get("quiz_grade",5)), key=prefix+"quizgrade")
            options = list(dict.fromkeys([*standard_codes_for(plan["quiz_grade"]), *plan.get("quiz_standards", [])]))
            plan["quiz_standards"] = st.multiselect("Previously taught standards to assess", options,
                default=plan.get("quiz_standards", []), format_func=_label, key=prefix+"quizstandards")
            if not plan["quiz_standards"]:
                st.info("No previous instruction was found or selected. Choose Friday's taught skills; current-week skills are never copied automatically.")
        replace = st.checkbox("Replace suggestions in unpublished draft slots", key=prefix+"replace")
        if st.button("Suggest questions", type="primary", key=prefix+"suggest"):
            proposed, warnings = suggest_questions(plan, replace_drafts=replace)
            state["plan"] = proposed
            state["suggestion_warnings"] = warnings
            _reset_editors(state)
            st.rerun()
        for warning in state.get("suggestion_warnings", []):
            st.warning(warning)
        st.caption("Suggestions fill drafts only. Already published questions stay in place. Every suggestion remains yours to edit or replace.")
    elif mode == "Edit questions":
        index = st.selectbox("Activity", list(range(5)), format_func=lambda i:
            f"{date.fromisoformat(plan['days'][i]['date']):%A} · {'Igniter' if i<4 else 'Quiz of the Week'}", key=session_key+"::day")
        item = plan["days"][index]
        day = date.fromisoformat(item["date"])
        st.caption(state_label(item, plan["baseline"][index]))
        item["enabled"] = st.checkbox("Include this activity when publishing", value=item.get("enabled", True), key=f"{prefix}enabled{index}")
        if not item["enabled"]:
            st.info("This date will be left unchanged, including any already published assignment.")
        else:
            if index == 4:
                item["assignment_name"] = st.text_input("Assignment name", item["assignment_name"], key=prefix+"name", max_chars=120)
                c, d = st.columns(2)
                with c:
                    item["category_code"] = st.selectbox("Skyward category", ["SUMM", "FORM"],
                        index=["SUMM", "FORM"].index(item["category_code"]), key=prefix+"category")
                with d:
                    item["max_score"] = st.number_input("Maximum score", min_value=0.01, max_value=100.0,
                        value=float(item["max_score"]), key=prefix+"maxscore")
            st.caption("Apply each question before leaving its editor. This changes the draft only.")
            for slot, question in enumerate(list(item["questions"]), 1):
                with st.expander(f"Question {slot} · {question.get('prompt') or 'Write or choose a question'}", expanded=slot==1):
                    editor_prefix = f"{prefix}::day{index}"
                    edited = (_warmup_form_question(question, slot, editor_prefix, plan.get("standards", []))
                              if index < 4 else _question_editor(question, slot, editor_prefix))
                    if st.button(f"Apply Question {slot} to draft", key=f"{editor_prefix}apply{slot}"):
                        try:
                            item["questions"][slot-1] = _prepare_editor_image(store, edited, day=day, kind=item["kind"], slot=slot)
                            _reset_editors(state)
                            state["notice"] = "Question applied to the draft. Save draft to keep your work."
                            st.rerun()
                        except Exception as exc:
                            _error(exc)
                    destinations = [(j, s) for j, other in enumerate(plan["days"])
                                    if other["kind"] == item["kind"]
                                    for s in range(len(other["questions"])) if (j,s)!=(index,slot-1)]
                    target = st.selectbox("Swap this draft question with", destinations,
                        format_func=lambda pair: f"{date.fromisoformat(plan['days'][pair[0]]['date']):%A} · Q{pair[1]+1}",
                        key=f"{editor_prefix}swap_to{slot}")
                    if st.button("Swap questions", key=f"{editor_prefix}swap{slot}"):
                        other = plan["days"][target[0]]["questions"]
                        try:
                            moved_here = question_for_date(store, other[target[1]], day, item["kind"], slot)
                            moved_there = question_for_date(store, item["questions"][slot-1],
                                date.fromisoformat(plan["days"][target[0]]["date"]), item["kind"], target[1]+1)
                        except Exception:
                            st.error("The question image could not move. The draft is unchanged; try again or re-upload the image for the destination date.")
                            return
                        item["questions"][slot-1], other[target[1]] = moved_here, moved_there
                        # Slot labels must follow their new positions before comparisons/publication.
                        for changed_index in {index, target[0]}:
                            changed = plan["days"][changed_index]
                            for k, q in enumerate(changed["questions"], 1):
                                if q.get("prompt"):
                                    try:
                                        changed["questions"][k-1] = normalize_question(q, changed["kind"], k)
                                    except ValueError:
                                        pass
                        _reset_editors(state)
                        st.rerun()
        if index < 4 and plan["baseline"][index]:
            if st.button("Display Igniter", key=prefix+"display"):
                open_igniter_presentation(class_id, day)
                st.rerun()
            st.caption("Display Igniter uses the published questions; draft edits appear after publishing.")
    else:
        st.info("Monday Recovery, Daily 10, and Friday Mystery keep their existing sequence. Started assignments cannot be replaced.")
        _preview(store, plan)
        duplicates = duplicate_slots(plan)
        if duplicates:
            st.warning("Repeated questions: " + "; ".join(duplicates) + ". You may keep intentional repetition.")
        valid = True
        try:
            prepared = validate_plan(plan)
        except (ValueError, KeyError, TypeError) as exc:
            valid = False
            st.warning(f"Finish the draft before publishing: {exc}")
        dirty = plan != state["saved_plan"] or state["revision"] == 0
        confirmed = st.checkbox("I reviewed this week and confirm replacing any unstarted published assignments, including today's work.", key=prefix+"confirm")
        if st.button("Publish week", type="primary", disabled=not valid or dirty or not confirmed, key=prefix+"publish"):
            try:
                # Draft must be durably saved first. A failed/unknown response uses
                # the same request ID on retry; the database returns its receipt.
                request_id = state.setdefault("publish_request", uuid4().hex)
                result = repository.publish(plan, state["revision"], request_id, confirm=confirmed)
                _set_record(state, result["draft"])
                state["notice"] = f"Week published. {result['changed']} assignment(s) updated."
                st.rerun()
            except Exception as exc:
                _error(exc)
        if dirty:
            st.caption("Save the draft below before publishing.")
    # Changes to settings are always held in the per-class/week working copy.
    state["plan"] = plan
    st.divider()
    dirty = plan != state["saved_plan"] or state["revision"] == 0
    st.caption("Unsaved draft changes" if dirty else "Draft saved · publishing is a separate step")
    if st.button("Save draft", disabled=not dirty, key=prefix+"save"):
        try:
            # Incomplete drafts are allowed; normalize complete questions on publish.
            normalized = deepcopy(plan)
            for day in normalized["days"]:
                for slot, q in enumerate(day["questions"], 1):
                    try:
                        day["questions"][slot-1] = normalize_question(q, day["kind"], slot)
                    except (ValueError, TypeError):
                        pass
            record = repository.save(normalized, state["revision"])
            _set_record(state, record)
            state["notice"] = "Draft saved. Student assignments have not changed."
            st.rerun()
        except Exception as exc:
            _error(exc)
    with st.expander("Reload or keep a copy"):
        st.caption("Reloading discards unsaved changes. Reload published week also replaces this working draft with current assignments.")
        confirm_reload = st.checkbox("Discard my unsaved changes", key=prefix+"discard")
        if st.button("Reload saved draft", disabled=not confirm_reload, key=prefix+"reload"):
            st.session_state.pop(session_key, None)
            st.rerun()
        if st.button("Reload published week", disabled=not confirm_reload, key=prefix+"reload_published"):
            try:
                latest = repository.load(class_id, week)
                state["plan"] = new_plan(store, class_id, week)
                state["revision"] = latest["revision"] if latest else 0
                state["saved_plan"] = latest["plan"] if latest else {}
                _reset_editors(state)
                st.rerun()
            except Exception as exc:
                _error(exc)
        st.download_button("Download draft copy", json.dumps(plan, indent=2, ensure_ascii=False),
            file_name=f"weekly-plan-{week}.json", mime="application/json", key=prefix+"download")
