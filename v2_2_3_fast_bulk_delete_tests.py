from fact_store import InMemoryFactStore


def run():
    store = InMemoryFactStore()
    block1 = store.create_class("Block 1", "FAST01")
    block2 = store.create_class("Block 2", "FAST02")

    wrong = [store.create_student(block1.class_id, f"Wrong {i}", f"{5000+i:04d}"[-4:]) for i in range(28)]
    keep = [store.create_student(block2.class_id, f"Keep {i}", f"{6000+i:04d}"[-4:]) for i in range(5)]

    # True multi-delete removes a whole selected set in one store call.
    deleted = store.delete_students([student.student_id for student in wrong[:10]])
    assert deleted == 10
    remaining1 = store.list_students(block1.class_id, include_inactive=True)
    assert len(remaining1) == 18

    # Whole-roster clear removes every remaining student while preserving the class.
    deleted = store.delete_class_students(block1.class_id)
    assert deleted == 18
    assert store.list_students(block1.class_id, include_inactive=True) == []
    assert any(item.class_id == block1.class_id and item.class_name == "Block 1" for item in store.list_classes(include_inactive=True))
    assert len(store.list_students(block2.class_id, include_inactive=True)) == len(keep)

    backend = open("supabase_fact_store.py", encoding="utf-8").read()
    ui = open("app.py", encoding="utf-8").read()
    engine = open("fact_engine.py", encoding="utf-8").read()

    assert 'APP_VERSION = "2.2.3"' in engine
    assert 'def delete_students(' in backend
    assert '.delete().in_("student_id", ids).execute()' in backend
    assert 'def delete_class_students(' in backend
    assert '.delete().eq("class_id", str(class_id)).execute()' in backend
    assert 'store.delete_students([target.student_id for target in targets])' in ui
    assert 'Clear this entire roster' in ui
    assert 'Permanently delete all' in ui
    assert 'DELETE {selected.class_name}' in ui

    print("v2_2_3_fast_bulk_delete_tests: PASS (28-student cleanup, single-call bulk delete, whole-roster clear)")


if __name__ == "__main__":
    run()
