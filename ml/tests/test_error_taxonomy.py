"""Error classification taxonomy (NON-CRIT-001). Pure, no models."""

from agent.error_taxonomy import ErrorType, classify_error, recovery_hint


def test_perception_failure():
    assert classify_error("No target element found") is ErrorType.PERCEPTION


def test_execution_failure():
    assert classify_error("Execution failed at OS level") is ErrorType.EXECUTION


def test_state_failure():
    assert classify_error("The app crashed into an unexpected state") is ErrorType.STATE


def test_task_failure():
    assert classify_error("that feature does not exist") is ErrorType.TASK


def test_unknown_when_no_keywords():
    assert classify_error("qwerty zzz noise") is ErrorType.UNKNOWN


def test_recovery_hint_is_nonempty_for_every_type():
    for t in ErrorType:
        hint = recovery_hint(t)
        assert isinstance(hint, str) and hint.strip()
