"""
ATLAS ML Pipeline - Bounding Box Fusion
========================================
PIPELINE STEP 6: Merges boxes from OCR, VLM, and geometry detection.
"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np
import cv2
from loguru import logger


@dataclass
class FusedElement:
    """A fused UI element from multiple detection sources."""
    role: str
    bbox_normalized: List[float]  # [x1, y1, x2, y2] in 0-1
    confidence: float
    sources: List[str] = field(default_factory=list)
    text: Optional[str] = None
    description: Optional[str] = None
    
    @property
    def center(self) -> Tuple[float, float]:
        x = (self.bbox_normalized[0] + self.bbox_normalized[2]) / 2
        y = (self.bbox_normalized[1] + self.bbox_normalized[3]) / 2
        return (x, y)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role, "bbox": self.bbox_normalized,
            "confidence": self.confidence, "text": self.text,
            "description": self.description, "sources": self.sources
        }


class BoundingBoxFusion:
    """Fuses bounding boxes from OCR, VLM, and geometric detection."""
    
    def __init__(self, iou_threshold: float = 0.5, expand_ratio: float = 0.1):
        self.iou_threshold = iou_threshold
        self.expand_ratio = expand_ratio
        
    def fuse(self, ocr_results: List[Dict], vlm_regions: List[Dict],
             screen_width: int, screen_height: int, image: Optional[np.ndarray] = None,
             icon_regions: Optional[List[Dict]] = None) -> List[FusedElement]:
        """
        Fuse all bounding box sources into unified elements.

        Args:
            ocr_results: OCR detections (text + boxes).
            vlm_regions: VLM UI regions.
            screen_width: Frame width in pixels.
            screen_height: Frame height in pixels.
            image: Optional frame used for geometric detection.
            icon_regions: Optional icon candidates (for example from
                perception.detect_icon_candidates / match_template). Each is a
                dict with bbox_normalized, role, confidence, and source. When
                provided they participate in fusion alongside OCR/VLM boxes so
                text-free icons are not lost (NON-CRIT-005). Backward
                compatible: existing callers that omit this are unchanged.
        """
        all_boxes = []

        for ocr in ocr_results:
            bbox = ocr.get("bbox_rect") or self._polygon_to_rect(ocr.get("bbox", []))
            bbox_norm = self._normalize_bbox(bbox, screen_width, screen_height)
            bbox_norm = self._expand_bbox(bbox_norm, self.expand_ratio)
            all_boxes.append({"bbox_normalized": bbox_norm, "role": self._infer_role(ocr.get("text", "")),
                              "text": ocr.get("text"), "confidence": ocr.get("confidence", 0.8), "source": "ocr"})

        for vlm in vlm_regions:
            all_boxes.append({"bbox_normalized": vlm.get("bbox_normalized", [0,0,1,1]), "role": vlm.get("role", "unknown"),
                              "description": vlm.get("description"), "confidence": vlm.get("confidence", 0.7), "source": "vlm"})

        if image is not None:
            all_boxes.extend(self._detect_geometric(image, screen_width, screen_height))

        if icon_regions:
            for icon in icon_regions:
                all_boxes.append({"bbox_normalized": icon.get("bbox_normalized", [0, 0, 1, 1]),
                                  "role": icon.get("role", "icon"),
                                  "description": icon.get("description"),
                                  "confidence": icon.get("confidence", 0.5),
                                  "source": icon.get("source", "icon")})

        merged = self._merge_overlapping(all_boxes)
        elements = [FusedElement(role=b["role"], bbox_normalized=b["bbox_normalized"], confidence=b["confidence"],
                                  sources=b.get("sources", [b.get("source")]), text=b.get("text"), description=b.get("description")) for b in merged]
        elements.sort(key=lambda x: x.confidence, reverse=True)
        return elements
    
    def _normalize_bbox(self, bbox: Tuple, w: int, h: int) -> List[float]:
        return [bbox[0]/w, bbox[1]/h, bbox[2]/w, bbox[3]/h]
    
    def _expand_bbox(self, bbox: List[float], r: float) -> List[float]:
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        return [max(0,bbox[0]-w*r), max(0,bbox[1]-h*r), min(1,bbox[2]+w*r), min(1,bbox[3]+h*r)]
    
    def _polygon_to_rect(self, poly: List) -> Tuple:
        if not poly: return (0,0,0,0)
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        return (min(xs), min(ys), max(xs), max(ys))
    
    def _calculate_iou(self, b1: List, b2: List) -> float:
        x1, y1 = max(b1[0],b2[0]), max(b1[1],b2[1])
        x2, y2 = min(b1[2],b2[2]), min(b1[3],b2[3])
        if x2<=x1 or y2<=y1: return 0.0
        inter = (x2-x1)*(y2-y1)
        a1, a2 = (b1[2]-b1[0])*(b1[3]-b1[1]), (b2[2]-b2[0])*(b2[3]-b2[1])
        return inter/(a1+a2-inter) if (a1+a2-inter)>0 else 0.0
    
    def _merge_overlapping(self, boxes: List[Dict]) -> List[Dict]:
        merged, used = [], set()
        for i, b1 in enumerate(boxes):
            if i in used: continue
            group, used = [b1], used | {i}
            for j, b2 in enumerate(boxes):
                if j not in used and self._calculate_iou(b1["bbox_normalized"], b2["bbox_normalized"]) >= self.iou_threshold:
                    group.append(b2); used.add(j)
            merged.append(self._merge_group(group))
        return merged
    
    def _merge_group(self, group: List[Dict]) -> Dict:
        if len(group)==1: return group[0]
        bboxes = [b["bbox_normalized"] for b in group]
        return {"bbox_normalized": [sum(b[i] for b in bboxes)/len(bboxes) for i in range(4)],
                "confidence": max(b["confidence"] for b in group), "sources": list(set(b.get("source") for b in group)),
                "role": next((b["role"] for b in group if b.get("source")=="vlm" and b["role"]!="unknown"), group[0]["role"]),
                "text": next((b.get("text") for b in group if b.get("text")), None),
                "description": next((b.get("description") for b in group if b.get("description")), None)}
    
    def _infer_role(self, text: str) -> str:
        t = text.lower()
        if t in ["ok","cancel","submit","save","close","open","next","back","yes","no"]: return "button"
        if any(k in t for k in ["search","enter","email","password"]): return "input_field"
        return "text"
    
    def _detect_geometric(self, image: np.ndarray, w: int, h: int) -> List[Dict]:
        boxes = []
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            contours, _ = cv2.findContours(cv2.Canny(gray, 50, 150), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                approx = cv2.approxPolyDP(c, 0.02*cv2.arcLength(c,True), True)
                if len(approx)==4:
                    x,y,bw,bh = cv2.boundingRect(approx)
                    if 100 < bw*bh < w*h*0.5 and 1.5 < bw/bh < 10:
                        boxes.append({"bbox_normalized": self._normalize_bbox((x,y,x+bw,y+bh),w,h),
                                      "role": "input_field" if bw/bh>4 else "button", "confidence": 0.4, "source": "geometric"})
        except Exception as e: logger.warning(f"Geometric detection failed: {e}")
        return boxes
