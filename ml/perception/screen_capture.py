"""
ATLAS ML Pipeline - Screen Capture
===================================

Handles screenshot capture and coordinate frame management.

PIPELINE STEP 3
"""

from typing import Tuple, Optional
from dataclasses import dataclass
import numpy as np
from loguru import logger

from config import ScreenConfig, config


@dataclass
class ScreenFrame:
    """Captured screen with metadata."""
    image: np.ndarray  # RGB image array
    width: int
    height: int
    monitor: int
    timestamp: float
    dpi_scale: float = 1.0
    # Top-left of this monitor in the virtual desktop. pyautogui clicks use
    # virtual-desktop coordinates, so these offsets must be added when a target
    # is on a non-primary monitor.
    offset_x: int = 0
    offset_y: int = 0

    def to_absolute(self, x_norm: float, y_norm: float) -> Tuple[int, int]:
        """
        Convert normalized in-frame coordinates to absolute click coordinates.

        Adds the monitor offset so the result is in the virtual-desktop space
        that the OS input layer expects. When the process is DPI aware the
        captured pixels and input pixels share one space and dpi_scale stays 1.0.
        """
        x = self.offset_x + int(x_norm * self.width * self.dpi_scale)
        y = self.offset_y + int(y_norm * self.height * self.dpi_scale)
        return (x, y)

    def to_normalized(self, x: int, y: int) -> Tuple[float, float]:
        """Convert absolute (virtual-desktop) pixels to normalized in-frame coordinates."""
        x_norm = (x - self.offset_x) / (self.width * self.dpi_scale)
        y_norm = (y - self.offset_y) / (self.height * self.dpi_scale)
        return (x_norm, y_norm)


class ScreenCapture:
    """
    Screen capture utility using mss.
    
    Captures screenshots and manages coordinate frames.
    
    Usage:
        capture = ScreenCapture()
        frame = capture.grab()
        x, y = frame.to_absolute(0.5, 0.5)  # Center of screen
    """
    
    def __init__(self, screen_config: Optional[ScreenConfig] = None):
        self.config = screen_config or config.screen
        self._mss = None
        self._monitor_info = None
        
    def _init_mss(self) -> None:
        """Initialize mss screen capture."""
        import mss
        self._mss = mss.mss()
        self._monitor_info = self._mss.monitors
        logger.debug(f"Screen capture initialized. Monitors: {len(self._monitor_info) - 1}")
        
    def grab(self, monitor: Optional[int] = None) -> ScreenFrame:
        """
        Capture screenshot of specified monitor.
        
        Args:
            monitor: Monitor number (1-based) or None for configured default
            
        Returns:
            ScreenFrame with image and metadata
        """
        if self._mss is None:
            self._init_mss()
            
        import time
        
        mon = monitor or self.config.capture_monitor
        
        try:
            # Get monitor geometry
            mon_info = self._mss.monitors[mon]
            
            # Capture screenshot
            screenshot = self._mss.grab(mon_info)
            
            # Convert to numpy RGB array
            image = np.array(screenshot)
            # mss returns BGRA, convert to RGB
            image = image[:, :, [2, 1, 0]]
            
            frame = ScreenFrame(
                image=image,
                width=mon_info["width"],
                height=mon_info["height"],
                monitor=mon,
                timestamp=time.time(),
                dpi_scale=self.config.dpi_scale,
                offset_x=mon_info.get("left", 0),
                offset_y=mon_info.get("top", 0),
            )
            
            logger.debug(f"Captured screen: {frame.width}x{frame.height}")
            return frame
            
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            raise
    
    def get_monitor_info(self) -> list:
        """Get information about all monitors."""
        if self._mss is None:
            self._init_mss()
        return self._monitor_info[1:]  # Skip the "all monitors" entry
    
    def set_dpi_awareness(self) -> bool:
        """
        Make the process per-monitor DPI aware (Windows).

        This is the robust fix for CRITICAL-001: once the process is DPI aware,
        mss captures at physical pixels and the OS input layer also uses physical
        pixels, so captured coordinates and click coordinates share one space and
        no per-axis scaling correction is needed. Safe no-op off Windows.

        Returns True if awareness was set (or already active), False otherwise.
        """
        try:
            import ctypes

            # PROCESS_PER_MONITOR_DPI_AWARE = 2
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            logger.info("Process set to per-monitor DPI aware")
            return True
        except AttributeError:
            # Not on Windows, or shcore unavailable.
            return False
        except OSError as e:
            # Already set by a manifest or an earlier call; treat as success.
            logger.debug(f"DPI awareness already configured: {e}")
            return True
        except Exception as e:
            logger.warning(f"Could not set DPI awareness: {e}")
            return False

    def detect_dpi_scale(self) -> float:
        """
        Detect current DPI scaling for reporting and logging.

        Coordinate correctness comes from set_dpi_awareness(); this value is
        informational (for example, to warn a user about a scaled display).
        """
        try:
            import ctypes
            
            # Get DPI awareness
            awareness = ctypes.c_int()
            ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
            
            # Get DPI for primary monitor
            dc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, dc)
            
            scale = dpi / 96.0  # 96 DPI is 100% scaling
            logger.info(f"Detected DPI scale: {scale}")
            return scale
            
        except Exception as e:
            logger.warning(f"DPI detection failed, using 1.0: {e}")
            return 1.0
    
    def save_screenshot(self, frame: ScreenFrame, path: str) -> None:
        """Save screenshot to file for debugging."""
        from PIL import Image
        
        img = Image.fromarray(frame.image)
        img.save(path)
        logger.debug(f"Screenshot saved: {path}")
