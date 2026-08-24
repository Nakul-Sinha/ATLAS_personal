"""Modal / dialog detection heuristic (CRITICAL-002). Uses synthetic images."""

import numpy as np

from perception.modal_detection import detect_modal, is_blocking_modal


def _plain_screen():
    # A uniform, edge-free background.
    return np.full((600, 800, 3), 60, dtype=np.uint8)


def _screen_with_centered_dialog():
    img = np.full((600, 800, 3), 60, dtype=np.uint8)
    # A bright, centered dialog rectangle from (250,150) to (550,450).
    img[150:450, 250:550] = 240
    return img


def test_no_modal_on_plain_screen():
    assert detect_modal(_plain_screen()) is None
    assert is_blocking_modal(_plain_screen()) is False


def test_detects_centered_dialog():
    result = detect_modal(_screen_with_centered_dialog())
    assert result is not None
    cx, cy = result["center"]
    assert abs(cx - 0.5) < 0.15
    assert abs(cy - 0.5) < 0.15
    assert 0.05 < result["area_ratio"] < 0.75
    assert 0.0 < result["confidence"] <= 0.95


def test_ignores_tiny_corner_box():
    img = np.full((600, 800, 3), 60, dtype=np.uint8)
    img[10:40, 10:60] = 240  # small, off-center
    assert detect_modal(img) is None


def test_handles_none_and_grayscale():
    assert detect_modal(None) is None
    gray = np.full((600, 800), 60, dtype=np.uint8)
    # Grayscale plain screen: no modal, and must not raise.
    assert detect_modal(gray) is None
