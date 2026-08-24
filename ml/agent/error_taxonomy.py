"""
ATLAS ML Pipeline - Error Classification Taxonomy
=================================================
NON-CRIT-001: classify pipeline failures into categories so the agent loop can
route each failure to a recovery strategy tuned to its cause instead of falling
back on a single generic retry.

This module is intentionally pure and unit-testable: it imports nothing beyond
the standard library, enum, typing, and loguru, and it never touches the screen,
the models, the filesystem, or the network. Everything is derived from the
error message string plus an optional context dict.

Public surface:
    ErrorType        - enum of failure categories.
    classify_error   - map an error message (+ optional context) to an ErrorType.
    recovery_hint    - short suggested recovery strategy per ErrorType.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple

from loguru import logger

__all__ = ["ErrorType", "classify_error", "recovery_hint"]


class ErrorType(Enum):
    """Category of a pipeline failure."""

    PERCEPTION = "perception"  # Could not see/read/locate the element or any change.
    EXECUTION = "execution"    # The input actuation itself failed (OS / PyAutoGUI).
    STATE = "state"            # App/environment is in a bad or unexpected condition.
    TASK = "task"              # The requested thing is not achievable (feature absent).
    UNKNOWN = "unknown"        # No signal strong enough to classify.


# Ordered (ErrorType, keywords) rules. The list is scanned top to bottom and the
# first keyword found as a substring of the lowercased message wins, so more
# specific phrases are deliberately placed above broader single words (for
# example "cannot find" -> PERCEPTION is checked before the bare "cannot" ->
# TASK rule near the end).
_RULES: List[Tuple[ErrorType, Tuple[str, ...]]] = [
    # State: the application or environment is in a bad / unexpected condition.
    (ErrorType.STATE, (
        "crashed", "has crashed", "unexpected state", "modal", "dialog",
        "popup", "pop-up", "not responding", "unresponsive", "froze",
        "frozen", "window closed", "window disappeared", "lost focus",
        "not focused", "blocked by", "permission request", "hung",
    )),
    # Task: the requested thing is not achievable (feature absent / impossible).
    (ErrorType.TASK, (
        "feature does not exist", "does not exist", "doesn't exist",
        "not supported", "unsupported", "no such feature", "no such option",
        "no such command", "not a feature", "not implemented", "not available",
        "not possible", "impossible", "cannot be done", "cannot be completed",
    )),
    # Perception: we could not see / read / locate the element or any change.
    (ErrorType.PERCEPTION, (
        "cannot find", "cannot locate", "can't find", "could not find",
        "unable to find", "unable to locate", "not found", "no target",
        "target not found", "no target element", "no element",
        "element missing", "not visible", "could not detect", "could not read",
        "failed to resolve", "no visual change", "no significant change",
        "not detected", "ocr", "unreadable", "low confidence",
    )),
    # Execution: the input actuation itself failed (OS / PyAutoGUI level).
    (ErrorType.EXECUTION, (
        "execution failed", "os level", "os-level", "pyautogui", "failsafe",
        "fail-safe", "could not click", "click failed", "click validation",
        "could not type", "type failed", "key press failed", "keypress failed",
        "scroll failed", "input failed", "keystroke", "timed out", "timeout",
    )),
    # Task (broad, checked late so specific perception phrases win first).
    (ErrorType.TASK, (
        "cannot", "can not",
    )),
    # Execution (broad single words, last resort before context / unknown).
    (ErrorType.EXECUTION, (
        "click", "type", "scroll", "mouse", "keyboard",
    )),
]

# Stage hints (from context["stage"]) map a pipeline phase to the category a
# failure most likely belongs to when the message itself is inconclusive.
_STAGE_MAP: Dict[str, ErrorType] = {
    "perception": ErrorType.PERCEPTION,
    "verification": ErrorType.PERCEPTION,
    "execution": ErrorType.EXECUTION,
    "act": ErrorType.EXECUTION,
    "planning": ErrorType.TASK,
    "plan": ErrorType.TASK,
    "state": ErrorType.STATE,
}

_ACTION_TYPES = {"click", "type", "key", "scroll"}


def _from_context(context: Dict) -> ErrorType:
    """Infer a category from context hints when the message gave no signal."""
    stage = str(context.get("stage", "")).strip().lower()
    if stage in _STAGE_MAP:
        return _STAGE_MAP[stage]

    action_type = str(context.get("action_type", "")).strip().lower()
    if action_type in _ACTION_TYPES:
        # A bare failure while actuating an action is most likely execution.
        return ErrorType.EXECUTION

    return ErrorType.UNKNOWN


def classify_error(error_message: str, context: Optional[Dict] = None) -> ErrorType:
    """
    Classify a failure message into an ErrorType using keyword heuristics.

    Args:
        error_message: The human-readable error / verification reason string.
        context: Optional dict of extra hints. Recognized keys (all optional):
            - "action_type": the attempted action ("click"/"type"/"key"/
              "scroll"); biases an otherwise-unknown failure toward EXECUTION.
            - "stage": pipeline stage where the failure surfaced
              ("perception"/"execution"/"verification"/"planning"/"state");
              used as a tiebreaker when the message keywords are inconclusive.

    Returns:
        The best-matching ErrorType. Keyword matches on the message take
        precedence; if none match, context hints are consulted; failing that,
        ErrorType.UNKNOWN is returned.
    """
    text = (error_message or "").lower()
    ctx = context or {}

    for error_type, keywords in _RULES:
        for kw in keywords:
            if kw in text:
                logger.debug(f"classify_error matched '{kw}' -> {error_type.name}")
                return error_type

    inferred = _from_context(ctx)
    if inferred is not ErrorType.UNKNOWN:
        logger.debug(f"classify_error used context hint -> {inferred.name}")
    else:
        logger.debug("classify_error found no signal; returning UNKNOWN")
    return inferred


_RECOVERY_HINTS: Dict[ErrorType, str] = {
    ErrorType.PERCEPTION: (
        "Re-perceive the screen (re-run OCR/VLM and let it settle), then widen "
        "or loosen element matching before retrying the same step."
    ),
    ErrorType.EXECUTION: (
        "Retry the actuation: re-resolve coordinates, slow the input down, and "
        "re-focus the target window before repeating the action."
    ),
    ErrorType.STATE: (
        "Stabilize the environment first: dismiss or handle the modal/dialog, "
        "bring the app to the front, or restart it, then replan the step."
    ),
    ErrorType.TASK: (
        "Do not retry as-is; the goal may be infeasible. Replan the task, or "
        "skip/abort this step and report that the feature is unavailable."
    ),
    ErrorType.UNKNOWN: (
        "Cause unclear: capture a fresh screenshot, retry once, and escalate to "
        "LLM-guided recovery if it fails again."
    ),
}


def recovery_hint(error_type: ErrorType) -> str:
    """Return a short suggested recovery strategy for the given error type."""
    return _RECOVERY_HINTS.get(error_type, _RECOVERY_HINTS[ErrorType.UNKNOWN])
