"""Coordinate transforms on ScreenFrame, including monitor offset (CRITICAL-004)."""

import numpy as np

from perception.screen_capture import ScreenFrame


def _frame(width=1920, height=1080, offset_x=0, offset_y=0, dpi_scale=1.0):
    return ScreenFrame(
        image=np.zeros((height, width, 3), dtype=np.uint8),
        width=width,
        height=height,
        monitor=1,
        timestamp=0.0,
        dpi_scale=dpi_scale,
        offset_x=offset_x,
        offset_y=offset_y,
    )


def test_center_of_primary_monitor():
    frame = _frame()
    assert frame.to_absolute(0.5, 0.5) == (960, 540)


def test_offset_added_for_secondary_monitor():
    # A 1920x1080 monitor placed to the right of the primary.
    frame = _frame(offset_x=1920, offset_y=0)
    x, y = frame.to_absolute(0.5, 0.5)
    assert x == 1920 + 960
    assert y == 540


def test_round_trip_with_offset():
    frame = _frame(offset_x=1920, offset_y=200)
    ax, ay = frame.to_absolute(0.25, 0.75)
    nx, ny = frame.to_normalized(ax, ay)
    assert abs(nx - 0.25) < 1e-3
    assert abs(ny - 0.75) < 1e-3


def test_dpi_scale_applied():
    frame = _frame(width=1000, height=1000, dpi_scale=1.5)
    assert frame.to_absolute(1.0, 1.0) == (1500, 1500)
