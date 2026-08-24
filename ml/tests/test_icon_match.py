"""Icon detection and template matching (NON-CRIT-005). Synthetic images.

Icons are drawn with internal structure (not flat blocks) so that normalized
template correlation is well defined, the way real icons behave.
"""

import numpy as np

from perception.icon_match import detect_icon_candidates, match_template


def _bordered_icon(img, y, x):
    img[y:y + 24, x:x + 24] = 245
    img[y + 6:y + 18, x + 6:x + 18] = 55


def _screen_with_icons():
    img = np.full((400, 400, 3), 130, dtype=np.uint8)
    _bordered_icon(img, 40, 40)
    _bordered_icon(img, 40, 320)
    # A unique checker-patterned icon at the bottom-left.
    img[340:364, 40:64] = 55
    img[340:352, 40:52] = 245
    img[352:364, 52:64] = 245
    return img


def test_detects_icon_candidates():
    icons = detect_icon_candidates(_screen_with_icons())
    assert isinstance(icons, list)
    assert len(icons) >= 1
    for ic in icons:
        assert ic["role"] == "icon"
        assert ic["source"] == "icon"
        b = ic["bbox_normalized"]
        assert len(b) == 4
        assert all(0.0 <= v <= 1.0 for v in b)


def test_plain_screen_has_no_icons():
    plain = np.full((400, 400, 3), 130, dtype=np.uint8)
    assert detect_icon_candidates(plain) == []


def test_match_template_finds_unique_icon():
    img = _screen_with_icons()
    # The checker icon is unique and has internal structure.
    template = img[340:364, 40:64].copy()
    hit = match_template(img, template)
    assert hit is not None
    assert hit["score"] > 0.9
    x1, y1, x2, y2 = hit["bbox_normalized"]
    assert abs(x1 - 40 / 400) < 0.05
    assert abs(y1 - 340 / 400) < 0.05


def test_match_template_rejects_oversized_template():
    img = np.full((50, 50, 3), 130, dtype=np.uint8)
    template = np.full((80, 80, 3), 245, dtype=np.uint8)
    assert match_template(img, template) is None
