"""
ATLAS ML Pipeline - Window State
================================

Addresses CRITICAL-003: the agent did not verify that the target app was
running, focused, and in front before capturing the screen. This module offers
best-effort window inspection and focus control on Windows using ctypes, so no
extra dependency is required. Every function degrades to a safe no-op on other
platforms or when the Win32 calls are unavailable.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from loguru import logger


def _user32():
    try:
        import ctypes

        return ctypes.windll.user32
    except Exception:
        return None


def get_foreground_window_title() -> Optional[str]:
    """Return the title of the currently focused window, or None."""
    user32 = _user32()
    if user32 is None:
        return None
    try:
        import ctypes

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value
    except Exception as e:
        logger.debug(f"get_foreground_window_title failed: {e}")
        return None


def is_app_focused(app_name: str) -> bool:
    """True when the focused window title contains app_name (case-insensitive)."""
    if not app_name:
        return False
    title = get_foreground_window_title()
    return bool(title) and app_name.lower() in title.lower()


def list_windows() -> List[Tuple[int, str]]:
    """Return visible top-level windows as (hwnd, title) pairs. Empty off Windows."""
    user32 = _user32()
    if user32 is None:
        return []
    try:
        import ctypes

        results: List[Tuple[int, str]] = []
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
        )

        def _callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value
            if title:
                results.append((int(hwnd), title))
            return True

        user32.EnumWindows(EnumWindowsProc(_callback), 0)
        return results
    except Exception as e:
        logger.debug(f"list_windows failed: {e}")
        return []


def find_window(app_name: str) -> Optional[int]:
    """Return the hwnd of a visible window whose title contains app_name."""
    if not app_name:
        return None
    needle = app_name.lower()
    for hwnd, title in list_windows():
        if needle in title.lower():
            return hwnd
    return None


def bring_to_front(app_name: str) -> bool:
    """
    Restore and focus a window matching app_name. Best-effort.

    Returns True if a matching window was found and focus was requested. Never
    raises and never launches anything.
    """
    user32 = _user32()
    if user32 is None:
        return False
    hwnd = find_window(app_name)
    if not hwnd:
        return False
    try:
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        logger.info(f"Brought window to front: {app_name}")
        return True
    except Exception as e:
        logger.debug(f"bring_to_front failed for {app_name}: {e}")
        return False
