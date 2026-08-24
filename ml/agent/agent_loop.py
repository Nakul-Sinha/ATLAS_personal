"""
ATLAS ML Pipeline - Agent Loop
===============================
Main agent loop: PERCEIVE → UNDERSTAND → PLAN → ACT → VERIFY → repeat
"""

import time
from loguru import logger

from models import LLMModel
from perception import PerceptionEngine, detect_modal, detect_icon_candidates, window_state
from actions import ActionExecutor, ClickAction, TypeAction, KeyAction, ScrollAction, WaitAction
from agent.state import AgentState, AgentStatus
from agent.verification import Verifier
from agent.error_taxonomy import classify_error, recovery_hint, ErrorType
from agent.app_context import AppContextManager
from memory import Memory
from memory.memory import PatternRecord
from config import config


class AgentLoop:
    """
    Main agent control loop implementing the core pipeline.
    
    Usage:
        agent = AgentLoop()
        agent.run("Open Notepad and type hello")
    """
    
    def __init__(self):
        self.llm = LLMModel()
        self.perception = PerceptionEngine(enable_vlm=config.vlm.use_vlm)
        self.executor = ActionExecutor()
        self.verifier = Verifier(self.perception)
        self.memory = Memory()
        self.state = AgentState()
        # Tracks the focused app across a multi-app task (NON-CRIT-003).
        self.app_context = AppContextManager()
        self._initialized = False
        # The element resolved for the most recent action, used when storing
        # a success pattern so the correct bbox is recorded.
        self._last_target = None

    def initialize(self) -> None:
        """Initialize all models."""
        if self._initialized:
            return
        logger.info("Initializing agent...")
        # CRITICAL-001: make the process DPI aware so captured pixels and click
        # pixels share one coordinate space before any capture happens.
        self.perception.screen_capture.set_dpi_awareness()
        detected_scale = self.perception.screen_capture.detect_dpi_scale()
        if abs(detected_scale - 1.0) > 0.01:
            logger.info(f"Display DPI scale is {detected_scale:.2f} (process is DPI aware)")
        self.llm.load()
        # Initialize perception (starts with OCR)
        self.perception.initialize_ocr()
        if config.vlm.use_vlm:
            self.perception.initialize_vlm()
             
        self._initialized = True
        logger.info("Agent ready")
        
    def run(self, user_prompt: str) -> bool:
        """
        Execute a user task.
        
        Args:
            user_prompt: Natural language instruction
            
        Returns:
            True if task completed successfully
        """
        if not self._initialized:
            self.initialize()
            
        self.state.reset()
        self.state.status = AgentStatus.RUNNING
        
        try:
            # STEP 1: Extract intent
            logger.info(f"Processing: {user_prompt}")
            self.state.intent = self.llm.extract_intent(user_prompt)
            logger.info(f"Intent: {self.state.intent.goal}")

            # CRITICAL-003: if the target app is already open but not focused,
            # bring it to the front so the screen capture shows the right window.
            if self.state.intent and self.state.intent.app:
                try:
                    if not window_state.is_app_focused(self.state.intent.app):
                        if window_state.bring_to_front(self.state.intent.app):
                            logger.info(f"Focused existing window for {self.state.intent.app}")
                except Exception as e:
                    logger.debug(f"Window focus pre-check skipped: {e}")

            # STEP 2: Create task plan
            self.state.task_steps = self.llm.create_task_plan(self.state.intent)
            if not self.state.task_steps:
                logger.error("Failed to create task plan")
                return False
                
            logger.info(f"Plan: {len(self.state.task_steps)} steps")
            for s in self.state.task_steps:
                logger.info(f"  {s.step_number}. {s.description}")
            
            # Main loop
            while not self.state.is_complete and self.state.status == AgentStatus.RUNNING:
                success = self._execute_step()
                
                if not success:
                    recovery = self._handle_failure()
                    if recovery == "retry":
                        continue
                    elif recovery == "skip":
                        self.state.retry_count = 0
                        self.state.advance_step()
                        continue
                    else:  # abort
                        self.state.status = AgentStatus.FAILED
                        logger.error("Task aborted after failure")
                        return False
                
                # Store successful pattern in memory
                self._store_success_pattern()
                
                # Reset retry count on success
                self.state.retry_count = 0
                self.state.advance_step()
            
            self.state.status = AgentStatus.COMPLETED
            logger.info("Task completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Agent error: {e}")
            self.state.status = AgentStatus.FAILED
            self.state.last_error = str(e)
            return False
    
    def _execute_step(self) -> bool:
        """Execute one step of the task."""
        step = self.state.current_step
        if not step:
            return True
            
        logger.info(f"Executing Step {step.step_number}: {step.description}")

        # NON-CRIT-003: if this step implies another app, focus it first so the
        # capture shows the right window (for example "paste into Word").
        try:
            target_app = self.app_context.detect_app_switch(step.description)
            if target_app and target_app != self.app_context.current_app:
                if self.app_context.switch_app(target_app):
                    logger.info(f"Switched context to {target_app}")
        except Exception as e:
            logger.debug(f"App switch skipped: {e}")

        # STEP 3-6: Perceive. OCR-only is the fast default (~5s). When
        # cross-validation is enabled, fuse OCR with the VLM (cached for static
        # screens, NON-CRIT-004) and add text-free icon candidates (NON-CRIT-005).
        if getattr(config.vlm, "cross_validate", False):
            self.state.perception = self.perception.perceive_fused(use_cache=True)
            if getattr(config.vlm, "use_icons", True):
                try:
                    icons = detect_icon_candidates(self.state.perception.frame.image)
                    if icons:
                        self.state.perception.fused_elements = self.perception.fusion.fuse(
                            self.state.perception.ocr_results,
                            self.state.perception.vlm_regions,
                            self.state.perception.frame.width,
                            self.state.perception.frame.height,
                            self.state.perception.frame.image,
                            icon_regions=icons,
                        )
                except Exception as e:
                    logger.debug(f"Icon detection skipped: {e}")
        else:
            self.state.perception = self.perception.quick_perceive()

        # CRITICAL-002: notice a blocking modal dialog before planning an action.
        try:
            modal = detect_modal(self.state.perception.frame.image)
            if modal:
                logger.warning(
                    f"Possible modal dialog detected (area {modal['area_ratio']}, "
                    f"confidence {modal['confidence']}); planning should address it first"
                )
        except Exception as e:
            logger.debug(f"Modal detection skipped: {e}")

        # Log detected elements count
        num_elements = len(self.state.perception.fused_elements)
        logger.debug(f"Perceived {num_elements} UI elements")
        
        elements = [e.to_dict() for e in self.state.perception.fused_elements]
        
        # STEP 7: Plan action
        planned = self.llm.plan_action(
            screen_description=self.state.perception.screen_description or f"Screen with {num_elements} elements",
            available_elements=elements,
            current_step=step,
            history=self.state.get_recent_actions()
        )
        self.state.current_action = planned
        logger.info(f"Planned action: {planned.action_type} on {planned.target_text or planned.target_role or 'screen'}")
        
        # Boost confidence from memory
        if self.state.intent and self.state.intent.app:
            boost = self.memory.get_confidence_boost(
                self.state.intent.app, 
                planned.target_role or "",
                planned.target_text
            )
            if boost > 0:
                planned.confidence = min(1.0, planned.confidence + boost)
                logger.debug(f"Memory confidence boost: +{boost:.2f} -> {planned.confidence:.2f}")
        
        if planned.confidence < 0.3:
            logger.warning(f"Low confidence action: {planned.confidence}")
        
        # STEP 8: Resolve coordinates
        action = self._resolve_action(planned)
        if action is None:
            logger.error(f"Failed to resolve action coordinates for {planned.target_text or planned.target_role}")
            return False
        
        # Store pre-action perception
        before = self.state.perception
        
        # STEP 9: Execute
        logger.info(f"Executing: {action.describe()}")
        success = self.executor.execute(action)
        
        if not success:
            logger.error("Execution failed at OS level")
            self.state.record_action(planned, False, False, "Execution failed")
            return False
        
        # STEP 10: Verify
        verification = self.verifier.verify(planned, before)
        
        logger.info(f"Verification: {'PASSED' if verification.passed else 'FAILED'} ({verification.confidence:.2f}) - {verification.reason}")
        
        self.state.record_action(planned, True, verification.passed, 
                                 None if verification.passed else verification.reason)
        
        if not verification.passed:
            return False
            
        return True
    
    def _resolve_action(self, planned):
        """Convert planned action to executable action with coordinates."""
        frame = self.state.perception.frame
        
        # Find target element
        target = None
        
        # 1. Try exact text match
        if planned.target_text:
            target = self.state.perception.get_element_by_text(planned.target_text, fuzzy=False)
            if not target:
                # 2. Try fuzzy text match
                target = self.state.perception.get_element_by_text(planned.target_text, fuzzy=True)
        
        # 3. Try role match if no text target or text match failed
        if not target and planned.target_role:
            target = self.state.perception.get_element_by_role(planned.target_role)
        
        # 4. If multiple candidates, use LLM to rank them
        if not target and planned.target_text:
            candidates = self.state.perception.get_all_by_text(planned.target_text, fuzzy=True)
            if len(candidates) > 1:
                ranked = self.llm.rank_candidates(
                    [c.to_dict() for c in candidates],
                    planned.target_text
                )
                if ranked and ranked[0].get("relevance_score", 0) > 0.5:
                    # Map the top-ranked entry back to its element by bbox, so we
                    # actually use the element the LLM chose (not the first one).
                    top = ranked[0]
                    target = next(
                        (c for c in candidates if c.to_dict().get("bbox") == top.get("bbox")),
                        candidates[0],
                    )
                    logger.debug(f"LLM ranked candidate: {target.text}")
        
        # Debug log result
        if target:
            logger.debug(f"Resolved target: {target.text or target.role} at {target.center}")
        elif planned.target_text or planned.target_role:
            logger.warning(f"Target not found: text='{planned.target_text}', role='{planned.target_role}'")
        
        # Remember which element we resolved so success patterns store its bbox.
        self._last_target = target

        if planned.action_type == "click":
            if target:
                cx, cy = target.center
                # Route through to_absolute so the monitor offset (and any DPI
                # scale) is applied; fixes off-target clicks on non-primary
                # monitors (CRITICAL-004).
                x, y = frame.to_absolute(cx, cy)
                return ClickAction(x=x, y=y, confidence=planned.confidence)
            logger.error("Click validation failed: No target element found")
            return None

        elif planned.action_type == "type":
            return TypeAction(text=planned.text or "", confidence=planned.confidence)

        elif planned.action_type == "key":
            return KeyAction(key=planned.key or "", confidence=planned.confidence)

        elif planned.action_type == "scroll":
            x, y = frame.to_absolute(0.5, 0.5)
            if target:
                cx, cy = target.center
                x, y = frame.to_absolute(cx, cy)
            return ScrollAction(x=x, y=y, direction=planned.direction or "down",
                                confidence=planned.confidence)
        
        elif planned.action_type == "wait":
            return WaitAction(duration=1.0)
        
        return None
    
    def _handle_failure(self) -> str:
        """
        Handle a failed step using LLM-guided error recovery.
        
        Returns:
            "retry" - retry the same step
            "skip" - skip to next step
            "abort" - stop the task
        """
        if not self.state.can_retry:
            logger.error("Max retries exceeded")
            return "abort"
        
        self.state.retry_count += 1
        self.state.status = AgentStatus.RETRYING
        
        step = self.state.current_step
        last_action = self.state.current_action
        last_error = self.state.last_error or "Verification failed"
        
        # Get the last action record's error if available
        if self.state.action_history:
            last_record = self.state.action_history[-1]
            if last_record.error:
                last_error = last_record.error
        
        logger.warning(f"Step {step.step_number} failed (attempt {self.state.retry_count}): {last_error}")

        # NON-CRIT-001: classify the failure so recovery is grounded per category
        # instead of generic. An infeasible task is skipped rather than retried.
        err_type = classify_error(last_error, {
            "action_type": getattr(last_action, "action_type", None),
            "stage": "verification",
        })
        logger.info(f"Error class: {err_type.name} | hint: {recovery_hint(err_type)}")
        if err_type is ErrorType.TASK:
            logger.info("Task-level failure classified as infeasible; skipping step")
            return "skip"

        # Ask LLM for recovery strategy
        try:
            screen_desc = ""
            if self.state.perception:
                screen_desc = self.state.perception.screen_description or f"Screen with {len(self.state.perception.fused_elements)} elements"

            recovery = self.llm.handle_error(
                error_description=f"{last_error} (classified as {err_type.name}: {recovery_hint(err_type)})",
                screen_state=screen_desc,
                last_action=last_action,
                retry_count=self.state.retry_count
            )
            
            strategy = recovery.get("strategy", "retry")
            reason = recovery.get("reason", "")
            logger.info(f"LLM recovery strategy: {strategy} - {reason}")
            
            if strategy == "abort":
                return "abort"
            elif strategy == "skip":
                return "skip"
            else:
                # retry or replan — both result in re-executing the step
                time.sleep(1.0)
                self.state.status = AgentStatus.RUNNING
                return "retry"
                
        except Exception as e:
            logger.warning(f"LLM error recovery failed, defaulting to retry: {e}")
            time.sleep(1.0)
            self.state.status = AgentStatus.RUNNING
            return "retry"
    
    def _store_success_pattern(self) -> None:
        """Store successful action pattern in memory for future confidence boosting."""
        try:
            action = self.state.current_action
            if not action or not self.state.intent:
                return
            
            app_name = self.state.intent.app or "unknown"
            # Record the bbox of the element actually acted on, not an arbitrary
            # element on screen (CRITICAL / ML-07).
            if self._last_target is not None:
                bbox_relative = list(self._last_target.bbox_normalized)
            else:
                bbox_relative = [0, 0, 0, 0]
            self.memory.store(PatternRecord(
                app_name=app_name,
                element_role=action.target_role or "unknown",
                element_text=action.target_text,
                bbox_relative=bbox_relative,
                action_type=action.action_type
            ))
        except Exception as e:
            logger.debug(f"Failed to store pattern (non-critical): {e}")
    
    def stop(self) -> None:
        """Stop the agent."""
        self.state.status = AgentStatus.IDLE
        self.memory.close()
        logger.info("Agent stopped")
