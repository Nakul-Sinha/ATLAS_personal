"""Window-state helpers (CRITICAL-003). These must never raise on any platform."""

from perception import window_state


def test_functions_return_safe_types():
    title = window_state.get_foreground_window_title()
    assert title is None or isinstance(title, str)

    windows = window_state.list_windows()
    assert isinstance(windows, list)
    for entry in windows:
        assert isinstance(entry, tuple) and len(entry) == 2

    assert isinstance(window_state.is_app_focused("definitely-not-an-app"), bool)


def test_empty_app_name_is_false_and_none():
    assert window_state.is_app_focused("") is False
    assert window_state.find_window("") is None


def test_bring_to_front_missing_window_is_false():
    # A window that will not exist: must return False, not raise.
    assert window_state.bring_to_front("zzz-nonexistent-window-zzz") is False
