"""
Ollama local LLM analyzer for content analysis.
"""

import logging
from typing import Optional
from datetime import datetime

from .base import ContentAnalyzer, AnalysisResult

logger = logging.getLogger(__name__)


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
                "format": "json",  # Request JSON mode
                "options": {
                    "temperature": 0.1,  # Lower = more deterministic
                    "num_predict": 300,  # Shorter response, less chance of errors
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
