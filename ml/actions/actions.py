"""
ATLAS ML Pipeline - Action Definitions
=======================================
Atomic action types for OS-level interaction.
"""

from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Optional


@dataclass
class Action(ABC):
    """Base class for all actions."""
    confidence: float = 0.0
    
    @abstractmethod
    def describe(self) -> str:
        """Human-readable description."""
        pass


@dataclass
class ClickAction(Action):
    """Mouse click at coordinates."""
    x: int = 0
    y: int = 0
    button: str = "left"  # left, right, middle
    clicks: int = 1  # 1 for single, 2 for double
    
    def describe(self) -> str:
        return f"Click ({self.button}, {self.clicks}x) at ({self.x}, {self.y})"


@dataclass
class TypeAction(Action):
    """Type text."""
    text: str = ""
    interval: float = 0.02  # Seconds between keystrokes (per-char delay)
    # Chunked typing (NON-CRIT-002): if set to a positive int, the text is typed
    # in fixed-size chunks with a short delay between chunks so apps that buffer
    # input slowly do not drop fast keystrokes. None types the whole string at once.
    chunk_size: Optional[int] = None
    # If True, pause a little longer between chunks so each chunk is buffered by
    # the app before the next one is sent (a lightweight settle, not visual OCR).
    verify_each: bool = False

    def describe(self) -> str:
        preview = self.text[:20] + "..." if len(self.text) > 20 else self.text
        return f"Type: '{preview}'"


@dataclass
class KeyAction(Action):
    """Press keyboard key(s)."""
    key: str = ""  # e.g., "enter", "tab", "ctrl+c"
    
    def describe(self) -> str:
        return f"Press key: {self.key}"


@dataclass
class ScrollAction(Action):
    """Scroll at position."""
    x: int = 0
    y: int = 0
    direction: str = "down"  # up, down, left, right
    amount: int = 3  # Scroll units
    
    def describe(self) -> str:
        return f"Scroll {self.direction} by {self.amount} at ({self.x}, {self.y})"


@dataclass
class WaitAction(Action):
    """Wait for specified duration."""
    duration: float = 1.0  # Seconds
    
    def describe(self) -> str:
        return f"Wait {self.duration}s"
