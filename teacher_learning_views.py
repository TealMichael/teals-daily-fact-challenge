"""Explicit Learning destinations, independent of the legacy wrapper signature.

The old one-argument render_teacher_mastery_focus may remain loaded during a
partial Streamlit update. These entry points never call it. Both use the same
established calculation/render functions and the same class selector.
"""

import streamlit as st
import teacher_learning_ui as learning


def render_learning_view(store, view=None):
    st.markdown("### 📈 Learning Data")
    st.caption("A simple view of multiplication fact fluency plus Indiana-standard evidence from Igniters, Quiz of the Week, and Recovery.")
    classes = store.list_classes()
    if not classes:
        st.info("Create a class first.")
        return
    class_by_name = {item.class_name: item for item in classes}
    class_name = st.selectbox("Class", list(class_by_name), key="teacher_mastery_class")
    selected = class_by_name[class_name]
    students = store.list_students(selected.class_id)
    if not students:
        st.info("No students are in this class yet.")
        return
    if view is None:
        view = st.radio(
            "Learning data view", ["⚡ Fact Fluency", "📚 Standards Tracker"],
            horizontal=True, label_visibility="collapsed", key="teacher_learning_data_view",
        )
    if view == "⚡ Fact Fluency":
        learning._render_teacher_fact_fluency(store, selected, students)
    elif view == "📚 Standards Tracker":
        learning._render_teacher_standards_tracker(store, selected, students)
    else:
        raise ValueError("Unknown Learning view")


def render_teacher_standards_mastery(store):
    render_learning_view(store, "📚 Standards Tracker")


def render_teacher_fact_fluency(store):
    render_learning_view(store, "⚡ Fact Fluency")
