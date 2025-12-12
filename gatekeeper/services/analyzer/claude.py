"""
Anthropic Claude analyzer for content analysis.
"""

import logging
from typing import Optional
from datetime import datetime

from .base import ContentAnalyzer, AnalysisResult

logger = logging.getLogger(__name__)


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
