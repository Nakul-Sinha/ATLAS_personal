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

    def perceive_fused(self, monitor: Optional[int] = None,
                       use_cache: bool = True) -> PerceptionResult:
        """
        Fused perception that always runs OCR and adds VLM cross-validation
        when the VLM is initialized (NON-CRIT-004).

        OCR runs on every call. The VLM runs only when it has already been
        initialized (self._vlm_initialized); when enable_vlm was set in the
        constructor but the model has not loaded yet, it is initialized here
        opportunistically. OCR and VLM detections are then fused through
        BoundingBoxFusion, which is where the two sources cross-validate each
        other.

        The VLM per-screen cache is reused for static screens, so repeatedly
        perceiving an unchanged screen does not pay the full VLM latency again.
        This is additive: quick_perceive() and full_perceive() are unchanged.

        Args:
            monitor: Monitor to capture (None for the configured default).
            use_cache: Reuse the VLM result cache for near-identical static
                       screens. Set False to force a fresh VLM query.

        Returns:
            PerceptionResult with fused OCR + VLM elements.
        """
        # OCR is always required.
        if not self._ocr_initialized:
            self.initialize_ocr()

        # Load the VLM opportunistically when it was enabled but not yet loaded.
        if self._enable_vlm and not self._vlm_initialized:
            self.initialize_vlm()

        # Step 3: Screen capture
        frame = self.screen_capture.grab(monitor)
        logger.debug(f"perceive_fused captured {frame.width}x{frame.height}")

        # Step 4: OCR (always)
        ocr_raw = self.ocr.detect(frame.image)
        ocr_results = [{"text": r.text, "bbox": r.bbox, "bbox_rect": r.bbox_rect,
                        "confidence": r.confidence} for r in ocr_raw]

        # Step 5: VLM (only when initialized), reusing its static-screen cache.
        vlm_regions: List[Dict[str, Any]] = []
        screen_description = ""
        if self._vlm_initialized and self.vlm is not None:
            prev_cache_enabled = getattr(self.vlm, "cache_enabled", None)
            try:
                if prev_cache_enabled is not None:
                    self.vlm.cache_enabled = use_cache
                vlm_raw = self.vlm.detect_ui_elements(frame.image)
                vlm_regions = [{"role": r.role, "description": r.description,
                                "bbox_normalized": r.bbox_normalized,
                                "confidence": r.confidence} for r in vlm_raw]
                screen_description = self.vlm.describe_screen(frame.image)
            except Exception as e:
                logger.warning(f"perceive_fused VLM step failed, continuing with OCR only: {e}")
            finally:
                if prev_cache_enabled is not None:
                    self.vlm.cache_enabled = prev_cache_enabled

        # Step 6: Fusion (cross-validates OCR and VLM boxes).
        fused = self.fusion.fuse(ocr_results, vlm_regions, frame.width, frame.height, frame.image)

        return PerceptionResult(
            frame=frame, ocr_results=ocr_results, vlm_regions=vlm_regions,
            fused_elements=fused, screen_description=screen_description
        )
