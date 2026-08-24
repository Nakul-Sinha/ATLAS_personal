"""
ATLAS ML Pipeline - Local LLM (Mistral/Phi)
===========================================

Handles reasoning and planning:
- Intent extraction from user prompts
- Task decomposition into steps
- Action planning
- Error recovery decisions
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import json
import re
from loguru import logger

from config import LLMConfig, config


@dataclass
class Intent:
    """Structured intent from user prompt."""
    goal: str
    app: Optional[str]
    entities: Dict[str, Any]
    raw_prompt: str


@dataclass
class TaskStep:
    """Single step in a task plan."""
    step_number: int
    action: str
    description: str
    target: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


@dataclass
class PlannedAction:
    """Single atomic action to execute."""
    action_type: str  # "click", "type", "key", "scroll", "wait"
    target_role: Optional[str] = None
    target_text: Optional[str] = None
    text: Optional[str] = None  # For typing
    key: Optional[str] = None  # For key press
    direction: Optional[str] = None  # For scroll
    confidence: float = 0.0


class LLMModel:
    """
    Local LLM wrapper using llama.cpp.
    
    Handles all reasoning tasks:
    - Intent interpretation
    - Task planning
    - Action selection
    - Error recovery
    
    Usage:
        llm = LLMModel()
        intent = llm.extract_intent("Open notepad and write hello")
        steps = llm.create_task_plan(intent)
        action = llm.plan_action(current_state, next_step)
    """
    
    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self.config = llm_config or config.llm
        self._model = None
        
    def load(self) -> None:
        """
        Initialize the configured LLM backend.

        The default Ollama backend has nothing to load locally: generation talks
        to the Ollama server over HTTP. Only the llama.cpp fallback needs a local
        GGUF model file, so we do not touch llama_cpp (or require the model file)
        unless that backend is selected.
        """
        if self.config.backend == "ollama":
            logger.info(f"LLM backend: ollama ({self.config.ollama_model})")
            return

        try:
            from llama_cpp import Llama

            self._model = Llama(
                model_path=self.config.model_path,
                n_ctx=self.config.n_ctx,
                n_gpu_layers=self.config.n_gpu_layers,
                verbose=False,
            )

            logger.info(f"LLM loaded: {self.config.model_path}")

        except Exception as e:
            logger.error(f"Failed to load LLM: {e}")
            raise
    
    def _generate(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Generate completion from prompt."""
        
        # Check backend
        if self.config.backend == "ollama":
            import requests
            
            logger.debug(f"Ollama Prompt ({self.config.ollama_model}):\n{prompt}")
            
            try:
                response = requests.post(
                    f"{config.ollama.base_url}/api/generate",
                    json={
                        "model": self.config.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.config.temperature,
                            "num_predict": max_tokens or self.config.max_tokens,
                            "stop": ["</s>", "[/INST]", "\n\n\n"]
                        }
                    },
                    timeout=config.ollama.timeout
                )
                response.raise_for_status()
                result = response.json()["response"].strip()
                logger.debug(f"Ollama Output:\n{result}")
                return result
            except Exception as e:
                logger.error(f"Ollama generation failed: {e}")
                return ""
        
        # Fallback to LlamaCpp
        if self._model is None:
            self.load()
            
        logger.debug(f"LlamaCpp Prompt:\n{prompt}")
            
        output = self._model(
            prompt,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=self.config.temperature,
            stop=["</s>", "[/INST]", "\n\n\n"],
        )
        
        result = output["choices"][0]["text"].strip()
        logger.debug(f"LlamaCpp Output:\n{result}")
        return result
    
    def extract_intent(self, user_prompt: str) -> Intent:
        """
        Extract structured intent from user's natural language prompt.
        
        PIPELINE STEP 1
        """
        prompt = f"""[INST] You are an intent extraction system. Extract the user's intent from their request.

User request: "{user_prompt}"

Respond with JSON only:
{{
    "goal": "main action in snake_case",
    "app": "target application name or null",
    "entities": {{
        "key": "extracted value"
    }}
}}

Extract WHAT the user wants, not HOW to do it. [/INST]
"""

        try:
            response = self._generate(prompt)
            data = self._parse_json(response)
            
            return Intent(
                goal=data.get("goal", "unknown"),
                app=data.get("app"),
                entities=data.get("entities", {}),
                raw_prompt=user_prompt
            )
        except Exception as e:
            logger.error(f"Intent extraction failed: {e}")
            return Intent(
                goal="unknown",
                app=None,
                entities={},
                raw_prompt=user_prompt
            )
    
    def create_task_plan(self, intent: Intent) -> List[TaskStep]:
        """
        Convert intent into high-level task steps.
        
        PIPELINE STEP 2
        """
        prompt = f"""[INST] You are a task planning system for a Windows desktop agent. Create a step-by-step plan for this task.

Intent:
- Goal: {intent.goal}
- App: {intent.app or "unspecified"}
- Details: {json.dumps(intent.entities)}

IMPORTANT RULES:
- To open any application, ALWAYS use Windows Search: press "win+s", type the app name, then press "enter". Do NOT click taskbar icons.
- Keep steps atomic and verifiable.
- Create abstract steps (no coordinates, no UI specifics).

Respond with JSON array only:
[
    {{"step": 1, "action": "verb phrase", "description": "what to do", "target": "element name or null"}},
    ...
]

[/INST]
"""

        try:
            response = self._generate(prompt)
            data = self._parse_json(response)
            
            steps = []
            for item in data:
                steps.append(TaskStep(
                    step_number=item.get("step", len(steps) + 1),
                    action=item.get("action", ""),
                    description=item.get("description", ""),
                    target=item.get("target"),
                    parameters=item.get("parameters")
                ))
            
            return steps
            
        except Exception as e:
            logger.error(f"Task planning failed: {e}")
            return []
    
    def _try_deterministic_action(self, step: TaskStep) -> Optional[PlannedAction]:
        """
        Try to determine the action deterministically from the step description.
        
        Returns a PlannedAction if the step clearly maps to a key press or type action,
        otherwise returns None to fall through to LLM-based planning.
        """
        desc = (step.action + " " + step.description).lower()
        
        # --- Key press patterns ---
        # Match "press <combo>" greedily, then try to normalize the captured key.
        # We try multiple extraction strategies from most specific to least.
        
        # First: look for explicit key combos with + sign  e.g. "press windows key + s"
        m = re.search(r'(?:press|hit)\s+(.+?\+\s*\S+)', desc)
        if m:
            raw_key = m.group(1).strip().rstrip('.')
            key = self._normalize_key(raw_key)
            if key:
                return PlannedAction(action_type="key", key=key, confidence=0.95)
        
        # Second: "press <known_key_word>" — match known single keys
        m = re.search(r'(?:press|hit)\s+(?:the\s+)?(\S+)', desc)
        if m:
            raw_key = m.group(1).strip().rstrip('.')
            key = self._normalize_key(raw_key)
            if key:
                return PlannedAction(action_type="key", key=key, confidence=0.95)
        
        # --- Type patterns ---
        # "type 'notepad'", "type \"hello world\"", "type notepad in search"
        type_patterns = [
            r"""type\s+['"](.+?)['"]""",          # type 'notepad' or type "notepad"
            r"type\s+(\S+)\s+in\s+",              # type notepad in search
        ]
        
        for pattern in type_patterns:
            m = re.search(pattern, desc)
            if m:
                text = m.group(1).strip()
                if text:
                    return PlannedAction(action_type="type", text=text, confidence=0.95)
        
        return None
    
    @staticmethod
    def _normalize_key(raw: str) -> Optional[str]:
        """Normalize a raw key description to a pyautogui-compatible key string."""
        raw = raw.lower().strip()
        
        # Common key combo normalizations
        replacements = {
            "windows key + s": "win+s",
            "windows key+s": "win+s",
            "win key + s": "win+s",
            "windows + s": "win+s",
            "win + s": "win+s",
            "windows key": "win",
            "win key": "win",
            "enter key": "enter",
            "enter": "enter",
            "return": "enter",
            "escape": "esc",
            "esc": "esc",
            "tab": "tab",
            "space": "space",
            "backspace": "backspace",
            "delete": "delete",
            "ctrl+c": "ctrl+c",
            "ctrl+v": "ctrl+v",
            "ctrl+a": "ctrl+a",
            "ctrl+s": "ctrl+s",
            "ctrl+z": "ctrl+z",
            "alt+f4": "alt+f4",
            "alt+tab": "alt+tab",
        }
        
        # Direct match
        if raw in replacements:
            return replacements[raw]
        
        # Try normalizing separators: "ctrl + c" -> "ctrl+c"
        normalized = re.sub(r'\s*\+\s*', '+', raw)
        if normalized in replacements:
            return replacements[normalized]
        
        # If it looks like a key combo (contains +), return as-is
        if '+' in normalized and len(normalized) < 20:
            return normalized
        
        # Single word keys
        if len(raw.split()) == 1 and len(raw) < 15:
            return raw
        
        return None
    
    def plan_action(
        self, 
        screen_description: str,
        available_elements: List[Dict[str, Any]],
        current_step: TaskStep,
        history: Optional[List[str]] = None
    ) -> PlannedAction:
        """
        Decide the next atomic action based on screen state.
        
        PIPELINE STEP 7
        """
        # --- Deterministic override for key/type steps ---
        # The LLM often ignores instructions to use "key" actions, so we detect
        # common patterns in the step description and return the action directly.
        override = self._try_deterministic_action(current_step)
        if override:
            logger.info(f"Deterministic action override: {override.action_type} (key={override.key}, text={override.text})")
            return override
        
        # --- LLM-based planning for click/scroll/complex actions ---
        # Limit elements to top 30 by confidence to avoid prompt bloat
        top_elements = sorted(available_elements, key=lambda e: e.get("confidence", 0), reverse=True)[:30]
        elements_str = json.dumps(top_elements, indent=2)
        history_str = "\n".join(history) if history else "None"
        
        prompt = f"""[INST] You are an action planning system for a Windows desktop agent. Decide ONE atomic action.

Current task step: {current_step.action} - {current_step.description}

Screen state: {screen_description}

Top UI elements on screen:
{elements_str}

Previous actions: {history_str}

CRITICAL RULES:
- If the step says "press" a key or key combo (e.g. "Win+S", "Enter", "Ctrl+C"), use action_type "key" with the key field. Example: {{"action_type":"key","key":"win+s"}}
- If the step says "type" text, use action_type "type" with the text field. Example: {{"action_type":"type","text":"notepad"}}
- Only use action_type "click" if you need to click a SPECIFIC element that EXISTS in the UI elements list above. NEVER invent element names.
- For target_text, use EXACT text from the elements list. Do not guess or hallucinate text.

Respond with JSON only:
{{
    "action_type": "click|type|key|scroll|wait",
    "target_role": "role from elements list or null",
    "target_text": "exact text from elements list or null",
    "text": "text to type or null",
    "key": "key combo to press or null",
    "direction": "up|down|left|right or null",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}

[/INST]
"""

        try:
            response = self._generate(prompt)
            data = self._parse_json(response)
            
            return PlannedAction(
                action_type=data.get("action_type", "wait"),
                target_role=data.get("target_role"),
                target_text=data.get("target_text"),
                text=data.get("text"),
                key=data.get("key"),
                direction=data.get("direction"),
                confidence=data.get("confidence", 0.5)
            )
            
        except Exception as e:
            logger.error(f"Action planning failed: {e}")
            return PlannedAction(action_type="wait", confidence=0.0)
    
    def handle_error(
        self,
        error_description: str,
        screen_state: str,
        last_action: PlannedAction,
        retry_count: int
    ) -> Dict[str, Any]:
        """
        Decide how to handle an error/failed verification.
        
        Returns recovery strategy.
        """
        prompt = f"""[INST] You are an error recovery system. Decide how to recover from this failure.

Error: {error_description}
Last action attempted: {last_action.action_type} on {last_action.target_role or last_action.target_text}
Current screen: {screen_state}
Retry count: {retry_count}

Choose a recovery strategy. Respond with JSON only:
{{
    "strategy": "retry|replan|skip|abort",
    "reason": "explanation",
    "modification": "what to change if retrying"
}}

[/INST]
"""

        try:
            response = self._generate(prompt)
            return self._parse_json(response)
        except Exception as e:
            logger.error(f"Error handling failed: {e}")
            return {"strategy": "abort", "reason": str(e)}
    
    def rank_candidates(
        self,
        candidates: List[Dict[str, Any]],
        target_description: str
    ) -> List[Dict[str, Any]]:
        """
        Rank UI element candidates by relevance to target.
        
        Used in PIPELINE STEP 6 for bounding box fusion.
        """
        prompt = f"""[INST] Rank these UI elements by how well they match: "{target_description}"

Candidates:
{json.dumps(candidates, indent=2)}

Respond with JSON array of indices sorted by relevance (most relevant first):
{{"ranking": [index1, index2, ...], "scores": [score1, score2, ...]}}

Scores should be 0-1. [/INST]
"""

        try:
            response = self._generate(prompt)
            data = self._parse_json(response)
            
            ranking = data.get("ranking", list(range(len(candidates))))
            scores = data.get("scores", [0.5] * len(candidates))
            
            # Reorder candidates
            ranked = []
            for idx, score in zip(ranking, scores):
                if idx < len(candidates):
                    candidate = candidates[idx].copy()
                    candidate["relevance_score"] = score
                    ranked.append(candidate)
                    
            return ranked
            
        except Exception as e:
            logger.error(f"Candidate ranking failed: {e}")
            return candidates
    
    def _parse_json(self, text: str) -> Any:
        """Extract and parse JSON from LLM response."""
        import json
        import re
        
        # 1. Try to find a code block first (common in newer models)
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if code_block:
            text = code_block.group(1)
            
        # 2. Find first opening bracket
        start_brace = text.find('{')
        start_bracket = text.find('[')
        
        if start_brace == -1 and start_bracket == -1:
             logger.warning(f"No JSON brackets found in response: {text[:50]}...")
             return {}
             
        # Determine which comes first
        if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
            start = start_brace
            opener, closer = '{', '}'
        else:
            start = start_bracket
            opener, closer = '[', ']'
            
        # 3. Find matching closing bracket
        count = 0
        for i, char in enumerate(text[start:], start=start):
            if char == opener:
                count += 1
            elif char == closer:
                count -= 1
                if count == 0:
                    json_str = text[start:i+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.error(f"Extracted JSON invalid error: {e}")
                        return {}
        
        logger.warning("Unmatched brackets in JSON response")
        return {}
