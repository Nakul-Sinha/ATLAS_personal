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
        """Execute keyboard typing."""
        pg = _pyautogui()
        pg.write(action.text, interval=action.interval or self.type_interval)
        logger.debug(f"Typed {len(action.text)} characters")
        return True
    
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
