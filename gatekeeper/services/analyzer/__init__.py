"""
Pluggable AI Content Analyzer

Supports multiple AI providers for content analysis:
- Claude (Anthropic)
- Ollama (local)
- OpenAI (GPT)
- Grok (xAI)

Each provider implements the same interface for consistent behavior.
"""

import logging
from typing import Optional

from gatekeeper.config import get_config, AIConfig
from .base import ContentAnalyzer, AnalysisResult
from .ollama import OllamaAnalyzer
from .claude import ClaudeAnalyzer
from .openai_grok import OpenAIAnalyzer, GrokAnalyzer

logger = logging.getLogger(__name__)

# Public API
__all__ = [
    'ContentAnalyzer',
    'AnalysisResult',
    'get_analyzer',
    'reset_analyzer',
    'OllamaAnalyzer',
    'ClaudeAnalyzer',
    'OpenAIAnalyzer',
    'GrokAnalyzer',
]

# Global analyzer instance
_analyzer: Optional[ContentAnalyzer] = None


def get_analyzer(config: Optional[AIConfig] = None) -> ContentAnalyzer:
    """
    Get or create the global analyzer instance.

    Args:
        config: AI configuration. If None, uses global config.

    Returns:
        ContentAnalyzer instance based on configured provider
    """
    global _analyzer

    if _analyzer is not None:
        return _analyzer

    if config is None:
        config = get_config().ai

    provider = config.provider.lower()

    if provider == "claude":
        if not config.api_key:
            raise ValueError("ANTHROPIC_API_KEY or AI_API_KEY required for Claude provider")
        _analyzer = ClaudeAnalyzer(api_key=config.api_key, model=config.model)

    elif provider == "ollama":
        base_url = config.base_url or "http://localhost:11434"
        _analyzer = OllamaAnalyzer(base_url=base_url, model=config.model)

    elif provider == "openai":
        if not config.api_key:
            raise ValueError("AI_API_KEY required for OpenAI provider")
        _analyzer = OpenAIAnalyzer(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url
        )

    elif provider == "grok":
        if not config.api_key:
            raise ValueError("AI_API_KEY required for Grok provider")
        _analyzer = GrokAnalyzer(api_key=config.api_key, model=config.model)

    else:
        raise ValueError(f"Unknown AI provider: {provider}. Supported: claude, ollama, openai, grok")

    logger.info(f"Initialized {provider} analyzer with model {_analyzer.model_name}")
    return _analyzer


def reset_analyzer():
    """Reset the global analyzer (useful for testing or config changes)"""
    global _analyzer
    _analyzer = None
