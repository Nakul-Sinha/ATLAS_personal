"""
ATLAS ML Pipeline - Modal / Dialog Detection
============================================

Addresses CRITICAL-002: unexpected modal dialogs (update prompts, save dialogs,
permission requests, error popups) block the pipeline. This module detects a
likely blocking overlay before the agent plans its next action, so the loop can
notice it instead of clicking through empty space.

The detector is a heuristic on the captured pixels: it looks for a prominent,
roughly centered rectangular region occupying a dialog-sized fraction of the
screen. It is deliberately conservative and returns the single best candidate
(or None). Pure function over a numpy image, so it is unit testable without a
live desktop.
"""

from __future__ import annotations

from typing import Optional, Dict, Any

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover - cv2 is a hard dependency at runtime
    cv2 = None


def detect_modal(
    image: np.ndarray,
    min_area_ratio: float = 0.06,
    max_area_ratio: float = 0.75,
    center_tolerance: float = 0.24,
) -> Optional[Dict[str, Any]]:
    """
    Detect a likely blocking modal in a screen image.

    Args:
        image: RGB (or grayscale) screen image as a numpy array.
        min_area_ratio: smallest fraction of the screen a modal may occupy.
        max_area_ratio: largest fraction of the screen a modal may occupy.
        center_tolerance: how far from center (sum of |dx| + |dy|, normalized)
            a candidate may sit and still count as a centered dialog.

    Returns:
        A dict with bbox_normalized, center, area_ratio, and confidence, or None
        when no convincing modal is found.
    """
    if image is None or cv2 is None:
        return None
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        gray = image
    h, w = gray.shape[:2]
    if h == 0 or w == 0:
        return None

    edges = cv2.Canny(gray, 40, 140)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    total = float(w * h)

    for contour in contours:
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) < 4:
            continue
        x, y, bw, bh = cv2.boundingRect(approx)
        if bw == 0 or bh == 0:
            continue
        area_ratio = (bw * bh) / total
        if not (min_area_ratio <= area_ratio <= max_area_ratio):
            continue
        aspect = bw / float(bh)
        if not (0.3 <= aspect <= 6.0):
            continue
        cx = (x + bw / 2) / w
        cy = (y + bh / 2) / h
        center_off = abs(cx - 0.5) + abs(cy - 0.5)
        if center_off > center_tolerance:
            continue
        score = area_ratio * (1.0 - center_off)
        if score > best_score:
            best_score = score
            best = {
                "bbox_normalized": [x / w, y / h, (x + bw) / w, (y + bh) / h],
                "center": [round(cx, 4), round(cy, 4)],
                "area_ratio": round(area_ratio, 4),
                "confidence": round(min(0.95, 0.4 + score), 3),
            }
    return best


def is_blocking_modal(image: np.ndarray) -> bool:
    """Convenience boolean wrapper around detect_modal."""
    return detect_modal(image) is not None
