"""
ATLAS MCP Agent - Modular LLM Backend
======================================

Provides a unified interface for LLM calls with three backends:
  1. Google Gemini API (native SDK - primary)
  2. OpenAI-compatible API (works with OpenAI, Groq, Together, Ollama, etc.)
  3. Local llama-cpp-python (fully offline)

Usage:
    from llm_backend import create_llm
    llm = create_llm(config)
    response = llm.chat([{"role": "user", "content": "Hello"}])
"""

from __future__ import annotations
import json
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from rich.console import Console

from config import MCPConfig, GeminiConfig, OpenAIConfig, LlamaConfig

console = Console()


class LLMBackend(ABC):
    """Abstract LLM interface - swap backends without changing agent code."""
    
    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request.
        
        Returns dict with:
            - role: "assistant"
            - content: str or None
            - tool_calls: list of tool call dicts (if tools were provided)
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name."""
        ...


# ─── Gemini Backend (Native SDK) ──────────────────────────────────────────────

class GeminiBackend(LLMBackend):
    """Google Gemini API backend using the native google-genai SDK."""
    
    def __init__(self, cfg: GeminiConfig):
        self.cfg = cfg
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError:
                raise RuntimeError(
                    "google-genai is not installed.\n"
                    "Install it with: pip install google-genai"
                )
            self._client = genai.Client(api_key=self.cfg.api_key)
        return self._client
    
    def _openai_tools_to_gemini_declarations(
        self, tools: List[Dict[str, Any]]
    ) -> list:
        """Convert OpenAI-format tool schemas to Gemini function declarations."""
        from google.genai import types
        
        declarations = []
        for tool in tools:
            fn = tool["function"]
            params = fn.get("parameters", {})
            
            # Clean up schema for Gemini - it's stricter about JSON Schema
            clean_params = self._clean_schema_for_gemini(params)
            
            declarations.append(types.FunctionDeclaration(
                name=fn["name"],
                description=fn.get("description", ""),
                parameters=clean_params if clean_params.get("properties") else None,
            ))
        return declarations
    
    def _clean_schema_for_gemini(self, schema: dict) -> dict:
        """Clean a JSON Schema dict to be Gemini-compatible."""
        cleaned = {}
        if "type" in schema:
            cleaned["type"] = schema["type"].upper() if schema["type"] in ("string", "number", "integer", "boolean", "array", "object") else schema["type"]
        if "properties" in schema:
            cleaned["properties"] = {}
            for k, v in schema["properties"].items():
                cleaned["properties"][k] = self._clean_schema_for_gemini(v)
        if "required" in schema:
            cleaned["required"] = schema["required"]
        if "description" in schema:
            cleaned["description"] = schema["description"]
        if "items" in schema:
            cleaned["items"] = self._clean_schema_for_gemini(schema["items"])
        if "enum" in schema:
            cleaned["enum"] = schema["enum"]
        return cleaned
    
    def _build_contents(self, messages: List[Dict[str, Any]]) -> tuple:
        """Convert OpenAI-style messages to Gemini contents + system instruction."""
        from google.genai import types
        
        system_instruction = None
        contents = []
        
        for msg in messages:
            role = msg["role"]
            
            if role == "system":
                system_instruction = msg["content"]
                continue
            
            if role == "assistant":
                parts = []
                if msg.get("content"):
                    parts.append(types.Part.from_text(text=msg["content"]))
                # Re-create function call parts for history
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        fn = tc["function"]
                        args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                        parts.append(types.Part.from_function_call(
                            name=fn["name"],
                            args=args,
                        ))
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
                continue
            
            if role == "tool":
                # Gemini expects function responses as "user" role content
                tool_call_id = msg.get("tool_call_id", "")
                # Find the function name from the previous assistant message
                fn_name = self._find_fn_name_for_tool_call(messages, tool_call_id)
                try:
                    result_data = json.loads(msg["content"])
                except (json.JSONDecodeError, TypeError):
                    result_data = {"result": msg.get("content", "")}
                
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=fn_name,
                        response=result_data,
                    )],
                ))
                continue
            
            if role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=msg.get("content", ""))],
                ))
                continue
        
        return contents, system_instruction
    
    def _find_fn_name_for_tool_call(
        self, messages: List[Dict[str, Any]], tool_call_id: str
    ) -> str:
        """Look back through messages to find the function name for a tool_call_id."""
        for msg in reversed(messages):
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if tc.get("id") == tool_call_id:
                        return tc["function"]["name"]
        return "unknown_function"
    
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        import time
        import re as _re
        from google.genai import types
        
        client = self._get_client()
        contents, system_instruction = self._build_contents(messages)
        
        # Build config
        gen_config = types.GenerateContentConfig(
            temperature=temperature or self.cfg.temperature,
            max_output_tokens=self.cfg.max_output_tokens,
        )
        if system_instruction:
            gen_config.system_instruction = system_instruction
        
        # Add tools if provided
        if tools:
            declarations = self._openai_tools_to_gemini_declarations(tools)
            gen_config.tools = [types.Tool(function_declarations=declarations)]
        
        # Retry with exponential backoff for rate limits
        max_retries = 5
        response = None
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=self.cfg.model,
                    contents=contents,
                    config=gen_config,
                )
                break  # Success
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    # quota=0 means the free tier is disabled entirely - retrying is pointless
                    if "limit: 0" in err_str:
                        raise RuntimeError(
                            "\n[!] Gemini free tier quota is 0 for your GCP project.\n"
                            "This is NOT a transient rate limit - retrying won't help.\n\n"
                            "Fix options:\n"
                            "  1. Enable billing on your GCP project at console.cloud.google.com\n"
                            "     (even $0 billing unlocks the free tier quota)\n\n"
                            "  2. Use OpenRouter instead (free credits, no billing needed):\n"
                            "     Set in .env:\n"
                            "       LLM_BACKEND=openai\n"
                            "       OPENAI_BASE_URL=https://openrouter.ai/api/v1\n"
                            "       OPENAI_API_KEY=<key from openrouter.ai/keys>\n"
                            "       OPENAI_MODEL=google/gemini-2.0-flash-exp:free\n"
                        ) from e
                    
                    # Transient rate limit - extract server-suggested delay and retry
                    delay_match = _re.search(r'retry\w* in ([\d.]+)', err_str, _re.IGNORECASE)
                    wait = float(delay_match.group(1)) + 2 if delay_match else min(15 * (2 ** attempt), 120)
                    
                    if attempt < max_retries - 1:
                        console.print(
                            f"  [yellow]⏳ Rate limited (attempt {attempt + 1}/{max_retries}), "
                            f"waiting {wait:.0f}s...[/yellow]"
                        )
                        time.sleep(wait)
                    else:
                        raise
                else:
                    raise  # Non-rate-limit error, don't retry
        
        # Parse response
        result = {
            "role": "assistant",
            "content": None,
            "tool_calls": None,
        }
        
        if not response.candidates:
            result["content"] = "No response generated."
            return result
        
        candidate = response.candidates[0]
        text_parts = []
        tool_calls = []
        
        for part in candidate.content.parts:
            if part.text:
                text_parts.append(part.text)
            elif part.function_call:
                fc = part.function_call
                tool_calls.append({
                    "id": f"gemini_{uuid.uuid4().hex[:8]}",
                    "function": {
                        "name": fc.name,
                        "arguments": json.dumps(dict(fc.args) if fc.args else {}),
                    },
                })
        
        if text_parts:
            result["content"] = "\n".join(text_parts)
        
        if tool_calls:
            result["tool_calls"] = tool_calls
        
        return result
    
    def name(self) -> str:
        return f"Gemini ({self.cfg.model})"


class OpenAIBackend(LLMBackend):
    """OpenAI-compatible API backend (works with any OpenAI-shaped endpoint)."""
    
    def __init__(self, cfg: OpenAIConfig):
        self.cfg = cfg
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = {"api_key": self.cfg.api_key}
            if self.cfg.base_url:
                kwargs["base_url"] = self.cfg.base_url
            self._client = OpenAI(**kwargs)
        return self._client
    
    def _is_gemini_model(self) -> bool:
        """Check if the configured model is a Gemini model (via OpenRouter or similar)."""
        model_lower = self.cfg.model.lower()
        return "gemini" in model_lower or "google" in model_lower
    
    def _sanitize_messages_for_gemini(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert tool-call message sequences into plain-text messages
        that Gemini can understand via OpenRouter.
        
        Gemini behind OpenRouter does not reliably support the OpenAI
        tool_calls/tool message format. Instead, we convert:
          - assistant msg with tool_calls → assistant text describing the call
          - tool result msg → user text with the result
        """
        clean = []
        for msg in messages:
            role = msg.get("role")
            
            if role == "assistant" and msg.get("tool_calls"):
                # Convert tool calls to a plain text description
                parts = []
                if msg.get("content"):
                    parts.append(msg["content"])
                for tc in msg["tool_calls"]:
                    fn = tc["function"]
                    parts.append(f"I'll call tool: {fn['name']}({fn['arguments']})")
                clean.append({"role": "assistant", "content": "\n".join(parts)})
            
            elif role == "tool":
                # Convert tool result into a user message
                tool_id = msg.get("tool_call_id", "")
                # Find the function name from previous assistant messages
                fn_name = "tool"
                for prev in reversed(clean):
                    if prev["role"] == "assistant" and "I'll call tool:" in prev.get("content", ""):
                        import re
                        match = re.search(r"I'll call tool: (\w+)", prev["content"])
                        if match:
                            fn_name = match.group(1)
                        break
                content = msg.get("content") or "(no output)"
                clean.append({
                    "role": "user",
                    "content": f"[Tool result from {fn_name}]:\n{content}",
                })
            
            else:
                # Pass through system, user, and normal assistant messages
                m = dict(msg)
                if role == "assistant" and m.get("content") is None:
                    m["content"] = ""
                clean.append(m)
        
        return clean
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        client = self._get_client()
        
        # Gemini via OpenRouter doesn't support OpenAI tool message format reliably.
        # For Gemini models: convert tool interactions to plain text messages.
        # For true OpenAI models: pass through with native tool support.
        use_native_tools = not self._is_gemini_model()
        
        if use_native_tools:
            clean_messages = messages
        else:
            clean_messages = self._sanitize_messages_for_gemini(messages)
        
        kwargs = {
            "model": self.cfg.model,
            "messages": clean_messages,
            "temperature": temperature or self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        response = client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        
        result = {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": None,
        }
        
        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        
        return result
    
    def name(self) -> str:
        base = self.cfg.base_url or "api.openai.com"
        return f"OpenAI ({self.cfg.model} @ {base})"


class LlamaBackend(LLMBackend):
    """Local llama-cpp-python backend for fully offline use."""
    
    def __init__(self, cfg: LlamaConfig):
        self.cfg = cfg
        self._model = None
    
    def _get_model(self):
        if self._model is None:
            try:
                from llama_cpp import Llama
            except ImportError:
                raise RuntimeError(
                    "llama-cpp-python is not installed. "
                    "Install it with: pip install llama-cpp-python"
                )
            console.print(f"[dim]Loading local model: {self.cfg.model_path}[/dim]")
            self._model = Llama(
                model_path=self.cfg.model_path,
                n_ctx=self.cfg.n_ctx,
                n_gpu_layers=self.cfg.n_gpu_layers,
                verbose=False,
                chat_format="chatml",  # Works with most instruct models
            )
            console.print("[green]✓ Local model loaded[/green]")
        return self._model
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        model = self._get_model()
        
        # If tools are provided, inject them into the system prompt
        # since llama.cpp chat doesn't natively support tool_choice
        if tools:
            messages = self._inject_tools_into_prompt(messages, tools)
        
        response = model.create_chat_completion(
            messages=messages,
            temperature=temperature or self.cfg.temperature,
            max_tokens=self.cfg.max_tokens,
        )
        
        msg = response["choices"][0]["message"]
        
        result = {
            "role": "assistant",
            "content": msg.get("content", ""),
            "tool_calls": None,
        }
        
        # Try to parse tool calls from the response text
        if tools and result["content"]:
            parsed = self._try_parse_tool_call(result["content"])
            if parsed:
                result["tool_calls"] = [parsed]
                result["content"] = None
        
        return result
    
    def _inject_tools_into_prompt(
        self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """Add tool descriptions to the system prompt for models without native tool support."""
        tool_desc = "You have access to these tools. To call a tool, respond with EXACTLY this JSON format and nothing else:\n"
        tool_desc += '{"tool": "<tool_name>", "arguments": {<args>}}\n\n'
        tool_desc += "Available tools:\n"
        for t in tools:
            fn = t["function"]
            tool_desc += f"\n### {fn['name']}\n{fn.get('description', '')}\n"
            if "parameters" in fn:
                props = fn["parameters"].get("properties", {})
                required = fn["parameters"].get("required", [])
                for pname, pinfo in props.items():
                    req_mark = " (REQUIRED)" if pname in required else ""
                    tool_desc += f"  - {pname}: {pinfo.get('description', pinfo.get('type', 'any'))}{req_mark}\n"
        
        # Prepend to system message or create one
        messages = list(messages)  # copy
        if messages and messages[0]["role"] == "system":
            messages[0] = {
                "role": "system",
                "content": messages[0]["content"] + "\n\n" + tool_desc,
            }
        else:
            messages.insert(0, {"role": "system", "content": tool_desc})
        
        return messages
    
    def _try_parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Try to extract a tool call JSON from the model's text output."""
        import re
        # Look for JSON blocks
        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{[^{}]*"tool"[^{}]*\})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if "tool" in data:
                        return {
                            "id": "local_call_0",
                            "function": {
                                "name": data["tool"],
                                "arguments": json.dumps(data.get("arguments", {})),
                            },
                        }
                except json.JSONDecodeError:
                    continue
        return None
    
    def name(self) -> str:
        return f"Llama.cpp ({self.cfg.model_path})"


def create_llm(config: MCPConfig) -> LLMBackend:
    """Factory: create the right LLM backend based on config."""
    if config.llm_backend == "gemini":
        if not config.gemini.api_key:
            raise ValueError(
                "LLM_BACKEND=gemini but GEMINI_API_KEY is not set.\n"
                "Set GEMINI_API_KEY in ml/mcp/.env (copy it from ml/mcp/.env.example)\n"
                "or export it as an environment variable."
            )
        return GeminiBackend(config.gemini)
    elif config.llm_backend == "openai":
        if not config.openai.api_key:
            raise ValueError(
                "LLM_BACKEND=openai but OPENAI_API_KEY is not set.\n"
                "Set OPENAI_API_KEY in ml/mcp/.env (copy it from ml/mcp/.env.example)\n"
                "or export it as an environment variable. For OpenRouter also set\n"
                "OPENAI_BASE_URL=https://openrouter.ai/api/v1 and an OPENAI_MODEL."
            )
        return OpenAIBackend(config.openai)
    elif config.llm_backend == "llama":
        return LlamaBackend(config.llama)
    else:
        raise ValueError(f"Unknown LLM backend: {config.llm_backend}")
