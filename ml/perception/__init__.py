"""
ATLAS ML Pipeline - Perception Module
======================================

Handles all visual perception:
- Screen capture
- OCR text extraction
- VLM UI detection
- Bounding box fusion
"""

from .screen_capture import ScreenCapture
from .bbox_fusion import BoundingBoxFusion
from .perception_engine import PerceptionEngine
from .modal_detection import detect_modal, is_blocking_modal
from . import window_state

__all__ = [
    "ScreenCapture",
    "BoundingBoxFusion",
    "PerceptionEngine",
    "detect_modal",
    "is_blocking_modal",
    "window_state",
]
