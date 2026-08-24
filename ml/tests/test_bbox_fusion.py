"""Bounding-box fusion math and the FusedElement helpers. Pure, no models."""

from perception.bbox_fusion import BoundingBoxFusion, FusedElement


def test_center():
    el = FusedElement(role="button", bbox_normalized=[0.2, 0.4, 0.6, 0.8], confidence=0.9)
    cx, cy = el.center
    assert abs(cx - 0.4) < 1e-9
    assert abs(cy - 0.6) < 1e-9


def test_iou_identical_boxes_is_one():
    f = BoundingBoxFusion()
    assert abs(f._calculate_iou([0, 0, 1, 1], [0, 0, 1, 1]) - 1.0) < 1e-9


def test_iou_disjoint_boxes_is_zero():
    f = BoundingBoxFusion()
    assert f._calculate_iou([0, 0, 0.1, 0.1], [0.5, 0.5, 0.6, 0.6]) == 0.0


def test_iou_partial_overlap():
    f = BoundingBoxFusion()
    # Two unit boxes offset by half in each axis overlap on a quarter area.
    iou = f._calculate_iou([0, 0, 1, 1], [0.5, 0.5, 1.5, 1.5])
    # intersection 0.25, union 1 + 1 - 0.25 = 1.75
    assert abs(iou - (0.25 / 1.75)) < 1e-6


def test_normalize_bbox():
    f = BoundingBoxFusion()
    assert f._normalize_bbox((100, 50, 300, 150), 1000, 500) == [0.1, 0.1, 0.3, 0.3]


def test_expand_bbox_stays_within_unit_square():
    f = BoundingBoxFusion()
    out = f._expand_bbox([0.0, 0.0, 1.0, 1.0], 0.5)
    assert out[0] >= 0.0 and out[1] >= 0.0
    assert out[2] <= 1.0 and out[3] <= 1.0


def test_infer_role():
    f = BoundingBoxFusion()
    assert f._infer_role("OK") == "button"
    assert f._infer_role("Search here") == "input_field"
    assert f._infer_role("some label") == "text"


def test_fuse_ocr_only_produces_elements():
    f = BoundingBoxFusion()
    ocr = [
        {"text": "Save", "bbox_rect": (10, 10, 60, 30), "confidence": 0.9},
        {"text": "Cancel", "bbox_rect": (80, 10, 140, 30), "confidence": 0.9},
    ]
    elements = f.fuse(ocr, [], 200, 100, image=None)
    assert len(elements) >= 1
    texts = [e.text for e in elements]
    assert "Save" in texts or "Cancel" in texts
