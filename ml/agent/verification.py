"""
ATLAS ML Pipeline - Verification
=================================
Visual verification after actions.
PIPELINE STEP 10
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
import time

from perception.perception_engine import PerceptionEngine, PerceptionResult
from models.llm_model import PlannedAction
from config import config


@dataclass
class VerificationResult:
    """Result of visual verification."""
    passed: bool
    confidence: float
    reason: str
    before_state: Optional[Dict] = None
    after_state: Optional[Dict] = None


class Verifier:
    """
    Verifies that actions had their intended effect via visual comparison.
    
    Usage:
        verifier = Verifier(perception_engine)
        result = verifier.verify(action, before_perception, after_perception)
    """
    
    def __init__(self, perception: PerceptionEngine):
        self.perception = perception
        self.delay = config.verification.verification_delay
        self.confidence_threshold = config.verification.confidence_threshold
        
    def verify(self, action: PlannedAction, 
               before: PerceptionResult,
               after: Optional[PerceptionResult] = None) -> VerificationResult:
        """
        Verify an action had its intended effect.
        
        Args:
            action: The action that was executed
            before: Perception before action
            after: Perception after action (captured if not provided)
        """
        # Wait for UI to update
        time.sleep(self.delay)
        
        # Capture new state if not provided
        if after is None:
            after = self.perception.quick_perceive()
        
        # Verify based on action type
        if action.action_type == "click":
            return self._verify_click(action, before, after)
        elif action.action_type == "type":
            return self._verify_type(action, before, after)
        elif action.action_type == "key":
            return self._verify_key(action, before, after)
        else:
            # For scroll/wait, just check screen changed
            return self._verify_generic(before, after)
    
    def _verify_click(self, action: PlannedAction, 
                      before: PerceptionResult, 
                      after: PerceptionResult) -> VerificationResult:
        """Verify click action."""
        reasons = []
        confidence = 0.0
        
        # 1. Check for text changes (OCR)
        before_texts = {e.text for e in before.fused_elements if e.text}
        after_texts = {e.text for e in after.fused_elements if e.text}
        new_texts = after_texts - before_texts
        
        if new_texts:
            reasons.append(f"New text detected: {list(new_texts)[:3]}")
            confidence += 0.4
            
        # 2. Check for visual changes (create diff)
        diff_score, diff_percent = self._calculate_visual_diff(before.frame.image, after.frame.image)
        
        if diff_percent > 1.0:  # >1% pixels changed (Significant)
            reasons.append(f"Visual change detected ({diff_percent:.2f}%)")
            confidence += 0.4
        elif diff_percent > 0.1:  # >0.1% pixels changed (Subtle)
            reasons.append(f"Minor visual change detected ({diff_percent:.2f}%)")
            confidence += 0.2
            
        # 3. Check if text count changed significantly
        before_count = len(before.ocr_results)
        after_count = len(after.ocr_results)
        if abs(after_count - before_count) > 2:
            reasons.append(f"Text count changed: {before_count} -> {after_count}")
            confidence += 0.2
            
        passed = confidence >= self.confidence_threshold
        # If visual change is massive, pass even if confidence is low
        if diff_percent > 5.0:
            passed = True
            confidence = max(confidence, 0.8)
            
        return VerificationResult(
            passed=passed,
            confidence=min(confidence, 1.0),
            reason="; ".join(reasons) if reasons else "No significant change detected"
        )
    
    def _verify_type(self, action: PlannedAction,
                     before: PerceptionResult,
                     after: PerceptionResult) -> VerificationResult:
        """Verify text was typed."""
        typed_text = action.text or ""
        
        # Look for the typed text in OCR results
        for result in after.ocr_results:
            ocr_text = result.get("text", "").lower()
            if typed_text.lower() in ocr_text:
                return VerificationResult(
                    passed=True, confidence=0.9,
                    reason=f"Typed text '{typed_text}' found on screen"
                )
        
        # Visual check as fallback
        diff_score, diff_percent = self._calculate_visual_diff(before.frame.image, after.frame.image)
        if diff_percent > 0.1: # Typing should change >0.1% pixels
            return VerificationResult(
                passed=True, confidence=0.5,
                reason=f"Visual change detected during typing ({diff_percent:.2f}%)"
            )
            
        return VerificationResult(
            passed=False, confidence=0.2,
            reason="Typed text not found and no visual change"
        )
    
    def _verify_key(self, action: PlannedAction,
                    before: PerceptionResult,
                    after: PerceptionResult) -> VerificationResult:
        """Verify key press."""
        key = action.key or ""
        
        # Visual check
        diff_score, diff_percent = self._calculate_visual_diff(before.frame.image, after.frame.image)
        
        # Keys like Enter usually cause big changes
        if key.lower() in ["enter", "return"]:
            if diff_percent > 1.0:  # >1% change
                return VerificationResult(passed=True, confidence=0.8, 
                                          reason=f"Significant screen update after Enter ({diff_percent:.2f}%)")
            elif diff_percent > 0.1:
                return VerificationResult(passed=True, confidence=0.6,
                                          reason=f"Moderate screen update after Enter ({diff_percent:.2f}%)")
                                          
        # General key press check
        if diff_percent > 0.1:
             return VerificationResult(passed=True, confidence=0.5,
                                       reason=f"Screen update detected ({diff_percent:.2f}%)")
                                       
        return VerificationResult(passed=False, confidence=0.2,
                                  reason="No visual change detected after key press")
    
    def _verify_generic(self, before: PerceptionResult,
                        after: PerceptionResult) -> VerificationResult:
        """Generic verification: did anything change?"""
        diff_score, diff_percent = self._calculate_visual_diff(before.frame.image, after.frame.image)
        
        if diff_percent > 1.0:
            return VerificationResult(passed=True, confidence=0.7,
                                      reason=f"Screen content changed ({diff_percent:.2f}%)")
        elif diff_percent > 0.1:
             return VerificationResult(passed=True, confidence=0.4,
                                       reason=f"Minor visual change ({diff_percent:.2f}%)")
                                       
        return VerificationResult(passed=True, confidence=0.3, # Passed but low confidence
                                  reason="Action executed (no significant change)")

    def _calculate_visual_diff(self, img1: Any, img2: Any) -> tuple:
        """
        Calculate visual difference between two images.
        Returns: (mse, percent_changed)
        """
        import cv2
        import numpy as np
        
        # Ensure images are same size
        if img1.shape != img2.shape:
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            
        # Convert to grayscale
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        
        # Compute absolute difference
        diff = cv2.absdiff(gray1, gray2)
        
        # Threshold to find changed pixels
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
        
        # Calculate percentage of changed pixels
        total_pixels = thresh.size
        changed_pixels = cv2.countNonZero(thresh)
        percent_changed = (changed_pixels / total_pixels) * 100
        
        # Calculate Mean Squared Error
        mse = np.mean((gray1 - gray2) ** 2)
        
        return mse, percent_changed
