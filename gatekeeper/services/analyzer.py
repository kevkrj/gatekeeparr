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
    recommended_age: Optional[str] = None  # e.g. "12+", "15+" from CSM
    raw_response: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        result = {
            'rating': self.rating,
            'summary': self.summary,
            'concerns': self.concerns,
            'provider': self.provider,
            'model': self.model,
            'analyzed_at': self.analyzed_at.isoformat(),
            'duration_ms': self.duration_ms,
        }
        if self.recommended_age:
            result['recommended_age'] = self.recommended_age
        return result


# Content summary prompt - used when we already have the official rating from TMDB
# AI focuses on describing actual content concerns for parents
CONTENT_PROMPT = """You are a parental content advisor helping parents decide if a {media_type} is appropriate for their child.

Title: {title} ({year})
Official Rating: {rating}
Overview: {overview}
{content_data}
Write a brief parental guide. Focus on WHY a parent might hesitate, not just WHAT happens.

Respond with JSON only:
{{
  "age": "12+",
  "summary": "Brief description of core parental concern",
  "concerns": [
    "Violence: [specific type] - [why it matters]",
    "Themes: [topic] - [why parents should know]"
  ]
}}

Rules:
- Summary: ONE sentence, the main reason this got its rating
- Max 3 concerns, only what's truly notable for THIS movie
- Each concern: specific content + why it matters (one sentence each)
- Use the content data above - it has accurate details
- NO filler or generic statements
- Skip mild content that's typical for the rating"""

# Fallback prompt - used when no official rating is available (rare)
# AI must estimate rating based on content
RATING_PROMPT = """You are a parental content advisor. Analyze this film/show and provide guidance for parents.

Title: {title}
Year: {year}
Overview: {overview}

No official rating is available. Analyze for these parental concerns:
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

# Legacy prompt alias for backwards compatibility
ANALYSIS_PROMPT = RATING_PROMPT


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
        Used as fallback when no official rating is available.

        Args:
            title: Media title
            overview: Media description/synopsis
            year: Release year (optional)

        Returns:
            AnalysisResult with rating, summary, and concerns
        """
        pass

    @abstractmethod
    def summarize_content(
        self,
        title: str,
        overview: str,
        rating: str,
        media_type: str = "movie",
        year: Optional[int] = None,
        content_data: Optional[str] = None
    ) -> AnalysisResult:
        """
        Summarize content concerns for parents when rating is already known.
        This is the primary method - AI describes content, doesn't guess rating.

        Args:
            title: Media title
            overview: Media description/synopsis
            rating: Official rating from TMDB (e.g., "PG-13", "R", "TV-MA")
            media_type: "movie" or "tv"
            year: Release year (optional)
            content_data: Pre-fetched content info from Common Sense Media etc.

        Returns:
            AnalysisResult with summary and concerns (rating passed through)
        """
        pass

    def _build_prompt(self, title: str, overview: str, year: Optional[int]) -> str:
        """Build the rating analysis prompt (fallback)"""
        return RATING_PROMPT.format(
            title=title,
            year=year or "Unknown",
            overview=overview or "No description available"
        )

    def _build_content_prompt(
        self,
        title: str,
        overview: str,
        rating: str,
        media_type: str,
        year: Optional[int],
        content_data: Optional[str] = None
    ) -> str:
        """Build the content summary prompt (primary)"""
        # Format content data section
        if content_data:
            content_section = f"\n{content_data}\n"
        else:
            content_section = ""

        return CONTENT_PROMPT.format(
            title=title,
            year=year or "Unknown",
            rating=rating,
            media_type=media_type,
            overview=overview or "No description available",
            content_data=content_section
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

    def _parse_content_response(
        self,
        response_text: str,
        rating: str,
        start_time: datetime
    ) -> AnalysisResult:
        """Parse content-only AI response (when rating is known)"""
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        try:
            json_str = extract_json(response_text)
            data = json.loads(json_str)

            # Normalize concerns - small models sometimes return dicts instead of strings
            raw_concerns = data.get('concerns', [])
            concerns = []
            for c in raw_concerns:
                if isinstance(c, str):
                    concerns.append(c)
                elif isinstance(c, dict):
                    # Convert dict to string: "content - why it matters"
                    content = c.get('content', c.get('type', ''))
                    why = c.get('why it matters', c.get('why', c.get('reason', '')))
                    if content and why:
                        concerns.append(f"{content} - {why}")
                    elif content:
                        concerns.append(content)

            return AnalysisResult(
                rating=rating,  # Use the official rating, not AI guess
                summary=data.get('summary', 'No summary provided'),
                concerns=concerns,
                provider=self.provider_name,
                model=self.model_name,
                analyzed_at=datetime.utcnow(),
                duration_ms=duration_ms,
                recommended_age=data.get('age'),  # CSM-style age like "12+"
                raw_response=response_text,
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse AI content response: {e}")
            return AnalysisResult(
                rating=rating,
                summary=f'Failed to parse response: {str(e)}',
                concerns=['Content analysis failed - held for manual review'],
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

    def _call_claude(self, prompt: str, title: str) -> str:
        """Make API call to Claude and return response text"""
        message = self.client.messages.create(
            model=self._model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text
        logger.info(f"Claude response for {title}: {response_text[:200]}")
        return response_text

    def analyze(self, title: str, overview: str, year: Optional[int] = None) -> AnalysisResult:
        start_time = datetime.utcnow()
        prompt = self._build_prompt(title, overview, year)

        try:
            response_text = self._call_claude(prompt, title)
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

    def summarize_content(
        self,
        title: str,
        overview: str,
        rating: str,
        media_type: str = "movie",
        year: Optional[int] = None,
        content_data: Optional[str] = None
    ) -> AnalysisResult:
        """Primary: describe content concerns when official rating is known"""
        start_time = datetime.utcnow()
        prompt = self._build_content_prompt(title, overview, rating, media_type, year, content_data)

        try:
            response_text = self._call_claude(prompt, title)
            return self._parse_content_response(response_text, rating, start_time)

        except Exception as e:
            logger.error(f"Claude content summary error for {title}: {e}")
            return AnalysisResult(
                rating=rating,
                summary=f'API error: {str(e)}',
                concerns=['Content analysis failed - held for manual review'],
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

    def _call_ollama(self, prompt: str, title: str) -> str:
        """Make API call to Ollama and return response text"""
        import requests

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
        return response_text

    def analyze(self, title: str, overview: str, year: Optional[int] = None) -> AnalysisResult:
        """Fallback: analyze content and estimate rating when no official rating available"""
        start_time = datetime.utcnow()
        prompt = self._build_prompt(title, overview, year)

        try:
            response_text = self._call_ollama(prompt, title)
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

    def summarize_content(
        self,
        title: str,
        overview: str,
        rating: str,
        media_type: str = "movie",
        year: Optional[int] = None,
        content_data: Optional[str] = None
    ) -> AnalysisResult:
        """Primary: describe content concerns when official rating is known"""
        start_time = datetime.utcnow()
        prompt = self._build_content_prompt(title, overview, rating, media_type, year, content_data)

        # Retry up to 3 total attempts for JSON parsing failures (small models can be inconsistent)
        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                response_text = self._call_ollama(prompt, title)
                result = self._parse_content_response(response_text, rating, start_time)

                # If parsing succeeded (no error), return the result
                if not result.error:
                    return result

                # If this was a JSON parse error, retry
                last_error = result.error
                if attempt < max_attempts - 1:
                    logger.warning(f"Ollama JSON parse failed for {title}, retrying ({attempt + 1}/{max_attempts})")
                    continue
                else:
                    return result

            except Exception as e:
                logger.error(f"Ollama content summary error for {title}: {e}")
                last_error = str(e)
                if attempt < max_attempts - 1:
                    continue

        return AnalysisResult(
            rating=rating,
            summary=f'API error after {max_attempts} attempts: {last_error}',
            concerns=['Content analysis failed - held for manual review'],
            provider=self.provider_name,
            model=self.model_name,
            analyzed_at=datetime.utcnow(),
            duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
            error=last_error,
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

    def _call_openai(self, prompt: str, title: str) -> str:
        """Make API call to OpenAI and return response text"""
        response = self.client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3,
        )
        response_text = response.choices[0].message.content
        logger.info(f"OpenAI response for {title}: {response_text[:200]}")
        return response_text

    def analyze(self, title: str, overview: str, year: Optional[int] = None) -> AnalysisResult:
        start_time = datetime.utcnow()
        prompt = self._build_prompt(title, overview, year)

        try:
            response_text = self._call_openai(prompt, title)
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

    def summarize_content(
        self,
        title: str,
        overview: str,
        rating: str,
        media_type: str = "movie",
        year: Optional[int] = None,
        content_data: Optional[str] = None
    ) -> AnalysisResult:
        """Primary: describe content concerns when official rating is known"""
        start_time = datetime.utcnow()
        prompt = self._build_content_prompt(title, overview, rating, media_type, year, content_data)

        try:
            response_text = self._call_openai(prompt, title)
            return self._parse_content_response(response_text, rating, start_time)

        except Exception as e:
            logger.error(f"OpenAI content summary error for {title}: {e}")
            return AnalysisResult(
                rating=rating,
                summary=f'API error: {str(e)}',
                concerns=['Content analysis failed - held for manual review'],
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

    def _call_grok(self, prompt: str, title: str) -> str:
        """Make API call to Grok and return response text"""
        response = self.client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3,
        )
        response_text = response.choices[0].message.content
        logger.info(f"Grok response for {title}: {response_text[:200]}")
        return response_text

    def analyze(self, title: str, overview: str, year: Optional[int] = None) -> AnalysisResult:
        start_time = datetime.utcnow()
        prompt = self._build_prompt(title, overview, year)

        try:
            response_text = self._call_grok(prompt, title)
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

    def summarize_content(
        self,
        title: str,
        overview: str,
        rating: str,
        media_type: str = "movie",
        year: Optional[int] = None,
        content_data: Optional[str] = None
    ) -> AnalysisResult:
        """Primary: describe content concerns when official rating is known"""
        start_time = datetime.utcnow()
        prompt = self._build_content_prompt(title, overview, rating, media_type, year, content_data)

        try:
            response_text = self._call_grok(prompt, title)
            return self._parse_content_response(response_text, rating, start_time)

        except Exception as e:
            logger.error(f"Grok content summary error for {title}: {e}")
            return AnalysisResult(
                rating=rating,
                summary=f'API error: {str(e)}',
                concerns=['Content analysis failed - held for manual review'],
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
