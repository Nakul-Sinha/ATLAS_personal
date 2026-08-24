"""
ATLAS ML Pipeline - Model Loaders
=================================

This module handles loading and initializing all ML models:
- EasyOCR for text detection
- LLaVA (via Ollama) for visual understanding
- Llama 3.2 (via Ollama), with a llama.cpp fallback, for reasoning and planning
"""

from .ocr_model import OCRModel
from .vlm_model import VLMModel
from .llm_model import LLMModel

__all__ = ["OCRModel", "VLMModel", "LLMModel"]
