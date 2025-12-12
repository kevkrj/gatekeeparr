"""
OpenAI-compatible analyzers for content analysis.

Includes:
- OpenAIAnalyzer: Standard OpenAI GPT models
- GrokAnalyzer: xAI Grok (uses OpenAI-compatible API)
"""

import logging
from typing import Optional
from datetime import datetime

from .base import ContentAnalyzer, AnalysisResult

logger = logging.getLogger(__name__)


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
            temperature=0.2,
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
            temperature=0.2,
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
