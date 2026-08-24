"""
ATLAS ML Pipeline - Perception Engine
======================================
Orchestrates OCR, VLM, and fusion for complete screen understanding.
PIPELINE STEPS 3-6 combined.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from loguru import logger

from models import OCRModel
from perception.screen_capture import ScreenCapture, ScreenFrame
from perception.bbox_fusion import BoundingBoxFusion, FusedElement


@dataclass
class PerceptionResult:
    """Complete perception result for one screen capture."""
    frame: ScreenFrame
    ocr_results: List[Dict[str, Any]]
    vlm_regions: List[Dict[str, Any]]
    fused_elements: List[FusedElement]
    screen_description: str
    
    def get_element_by_role(self, role: str) -> Optional[FusedElement]:
        for e in self.fused_elements:
            if e.role == role:
                return e
        return None
    
    def get_element_by_text(self, text: str, fuzzy: bool = True) -> Optional[FusedElement]:
        for e in self.fused_elements:
            if e.text:
                if fuzzy and text.lower() in e.text.lower():
                    return e
                elif e.text.lower() == text.lower():
                    return e
        return None
    
    def get_all_by_role(self, role: str) -> List[FusedElement]:
        """Get all elements with specified role."""
        return [e for e in self.fused_elements if e.role == role]
    
    def get_all_by_text(self, text: str, fuzzy: bool = True) -> List[FusedElement]:
        """Get all elements matching text."""
        matches = []
        text_lower = text.lower()
        for e in self.fused_elements:
            if e.text:
                if fuzzy and text_lower in e.text.lower():
                    matches.append(e)
                elif e.text.lower() == text_lower:
                    matches.append(e)
        return matches


class PerceptionEngine:
    """
    Complete perception pipeline combining screen capture, OCR, VLM, and fusion.
    
    VLM is optional and can be skipped for speed in quick_perceive().
    
    Usage:
        engine = PerceptionEngine()
        result = engine.quick_perceive()  # Fast, OCR only
        element = result.get_element_by_text("Search")
    """
    
    def __init__(self, enable_vlm: bool = False):
        """
        Initialize perception engine.
        
        Args:
            enable_vlm: If True, load VLM model (slow, requires GPU).
                        If False (default), use OCR only.
        """
        self.screen_capture = ScreenCapture()
        self.ocr = OCRModel()
        self.vlm = None  # Lazy load if needed
        self.fusion = BoundingBoxFusion()
        self._ocr_initialized = False
        self._vlm_initialized = False
        self._enable_vlm = enable_vlm
        
    def initialize_ocr(self) -> None:
        """Load OCR model. Called automatically."""
        if self._ocr_initialized:
            return
        logger.info("Loading OCR model...")
        self.ocr.load()
        self._ocr_initialized = True
        logger.info("OCR ready")
    
    def initialize_vlm(self) -> None:
        """Load VLM model (optional, slow)."""
        if self._vlm_initialized:
            return
        try:
            from models import VLMModel
            logger.info("Loading VLM model (this may take a while)...")
            self.vlm = VLMModel()
            self.vlm.load()
            self._vlm_initialized = True
            logger.info("VLM ready")
        except Exception as e:
            logger.warning(f"VLM load failed (continuing without VLM): {e}")
            self._vlm_initialized = False
        
    def perceive(self, monitor: Optional[int] = None, use_vlm: bool = False) -> PerceptionResult:
        """
        Run complete perception pipeline.
        
        Args:
            monitor: Monitor to capture (None for default)
            use_vlm: Whether to run VLM (can skip for speed)
        """
        # Initialize OCR on first use
        if not self._ocr_initialized:
            self.initialize_ocr()
        
        # Initialize VLM if requested and enabled
        if use_vlm and self._enable_vlm and not self._vlm_initialized:
            self.initialize_vlm()
        
        # Step 3: Screen capture
        frame = self.screen_capture.grab(monitor)
        logger.debug(f"Captured {frame.width}x{frame.height}")
        
        # Step 4: OCR
        ocr_raw = self.ocr.detect(frame.image)
        ocr_results = [{"text": r.text, "bbox": r.bbox, "bbox_rect": r.bbox_rect, 
                        "confidence": r.confidence} for r in ocr_raw]
        
        # Step 5: VLM (optional)
        vlm_regions = []
        screen_description = ""
        if use_vlm and self._vlm_initialized and self.vlm is not None:
            try:
                vlm_raw = self.vlm.detect_ui_elements(frame.image)
                vlm_regions = [{"role": r.role, "description": r.description,
                               "bbox_normalized": r.bbox_normalized, "confidence": r.confidence} for r in vlm_raw]
                screen_description = self.vlm.describe_screen(frame.image)
            except Exception as e:
                logger.warning(f"VLM failed, continuing without: {e}")
        
        # Step 6: Fusion
        fused = self.fusion.fuse(ocr_results, vlm_regions, frame.width, frame.height, frame.image)
        
        return PerceptionResult(
            frame=frame, ocr_results=ocr_results, vlm_regions=vlm_regions,
            fused_elements=fused, screen_description=screen_description
        )
    
    def quick_perceive(self, monitor: Optional[int] = None) -> PerceptionResult:
        """Fast perception using only OCR (no VLM)."""
        return self.perceive(monitor, use_vlm=False)
    
    def full_perceive(self, monitor: Optional[int] = None) -> PerceptionResult:
        """Full perception with VLM (slow, requires GPU)."""
        if not self._enable_vlm:
            logger.warning("VLM not enabled. Use enable_vlm=True in constructor.")
        return self.perceive(monitor, use_vlm=True)
