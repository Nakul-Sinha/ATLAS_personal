"""
ATLAS ML Pipeline - Action Executor
====================================
Executes actions via OS-level input (PyAutoGUI).
PIPELINE STEP 9
"""

import time
from loguru import logger

from actions.actions import Action, ClickAction, TypeAction, KeyAction, ScrollAction, WaitAction
from config import config

# PyAutoGUI is imported lazily. It requires a display and (on Linux) an X server
# at import time, so importing it at module load would make the whole ml package
# unimportable on headless hosts and in CI. It is loaded and configured the first
# time an action actually runs.
_pg = None


def _pyautogui():
    """Import PyAutoGUI on first use and apply safety settings once."""
    global _pg
    if _pg is None:
        import pyautogui

        pyautogui.FAILSAFE = True  # move mouse to a corner to abort
        pyautogui.PAUSE = 0.1  # small pause between actions
        _pg = pyautogui
    return _pg


class ActionExecutor:
    """
    Executes atomic actions using PyAutoGUI.
    
    Usage:
        executor = ActionExecutor()
        executor.execute(ClickAction(x=100, y=200))
    """
    
    def __init__(self):
        self.move_duration = config.screen.mouse_move_duration
        self.type_interval = config.screen.typing_interval
        # Delay inserted between typed chunks so apps that buffer input slowly do
        # not drop keystrokes (NON-CRIT-002). Kept small to stay responsive.
        self.chunk_delay = 0.05
        self.last_action = None
        self.last_action_time = 0
        
    def execute(self, action: Action) -> bool:
        """
        Execute an action.
        
        Returns:
            True if action executed without error (NOT verification of success)
        """
        logger.info(f"Executing: {action.describe()}")
        
        try:
            if isinstance(action, ClickAction):
                return self._execute_click(action)
            elif isinstance(action, TypeAction):
                return self._execute_type(action)
            elif isinstance(action, KeyAction):
                return self._execute_key(action)
            elif isinstance(action, ScrollAction):
                return self._execute_scroll(action)
            elif isinstance(action, WaitAction):
                return self._execute_wait(action)
            else:
                logger.error(f"Unknown action type: {type(action)}")
                return False
                
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False
        finally:
            self.last_action = action
            self.last_action_time = time.time()
    
    def _execute_click(self, action: ClickAction) -> bool:
        """Execute mouse click."""
        pg = _pyautogui()
        pg.moveTo(action.x, action.y, duration=self.move_duration)
        pg.click(x=action.x, y=action.y, clicks=action.clicks, button=action.button)
        logger.debug(f"Clicked at ({action.x}, {action.y})")
        return True
    
    def _execute_type(self, action: TypeAction) -> bool:
        """Execute keyboard typing (robust, chunked, unicode-safe)."""
        interval = action.interval or self.type_interval
        self._type_text(
            action.text,
            interval=interval,
            chunk_size=action.chunk_size,
            verify_each=action.verify_each,
        )
        logger.debug(f"Typed {len(action.text)} characters")
        return True

    def _type_text(self, text: str, interval: float = None,
                   chunk_size: int = None, verify_each: bool = False) -> bool:
        """
        Type text robustly (NON-CRIT-002).

        The text is typed in optional fixed-size chunks with a short delay
        between chunks, so applications that buffer input slowly do not drop
        fast keystrokes. Unicode and special characters go through
        pyautogui.write() where supported; any character PyAutoGUI cannot emit
        is logged and skipped rather than aborting the whole action.

        Args:
            text: The string to type.
            interval: Per-character delay in seconds (defaults to the configured
                typing_interval). A larger value trades speed for reliability.
            chunk_size: If a positive int, type in chunks of this many characters
                with a delay between them; None types the whole string at once.
            verify_each: If True, pause a little longer between chunks so each is
                buffered by the app before the next is sent.

        PyAutoGUI is still resolved lazily via _pyautogui(); nothing here imports
        it at module load.
        """
        if not text:
            return True

        pg = _pyautogui()
        if interval is None:
            interval = self.type_interval

        if chunk_size and chunk_size > 0:
            chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        else:
            chunks = [text]

        # A slightly longer settle when the caller asked to buffer each chunk.
        settle = self.chunk_delay * 2 if verify_each else self.chunk_delay
        last = len(chunks) - 1
        for idx, chunk in enumerate(chunks):
            self._write_chunk(pg, chunk, interval)
            if verify_each:
                logger.debug(f"Typed chunk {idx + 1}/{len(chunks)} ({len(chunk)} chars)")
            if idx < last:
                time.sleep(settle)

        logger.debug(f"Typed {len(text)} characters in {len(chunks)} chunk(s)")
        return True

    def _write_chunk(self, pg, chunk: str, interval: float) -> None:
        """
        Write one chunk, degrading to per-character typing on failure.

        pyautogui.write() handles the common printable/unicode characters. If a
        chunk raises (for example on an unusual character), fall back to typing
        it character by character so a single problematic character does not
        abort the whole chunk; such characters are logged and skipped.
        """
        try:
            pg.write(chunk, interval=interval)
        except Exception as e:
            logger.debug(f"Chunk write failed ({e}); retrying character by character")
            for ch in chunk:
                try:
                    pg.write(ch, interval=interval)
                except Exception as char_err:
                    logger.warning(
                        f"Skipping character {ch!r} PyAutoGUI could not type: {char_err}"
                    )
                    continue
    
    def _execute_key(self, action: KeyAction) -> bool:
        """Execute key press."""
        pg = _pyautogui()
        # Handle hotkeys like "ctrl+c"
        if "+" in action.key:
            keys = action.key.split("+")
            pg.hotkey(*keys)
        else:
            pg.press(action.key)
        logger.debug(f"Pressed key: {action.key}")
        return True
    
    def _execute_scroll(self, action: ScrollAction) -> bool:
        """Execute scroll."""
        pg = _pyautogui()
        pg.moveTo(action.x, action.y, duration=self.move_duration)
        
        if action.direction in ["up", "down"]:
            amount = action.amount if action.direction == "up" else -action.amount
            pg.scroll(amount, x=action.x, y=action.y)
        else:
            amount = action.amount if action.direction == "right" else -action.amount
            pg.hscroll(amount, x=action.x, y=action.y)
            
        logger.debug(f"Scrolled {action.direction}")
        return True
    
    def _execute_wait(self, action: WaitAction) -> bool:
        """Execute wait."""
        time.sleep(action.duration)
        return True
    
    def move_to(self, x: int, y: int) -> None:
        """Move mouse without clicking."""
        pg = _pyautogui()
        pg.moveTo(x, y, duration=self.move_duration)
    
    def get_mouse_position(self) -> tuple:
        """Get current mouse position."""
        pg = _pyautogui()
        return pg.position()
