"""Multi-app context switching (NON-CRIT-003). Pure logic with a fake executor."""

from agent.app_context import AppContextManager


class _FakeExecutor:
    def __init__(self):
        self.keys = []

    def execute(self, action):
        # KeyAction has a .key attribute.
        self.keys.append(getattr(action, "key", None))
        return True


def test_detect_app_switch_destination_wins():
    assert AppContextManager.detect_app_switch("copy from Chrome, paste into Word") == "Word"


def test_detect_app_switch_simple():
    assert AppContextManager.detect_app_switch("switch to Chrome") == "Chrome"


def test_detect_app_switch_none_when_no_app():
    assert AppContextManager.detect_app_switch("just type hello there") is None


def test_copy_paste_issue_key_actions():
    mgr = AppContextManager(current_app="Chrome")
    exe = _FakeExecutor()
    assert mgr.copy(exe) is True
    assert mgr.paste(exe) is True
    assert exe.keys == ["ctrl+c", "ctrl+v"]


def test_copy_without_executor_is_false():
    mgr = AppContextManager()
    assert mgr.copy(None) is False


def test_copy_paste_action_sequences_available():
    assert AppContextManager.copy_actions()
    assert AppContextManager.paste_actions()
