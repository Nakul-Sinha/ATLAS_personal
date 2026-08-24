"""
ATLAS ML Pipeline - Multi-App Context Switching (NON-CRIT-003)
=============================================================

Coordinates work that spans more than one application, such as "copy from
Chrome, paste into Word". The agent loop plans one abstract step at a time and
has no memory of which application a step belongs to, so a cross-app workflow
can type into the wrong window or lose the clipboard relay halfway through.

AppContextManager fills that gap. It:

- tracks a "current_app" plus small per-app scratch state across a task,
- exposes a lightweight clipboard-relay concept (copy / paste) built on the
  existing KeyAction type instead of driving the keyboard directly, and
- offers detect_app_switch, a heuristic that reads a step description and tells
  the loop which application (if any) that step implies switching to.

Design constraints:

- Pure-ish and defensive: no method raises, and construction/import never
  requires a display, PyAutoGUI, or Ollama. The only executor interaction is
  through an optional executor object the caller passes in.
- Actuation is delegated: copy() and paste() build KeyAction sequences and hand
  them to the caller's executor. This module never imports pyautogui and never
  presses a key itself.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from loguru import logger

# Both imports are intentionally guarded. app_context must stay importable even
# if the actions or perception packages fail to import on a given host (for
# example a headless CI box), so the module degrades to safe no-ops rather than
# breaking import of the whole agent package.
try:
    from actions.actions import KeyAction
except Exception:  # pragma: no cover - defensive import guard
    KeyAction = None  # type: ignore[assignment]

try:
    from perception import window_state
except Exception:  # pragma: no cover - defensive import guard
    window_state = None  # type: ignore[assignment]


class AppContextManager:
    """
    Tracks per-app state across a multi-app task and relays the clipboard.

    Typical use inside the agent loop, per step::

        target = AppContextManager.detect_app_switch(step.description)
        if target and target != ctx.current_app:
            ctx.switch_app(target)

    And for an explicit copy/paste handoff::

        ctx.copy(executor)          # Ctrl+C in the current app
        ctx.switch_app("Word")      # focus the destination
        ctx.paste(executor)         # Ctrl+V into it
    """

    # Copy / paste are expressed as key combos so callers can either let this
    # class execute them via an executor or read the sequence and run it
    # themselves. Kept as class constants so there is a single source of truth.
    COPY_KEY = "ctrl+c"
    PASTE_KEY = "ctrl+v"

    # Known desktop application names used by the detect_app_switch heuristic.
    # Maps a lowercase spelling that may appear in a step description to a
    # canonical name that window_state.find_window can match against a window
    # title. Multi-word spellings are preferred over their sub-words at scan
    # time (longest match wins), so "google chrome" beats "chrome".
    _CANON: Dict[str, str] = {
        "google chrome": "Chrome",
        "chrome": "Chrome",
        "firefox": "Firefox",
        "mozilla firefox": "Firefox",
        "microsoft edge": "Edge",
        "edge": "Edge",
        "safari": "Safari",
        "brave": "Brave",
        "opera": "Opera",
        "microsoft word": "Word",
        "ms word": "Word",
        "word": "Word",
        "microsoft excel": "Excel",
        "ms excel": "Excel",
        "excel": "Excel",
        "powerpoint": "PowerPoint",
        "microsoft powerpoint": "PowerPoint",
        "outlook": "Outlook",
        "onenote": "OneNote",
        "microsoft teams": "Teams",
        "teams": "Teams",
        "notepad++": "Notepad++",
        "notepad": "Notepad",
        "wordpad": "WordPad",
        "word pad": "WordPad",
        "file explorer": "Explorer",
        "windows explorer": "Explorer",
        "explorer": "Explorer",
        "visual studio code": "Visual Studio Code",
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "visual studio": "Visual Studio",
        "slack": "Slack",
        "discord": "Discord",
        "zoom": "Zoom",
        "skype": "Skype",
        "spotify": "Spotify",
        "calculator": "Calculator",
        "paint": "Paint",
        "command prompt": "Command Prompt",
        "powershell": "PowerShell",
        "terminal": "Terminal",
        "cmd": "Command Prompt",
        "adobe acrobat": "Acrobat",
        "acrobat": "Acrobat",
        "photoshop": "Photoshop",
        "gmail": "Gmail",
        "sublime text": "Sublime Text",
        "sublime": "Sublime Text",
    }

    # Longest names first so multi-word matches win over their sub-words.
    _KNOWN_SORTED: List[str] = sorted(_CANON.keys(), key=len, reverse=True)

    # Prepositions that mark the app being switched INTO (the destination) versus
    # the one being read FROM (the source). Destination wins when both appear in
    # one step, since that is where the next actions should land.
    _DEST_PREPS = ("switch to", "paste into", "into", "onto", "open", "in", "to", "over to")
    _SRC_PREPS = ("copy from", "from")

    def __init__(self, current_app: Optional[str] = None) -> None:
        # The app the agent believes is (or should be) in focus right now.
        self.current_app: Optional[str] = current_app
        # The app that was current before the most recent switch.
        self.previous_app: Optional[str] = None
        # Per-app scratch state, e.g. {"Chrome": {"copied": True}}.
        self.apps: Dict[str, Dict[str, Any]] = {}
        # Ordered record of switch targets, useful for debugging a multi-app run.
        self.switch_history: List[str] = []
        if current_app:
            self._register(current_app)

    # ------------------------------------------------------------------ #
    # App switching / current-app tracking
    # ------------------------------------------------------------------ #
    def switch_app(self, app_name: str, timeout: float = 2.0) -> bool:
        """
        Switch desktop focus to app_name and record it as the current app.

        Delegates the actual focus change to window_state.switch_to_app (which
        verifies the switch landed). current_app is updated to app_name so the
        rest of the task treats it as active, while the returned boolean reports
        whether the OS-level focus switch was actually confirmed. Never raises;
        returns False off Windows or when window_state is unavailable.
        """
        if not app_name:
            return False
        confirmed = False
        if window_state is not None:
            try:
                confirmed = bool(window_state.switch_to_app(app_name, timeout=timeout))
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(f"switch_app: window_state.switch_to_app failed: {e}")
                confirmed = False
        else:
            logger.debug("switch_app: window_state unavailable; treating as no-op")

        # Track intent regardless of confirmation so per-app state stays keyed to
        # the app the plan is now working in.
        self._register(app_name)
        if app_name != self.current_app:
            self.previous_app = self.current_app
            self.current_app = app_name
        self.switch_history.append(app_name)
        logger.info(
            f"AppContext current app -> {app_name} "
            f"({'focus confirmed' if confirmed else 'focus not confirmed'})"
        )
        return confirmed

    # ------------------------------------------------------------------ #
    # Clipboard relay
    # ------------------------------------------------------------------ #
    @staticmethod
    def copy_actions() -> List[Any]:
        """Intended KeyAction sequence for a copy (Ctrl+C). Empty if actions unavailable."""
        if KeyAction is None:
            return []
        return [KeyAction(key=AppContextManager.COPY_KEY, confidence=1.0)]

    @staticmethod
    def paste_actions() -> List[Any]:
        """Intended KeyAction sequence for a paste (Ctrl+V). Empty if actions unavailable."""
        if KeyAction is None:
            return []
        return [KeyAction(key=AppContextManager.PASTE_KEY, confidence=1.0)]

    def copy(self, executor: Any = None) -> bool:
        """
        Issue a copy (Ctrl+C) in the current app.

        If executor is provided its execute() is called with the KeyAction
        sequence; if it is None the sequence is exposed via copy_actions() but
        nothing runs (returns False). Records that the current app has copied
        content. Never raises.
        """
        ok = self._run(self.copy_actions(), executor, label="copy")
        if ok and self.current_app:
            self.apps.setdefault(self.current_app, {})["copied"] = True
        return ok

    def paste(self, executor: Any = None) -> bool:
        """
        Issue a paste (Ctrl+V) in the current app.

        Same executor contract as copy(): executes via the passed executor, or
        returns False when none is given. Never raises.
        """
        return self._run(self.paste_actions(), executor, label="paste")

    def relay(self, from_app: str, to_app: str, executor: Any = None) -> bool:
        """
        Convenience clipboard relay: copy in from_app, switch, paste in to_app.

        Focuses from_app, copies, focuses to_app, and pastes, in order. Returns
        True only if every sub-step that needed to run reported success. Each
        sub-step is defensive, so a failure part way through still leaves the
        manager in a consistent state. Never raises.
        """
        steps_ok = True
        if from_app:
            # A failure to confirm focus is not fatal (may be off Windows), but a
            # failed copy is, since there is then nothing to paste.
            self.switch_app(from_app)
        steps_ok = self.copy(executor) and steps_ok
        if to_app:
            self.switch_app(to_app)
        steps_ok = self.paste(executor) and steps_ok
        return steps_ok

    def _run(self, actions: List[Any], executor: Any, label: str) -> bool:
        """Execute a KeyAction sequence via executor. Defensive; never raises."""
        if not actions:
            logger.debug(f"{label}: no KeyAction available (actions module missing); skipping")
            return False
        if executor is None:
            logger.debug(f"{label}: no executor supplied; sequence exposed but not executed")
            return False
        ok = True
        for action in actions:
            try:
                result = executor.execute(action)
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(f"{label}: executor raised on {getattr(action, 'key', '?')}: {e}")
                result = False
            ok = ok and bool(result)
        return ok

    # ------------------------------------------------------------------ #
    # Per-app scratch state
    # ------------------------------------------------------------------ #
    def get_app_state(self, app_name: Optional[str] = None) -> Dict[str, Any]:
        """Return the scratch-state dict for app_name (default: current app)."""
        name = app_name or self.current_app
        if not name:
            return {}
        return self.apps.setdefault(name, {})

    def remember(self, key: str, value: Any, app_name: Optional[str] = None) -> None:
        """Store a per-app fact for later steps (default target: current app)."""
        name = app_name or self.current_app
        if not name:
            return
        self.apps.setdefault(name, {})[key] = value

    def reset(self) -> None:
        """Clear all tracked state for a fresh task."""
        self.current_app = None
        self.previous_app = None
        self.apps = {}
        self.switch_history = []

    def _register(self, app_name: str) -> None:
        """Ensure a scratch-state bucket exists for app_name."""
        if app_name:
            self.apps.setdefault(app_name, {})

    # ------------------------------------------------------------------ #
    # Step parsing
    # ------------------------------------------------------------------ #
    @staticmethod
    def detect_app_switch(step_description: str) -> Optional[str]:
        """
        Heuristically decide which application a task step implies switching to.

        Scans step_description for a known application name and returns its
        canonical form, or None when no app is implied. Resolution order:

        1. A known app immediately after a destination preposition
           ("into Word", "switch to Excel", "open Notepad") wins, since that is
           where the next actions should land.
        2. Otherwise a known app after a source preposition ("from Chrome").
        3. Otherwise the first known app mentioned anywhere.
        4. As a last resort, a capitalized proper-noun token right after a
           destination preposition ("into Figma") even if it is not a known app.

        Purely lexical, case-insensitive, and defensive: returns None on empty
        input and never raises.
        """
        if not step_description:
            return None
        try:
            text = str(step_description)
            low = text.lower()

            # Collect known-app mentions, longest names first, skipping any match
            # already covered by a longer one (so "wordpad" does not also fire
            # "word", and "google chrome" beats "chrome").
            covered: List[tuple] = []
            mentions: List[tuple] = []  # (start_index, canonical_name)
            for app in AppContextManager._KNOWN_SORTED:
                pattern = r"(?<![a-z0-9])" + re.escape(app) + r"(?![a-z0-9])"
                for m in re.finditer(pattern, low):
                    s, e = m.start(), m.end()
                    if any(s >= cs and e <= ce for cs, ce in covered):
                        continue
                    covered.append((s, e))
                    mentions.append((s, AppContextManager._CANON[app]))
            mentions.sort()

            if mentions:
                dest = [
                    name for (idx, name) in mentions
                    if AppContextManager._prep_before(low, idx, AppContextManager._DEST_PREPS)
                ]
                if dest:
                    return dest[0]
                src = [
                    name for (idx, name) in mentions
                    if AppContextManager._prep_before(low, idx, AppContextManager._SRC_PREPS)
                ]
                if src:
                    return src[0]
                # No preposition anchor: fall back to the first app mentioned.
                return mentions[0][1]

            # No known app: accept a Capitalized token right after a destination
            # preposition, e.g. "paste into Figma" -> "Figma".
            m = re.search(
                r"\b(?:switch\s+to|paste\s+into|into|onto|open|over\s+to)\s+"
                r"(?:the\s+|a\s+|an\s+)?"
                r"([A-Z][A-Za-z0-9+.\-]*(?:\s+[A-Z][A-Za-z0-9+.\-]*)?)",
                text,
            )
            if m:
                return m.group(1).strip()
            return None
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"detect_app_switch failed: {e}")
            return None

    @staticmethod
    def _prep_before(low: str, idx: int, preps: tuple) -> bool:
        """
        True when the text immediately before position idx ends with one of the
        given prepositions, ignoring a single article ("the"/"a"/"an").
        """
        prefix = low[:idx].strip()
        for art in (" the", " a", " an"):
            if prefix.endswith(art):
                prefix = prefix[: -len(art)].rstrip()
                break
        for p in preps:
            if prefix == p or prefix.endswith(" " + p):
                return True
        return False
