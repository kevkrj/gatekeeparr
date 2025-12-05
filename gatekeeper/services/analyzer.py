"""
Pluggable AI Content Analyzer

Supports multiple AI providers for content analysis:
- Claude (Anthropic)
- Ollama (local)
- OpenAI (GPT)
- Grok (xAI)

Each provider implements the same interface for consistent behavior.
"""

import json
import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from gatekeeper.config import get_config, AIConfig

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of content analysis"""
    rating: str
    summary: str
    concerns: list[str]
    provider: str
    model: str
    analyzed_at: datetime
    duration_ms: int
    raw_response: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'rating': self.rating,
            'summary': self.summary,
            'concerns': self.concerns,
            'provider': self.provider,
            'model': self.model,
            'analyzed_at': self.analyzed_at.isoformat(),
            'duration_ms': self.duration_ms,
        }


# The analysis prompt - shared across all providers
ANALYSIS_PROMPT = """You are a parental content advisor. Analyze this film/show and provide guidance for parents.

Title: {title}
Year: {year}
Overview: {overview}

Analyze for these parental concerns:
- Language (profanity, slurs, intensity)
- Violence (type, graphic level, who is harmed)
- Sexual Content (nudity, sex scenes, innuendo)
- Scary/Intense Scenes (horror, jump scares, emotional intensity)
- Substances (alcohol, drugs, smoking)
- Mature Themes (death, divorce, discrimination, political themes)

Respond with JSON only (no markdown code blocks):
{{
  "rating": "PG-13",
  "summary": "One sentence summary of overall content level",
  "concerns": [
    "Violence: Brief description",
    "Language: Brief description"
  ]
}}

Rules:
- Only include categories that are actually present/concerning
- Keep each concern to one short line
- For movies use: G, PG, PG-13, R, NC-17
- For TV use: TV-Y, TV-Y7, TV-G, TV-PG, TV-14, TV-MA
- Be conservative - if unsure, rate higher
- If content is clearly adult/pornographic, use NC-17 or X"""


def extract_json(text: str) -> str:
    """Extract JSON from response, handling markdown code blocks"""
    # Try to find JSON in code blocks first
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        return code_block.group(1)
    # Fall back to finding raw JSON
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json_match.group(0)
    return text


class ContentAnalyzer(ABC):
    """Abstract base class for AI content analyzers"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'claude', 'ollama')"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model being used"""
        pass

    @abstractmethod
    def analyze(self, title: str, overview: str, year: Optional[int] = None) -> AnalysisResult:
        """
        Analyze content and return rating information.

        Args:
            title: Media title
            overview: Media description/synopsis
            year: Release year (optional)

        Returns:
            AnalysisResult with rating, summary, and concerns
        """
        pass

    def _build_prompt(self, title: str, overview: str, year: Optional[int]) -> str:
        """Build the analysis prompt"""
        return ANALYSIS_PROMPT.format(
            title=title,
            year=year or "Unknown",
            overview=overview or "No description available"
        )

    def _parse_response(self, response_text: str, start_time: datetime) -> AnalysisResult:
        """Parse AI response into AnalysisResult"""
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        try:
            json_str = extract_json(response_text)
            data = json.loads(json_str)

            return AnalysisResult(
                rating=data.get('rating', 'UNKNOWN'),
                summary=data.get('summary', 'No summary provided'),
                concerns=data.get('concerns', []),
                provider=self.provider_name,
                model=self.model_name,
                analyzed_at=datetime.utcnow(),
                duration_ms=duration_ms,
                raw_response=response_text,
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse AI response: {e}")
            return AnalysisResult(
                rating='UNKNOWN',
                summary=f'Failed to parse response: {str(e)}',
                concerns=['Analysis failed - held for manual review'],
                provider=self.provider_name,
                model=self.model_name,
                analyzed_at=datetime.utcnow(),
                duration_ms=duration_ms,
                raw_response=response_text,
                error=str(e),
            )


class ClaudeAnalyzer(ContentAnalyzer):
    """Anthropic Claude analyzer"""

    def __init__(self, api_key: str, model: Optional[str] = None):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)
        self._model = model or "claude-sonnet-4-20250514"

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def model_name(self) -> str:
        return self._model

    def analyze(self, title: str, overview: str, year: Optional[int] = None) -> AnalysisResult:
        start_time = datetime.utcnow()
        prompt = self._build_prompt(title, overview, year)

        try:
            message = self.client.messages.create(
                model=self._model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = message.content[0].text
            logger.info(f"Claude response for {title}: {response_text[:200]}")
            return self._parse_response(response_text, start_time)

        except Exception as e:
            logger.error(f"Claude API error for {title}: {e}")
            return AnalysisResult(
                rating='UNKNOWN',
                summary=f'API error: {str(e)}',
                concerns=['Analysis failed - held for manual review'],
                provider=self.provider_name,
                model=self.model_name,
                analyzed_at=datetime.utcnow(),
                duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                error=str(e),
            )


class OllamaAnalyzer(ContentAnalyzer):
    """Ollama local LLM analyzer"""

    def __init__(self, base_url: str = "http://localhost:11434", model: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self._model = model or "llama3.2"

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def analyze(self, title: str, overview: str, year: Optional[int] = None) -> AnalysisResult:
        import requests

        start_time = datetime.utcnow()
        prompt = self._build_prompt(title, overview, year)

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 600,
                    }
                },
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            response_text = data.get('response', '')
            logger.info(f"Ollama response for {title}: {response_text[:200]}")
            return self._parse_response(response_text, start_time)

        except Exception as e:
            logger.error(f"Ollama API error for {title}: {e}")
            return AnalysisResult(
                rating='UNKNOWN',
                summary=f'API error: {str(e)}',
                concerns=['Analysis failed - held for manual review'],
                provider=self.provider_name,
                model=self.model_name,
                analyzed_at=datetime.utcnow(),
                duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                error=str(e),
            )


class OpenAIAnalyzer(ContentAnalyzer):
    """OpenAI GPT analyzer"""

    def __init__(self, api_key: str, model: Optional[str] = None, base_url: Optional[str] = None):
        from openai import OpenAI
        self._model = model or "gpt-4o-mini"
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    def analyze(self, title: str, overview: str, year: Optional[int] = None) -> AnalysisResult:
        start_time = datetime.utcnow()
        prompt = self._build_prompt(title, overview, year)

        try:
            response = self.client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.3,
            )
            response_text = response.choices[0].message.content
            logger.info(f"OpenAI response for {title}: {response_text[:200]}")
            return self._parse_response(response_text, start_time)

        except Exception as e:
            logger.error(f"OpenAI API error for {title}: {e}")
            return AnalysisResult(
                rating='UNKNOWN',
                summary=f'API error: {str(e)}',
                concerns=['Analysis failed - held for manual review'],
                provider=self.provider_name,
                model=self.model_name,
                analyzed_at=datetime.utcnow(),
                duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                error=str(e),
            )


class GrokAnalyzer(ContentAnalyzer):
    """xAI Grok analyzer (uses OpenAI-compatible API)"""

    def __init__(self, api_key: str, model: Optional[str] = None):
        from openai import OpenAI
        self._model = model or "grok-2-latest"
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )

    @property
    def provider_name(self) -> str:
        return "grok"

    @property
    def model_name(self) -> str:
        return self._model

    def analyze(self, title: str, overview: str, year: Optional[int] = None) -> AnalysisResult:
        start_time = datetime.utcnow()
        prompt = self._build_prompt(title, overview, year)

        try:
            response = self.client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.3,
            )
            response_text = response.choices[0].message.content
            logger.info(f"Grok response for {title}: {response_text[:200]}")
            return self._parse_response(response_text, start_time)

        except Exception as e:
            logger.error(f"Grok API error for {title}: {e}")
            return AnalysisResult(
                rating='UNKNOWN',
                summary=f'API error: {str(e)}',
                concerns=['Analysis failed - held for manual review'],
                provider=self.provider_name,
                model=self.model_name,
                analyzed_at=datetime.utcnow(),
                duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                error=str(e),
            )


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
