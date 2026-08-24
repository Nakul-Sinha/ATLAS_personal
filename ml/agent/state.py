"""
ATLAS ML Pipeline - Agent State
================================
Tracks current state of the agent during execution.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

from models.llm_model import Intent, TaskStep, PlannedAction
from perception.perception_engine import PerceptionResult


class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_VERIFICATION = "waiting_verification"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ActionRecord:
    """Record of an executed action."""
    action: PlannedAction
    success: bool
    verification_passed: bool
    error: Optional[str] = None
    timestamp: float = 0


@dataclass
class AgentState:
    """
    Complete state of the agent at any point in execution.
    """
    status: AgentStatus = AgentStatus.IDLE
    
    # Task info
    intent: Optional[Intent] = None
    task_steps: List[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    
    # Current perception
    perception: Optional[PerceptionResult] = None
    
    # Action history
    action_history: List[ActionRecord] = field(default_factory=list)
    current_action: Optional[PlannedAction] = None
    
    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    
    # Error tracking
    last_error: Optional[str] = None
    
    @property
    def current_step(self) -> Optional[TaskStep]:
        if 0 <= self.current_step_index < len(self.task_steps):
            return self.task_steps[self.current_step_index]
        return None
    
    @property
    def is_complete(self) -> bool:
        return self.current_step_index >= len(self.task_steps)
    
    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries
    
    def advance_step(self) -> None:
        """Move to next task step."""
        self.current_step_index += 1
        self.retry_count = 0
        
    def record_action(self, action: PlannedAction, success: bool, 
                      verified: bool, error: Optional[str] = None) -> None:
        """Record an action attempt."""
        import time
        self.action_history.append(ActionRecord(
            action=action, success=success, verification_passed=verified,
            error=error, timestamp=time.time()
        ))
    
    def get_recent_actions(self, n: int = 5) -> List[str]:
        """Get descriptions of recent actions."""
        return [f"{r.action.action_type}: {'OK' if r.verification_passed else 'FAIL'}" 
                for r in self.action_history[-n:]]
    
    def reset(self) -> None:
        """Reset state for new task."""
        self.status = AgentStatus.IDLE
        self.intent = None
        self.task_steps = []
        self.current_step_index = 0
        self.perception = None
        self.action_history = []
        self.current_action = None
        self.retry_count = 0
        self.last_error = None
