"""Pattern memory store, lookup, and confidence boost. Uses a temp SQLite db."""

from memory.memory import Memory, PatternRecord


def _record(app="notepad", role="button", text="Save", action="click"):
    return PatternRecord(
        app_name=app,
        element_role=role,
        element_text=text,
        bbox_relative=[0.1, 0.2, 0.3, 0.4],
        action_type=action,
    )


def test_store_and_lookup(tmp_path):
    db = tmp_path / "mem.db"
    mem = Memory(db_path=str(db))
    mem.store(_record())
    results = mem.lookup("notepad", role="button", text="Save")
    assert len(results) == 1
    assert results[0].element_text == "Save"
    assert results[0].bbox_relative == [0.1, 0.2, 0.3, 0.4]
    mem.close()


def test_repeated_store_increments_success_count(tmp_path):
    db = tmp_path / "mem.db"
    mem = Memory(db_path=str(db))
    for _ in range(3):
        mem.store(_record())
    results = mem.lookup("notepad", role="button", text="Save")
    assert results[0].success_count == 3
    mem.close()


def test_confidence_boost_grows_then_caps(tmp_path):
    db = tmp_path / "mem.db"
    mem = Memory(db_path=str(db))
    assert mem.get_confidence_boost("notepad", "button", "Save") == 0.0
    for _ in range(20):
        mem.store(_record())
    boost = mem.get_confidence_boost("notepad", "button", "Save")
    assert 0.0 < boost <= 0.2
    mem.close()


def test_lookup_isolated_by_app(tmp_path):
    db = tmp_path / "mem.db"
    mem = Memory(db_path=str(db))
    mem.store(_record(app="notepad"))
    mem.store(_record(app="calculator"))
    assert len(mem.lookup("notepad")) == 1
    assert len(mem.lookup("calculator")) == 1
    assert mem.lookup("nonexistent") == []
    mem.close()
