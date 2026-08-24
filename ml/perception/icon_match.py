"""
ATLAS ML Pipeline - Icon / Template Matching
============================================
PIPELINE STEP 5b: Detect text-free UI elements (icons) and match reference
templates using classical computer vision only (OpenCV + numpy).

These are pure functions with no model calls, so they are fast and easy to
unit test. Outputs use the same dict shape that BoundingBoxFusion consumes
(bbox_normalized, role, confidence, source), so icon candidates can take part
directly in bounding box fusion (NON-CRIT-005).
"""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import cv2
from loguru import logger


def _to_gray(image: np.ndarray) -> np.ndarray:
    """
    Coerce an RGB, RGBA, single-channel, or already-gray image into a uint8
    grayscale array. Raises ValueError on an unsupported shape.
    """
    if image is None:
        raise ValueError("image is None")

    arr = np.asarray(image)
    if arr.size == 0:
        raise ValueError("image is empty")

    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)

    if arr.ndim == 2:
        return arr
    if arr.ndim == 3:
        channels = arr.shape[2]
        if channels == 4:
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2GRAY)
        if channels == 3:
            return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        if channels == 1:
            return arr[:, :, 0]
    raise ValueError(f"Unsupported image shape: {arr.shape}")


def _iou_px(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    """Intersection-over-union of two pixel boxes (x1, y1, x2, y2)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    x1, y1 = max(ax1, bx1), max(ay1, by1)
    x2, y2 = min(ax2, bx2), min(ay2, by2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    denom = area_a + area_b - inter
    return inter / denom if denom > 0 else 0.0


def detect_icon_candidates(
    image: np.ndarray,
    min_size: int = 10,
    max_size: int = 96,
    max_area_ratio: float = 0.02,
    min_contrast: float = 18.0,
    square_tolerance: float = 0.35,
    dedup_iou: float = 0.4,
    max_candidates: int = 64,
) -> List[Dict[str, Any]]:
    """
    Find small, roughly square, high-contrast regions that are likely icons
    (elements a text OCR pass would miss because they carry no text).

    The heuristic is: edge map -> morphological close so a glyph becomes one
    blob -> external contours -> filter each bounding box by size, squareness,
    and local contrast -> deduplicate overlaps keeping the higher confidence.

    Args:
        image: RGB / RGBA / grayscale screenshot as a numpy array.
        min_size: Minimum width and height in pixels for a candidate.
        max_size: Maximum width and height in pixels for a candidate.
        max_area_ratio: Reject boxes larger than this fraction of the image.
        min_contrast: Minimum grayscale std dev inside the box (contrast gate).
        square_tolerance: Allowed deviation from a 1:1 aspect ratio.
        dedup_iou: Overlap above which the lower-confidence box is dropped.
        max_candidates: Cap on returned candidates.

    Returns:
        List of dicts, each:
            {
              "bbox_normalized": [x1, y1, x2, y2] in 0-1,
              "role": "icon",
              "confidence": float 0-1,
              "source": "icon",
            }
        compatible with BoundingBoxFusion input. Returns [] on any failure.
    """
    candidates: List[Dict[str, Any]] = []
    try:
        gray = _to_gray(image)
        h, w = gray.shape[:2]
        if h == 0 or w == 0:
            return []

        edges = cv2.Canny(gray, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        img_area = float(w * h)
        low_aspect = 1.0 - square_tolerance
        high_aspect = 1.0 + square_tolerance

        raw: List[Dict[str, Any]] = []
        for contour in contours:
            x, y, bw, bh = cv2.boundingRect(contour)
            if bw < min_size or bh < min_size:
                continue
            if bw > max_size or bh > max_size:
                continue
            if bh == 0:
                continue

            aspect = bw / float(bh)
            if aspect < low_aspect or aspect > high_aspect:
                continue

            if (bw * bh) > (img_area * max_area_ratio):
                continue

            region = gray[y:y + bh, x:x + bw]
            if region.size == 0:
                continue
            contrast = float(region.std())
            if contrast < min_contrast:
                continue

            square_score = 1.0 - min(1.0, abs(aspect - 1.0))
            contrast_score = min(1.0, contrast / 80.0)
            confidence = round(0.30 + 0.35 * square_score + 0.35 * contrast_score, 4)

            raw.append({
                "bbox_px": (x, y, x + bw, y + bh),
                "bbox_normalized": [x / w, y / h, (x + bw) / w, (y + bh) / h],
                "role": "icon",
                "confidence": confidence,
                "source": "icon",
            })

        # Deduplicate overlapping detections, keeping the higher confidence one.
        raw.sort(key=lambda r: r["confidence"], reverse=True)
        kept: List[Dict[str, Any]] = []
        for cand in raw:
            if all(_iou_px(cand["bbox_px"], k["bbox_px"]) < dedup_iou for k in kept):
                kept.append(cand)
            if len(kept) >= max_candidates:
                break

        for k in kept:
            k.pop("bbox_px", None)
            candidates.append(k)
    except Exception as e:
        logger.warning(f"Icon candidate detection failed: {e}")

    return candidates


def match_template(
    image: np.ndarray,
    template: np.ndarray,
    method: int = cv2.TM_CCOEFF_NORMED,
) -> Optional[Dict[str, Any]]:
    """
    Locate a reference icon (template) inside a larger image via normalized
    template matching.

    Args:
        image: RGB / RGBA / grayscale screenshot as a numpy array.
        template: The reference icon to search for (same channel conventions).
        method: OpenCV matchTemplate method. Defaults to TM_CCOEFF_NORMED.

    Returns:
        On success, a dict:
            {
              "bbox_normalized": [x1, y1, x2, y2] in 0-1,
              "score": float,          # raw match score (higher is better)
              "confidence": float,     # score clamped to 0-1
              "role": "icon",
              "source": "icon",
            }
        Returns None if the template is empty, larger than the image, or on any
        failure. The result is BoundingBoxFusion-compatible.
    """
    try:
        img_gray = _to_gray(image)
        tpl_gray = _to_gray(template)

        ih, iw = img_gray.shape[:2]
        th, tw = tpl_gray.shape[:2]
        if th == 0 or tw == 0 or th > ih or tw > iw:
            logger.debug("match_template: template empty or larger than image")
            return None

        result = cv2.matchTemplate(img_gray, tpl_gray, method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if method in (cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED):
            top_left = min_loc
            score = 1.0 - float(min_val)
        else:
            top_left = max_loc
            score = float(max_val)

        x, y = top_left
        bbox_normalized = [x / iw, y / ih, (x + tw) / iw, (y + th) / ih]

        return {
            "bbox_normalized": bbox_normalized,
            "score": round(score, 4),
            "confidence": round(max(0.0, min(1.0, score)), 4),
            "role": "icon",
            "source": "icon",
        }
    except Exception as e:
        logger.warning(f"Template matching failed: {e}")
        return None
