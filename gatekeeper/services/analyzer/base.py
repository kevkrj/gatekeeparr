"""
Base classes and shared utilities for content analyzers.
"""

import json
import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

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
CONTENT_PROMPT = """Parental guide for: {title} ({year}) - Rated {rating}

Overview: {overview}
{content_data}
Write a brief JSON response. Keep it SHORT.

{{"age":"{rating}","summary":"One sentence why this rating","concerns":["First concern","Second concern","Third concern","Fourth concern"]}}

Rules:
- summary: ONE short sentence
- concerns: 3-4 simple strings, no nested objects
- Each concern under 15 words
- Output valid JSON only, no extra text"""

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
