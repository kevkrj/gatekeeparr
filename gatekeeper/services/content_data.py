"""
Content Data Fetcher

Fetches detailed parental content information from external sources.
Only called for content that needs parental approval (PG-13+, TV-14+).

Sources:
- Common Sense Media: Detailed age ratings, content breakdowns
- Future: IMDb Parental Guide, Kids-In-Mind, etc.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ContentInfo:
    """Parental content information from external sources"""
    source: str
    age_rating: Optional[str] = None
    violence: Optional[str] = None
    language: Optional[str] = None
    sexual_content: Optional[str] = None
    drugs_alcohol: Optional[str] = None
    scary_intense: Optional[str] = None
    summary: Optional[str] = None
    raw_data: dict = field(default_factory=dict)
    error: Optional[str] = None

    def has_data(self) -> bool:
        """Check if we got useful content data"""
        return any([
            self.violence,
            self.language,
            self.sexual_content,
            self.drugs_alcohol,
            self.scary_intense,
            self.summary  # Summary from reviewBody is also useful
        ])

    def to_prompt_context(self) -> str:
        """Format content info for AI prompt injection"""
        if not self.has_data():
            return ""

        parts = [f"Content information from {self.source}:"]

        if self.age_rating:
            parts.append(f"- Recommended age: {self.age_rating}")
        if self.violence:
            parts.append(f"- Violence: {self.violence}")
        if self.language:
            parts.append(f"- Language: {self.language}")
        if self.sexual_content:
            parts.append(f"- Sexual content: {self.sexual_content}")
        if self.drugs_alcohol:
            parts.append(f"- Drugs/Alcohol: {self.drugs_alcohol}")
        if self.scary_intense:
            parts.append(f"- Scary/Intense: {self.scary_intense}")
        if self.summary:
            parts.append(f"\nParent's guide summary: {self.summary}")

        return "\n".join(parts)


class CommonSenseMediaFetcher:
    """Fetch content data from Common Sense Media"""

    BASE_URL = "https://www.commonsensemedia.org"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        })

    def _slugify(self, title: str) -> str:
        """Convert title to URL slug"""
        # Remove special characters, convert to lowercase, replace spaces with hyphens
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[-\s]+', '-', slug).strip('-')
        return slug

    def fetch_movie(self, title: str, year: Optional[int] = None) -> ContentInfo:
        """Fetch content info for a movie"""
        return self._fetch(title, "movie-reviews", year)

    def fetch_tv(self, title: str, year: Optional[int] = None) -> ContentInfo:
        """Fetch content info for a TV show"""
        return self._fetch(title, "tv-reviews", year)

    def _fetch(self, title: str, review_type: str, year: Optional[int]) -> ContentInfo:
        """Fetch and parse content data from CSM"""
        slug = self._slugify(title)
        url = f"{self.BASE_URL}/{review_type}/{slug}"

        logger.info(f"Fetching Common Sense Media: {url}")

        try:
            response = self.session.get(url, timeout=self.timeout)

            # Try with year suffix if not found
            if response.status_code == 404 and year:
                url = f"{self.BASE_URL}/{review_type}/{slug}-{year}"
                logger.info(f"Trying with year: {url}")
                response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 404:
                logger.info(f"Not found on Common Sense Media: {title}")
                return ContentInfo(
                    source="Common Sense Media",
                    error="Not found"
                )

            response.raise_for_status()
            return self._parse_response(response.text)

        except requests.RequestException as e:
            logger.warning(f"Failed to fetch from Common Sense Media: {e}")
            return ContentInfo(
                source="Common Sense Media",
                error=str(e)
            )

    # Rating scale mapping (CSM uses 1-5 numeric scale)
    RATING_SCALE = {
        0: "None",
        1: "Very little",
        2: "A little",
        3: "Moderate",
        4: "A lot",
        5: "Extreme"
    }

    def _parse_response(self, html: str) -> ContentInfo:
        """Parse CSM HTML response to extract content info"""
        soup = BeautifulSoup(html, 'html.parser')
        info = ContentInfo(source="Common Sense Media")

        try:
            # Primary method: Parse JSON-LD schema data
            scripts = soup.select('script[type="application/ld+json"]')
            for script in scripts:
                try:
                    data = json.loads(script.string)

                    # Handle @graph structure (CSM wraps data in a graph array)
                    review_data = None
                    if isinstance(data, dict) and '@graph' in data:
                        for item in data['@graph']:
                            if item.get('@type') == 'Review':
                                review_data = item
                                break
                    elif isinstance(data, dict) and data.get('@type') == 'Review':
                        review_data = data
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get('@type') == 'Review':
                                review_data = item
                                break

                    if review_data:
                        info.raw_data = review_data

                        # Extract age rating
                        if 'typicalAgeRange' in review_data:
                            info.age_rating = review_data['typicalAgeRange']

                        # Get review body as summary (contains content descriptions)
                        review_body = review_data.get('reviewBody')
                        if review_body:
                            info.summary = review_body[:1000]
                            # Use summary presence to indicate we have data
                            # The reviewBody typically describes violence/language/etc.
                            logger.info(f"Parsed CSM JSON-LD: age={info.age_rating}, summary_len={len(review_body)}")

                except json.JSONDecodeError:
                    continue

            # Parse HTML for detailed content ratings (h3 headers with descriptions)
            # CSM uses h3 elements for category names like "Violence", "Sex", etc.
            for h3 in soup.find_all('h3'):
                header_text = h3.get_text(strip=True).lower()
                # Get the next sibling or parent's text content
                parent = h3.parent
                if parent:
                    # Get all text after the h3 in the same container
                    full_text = parent.get_text(strip=True)
                    # Remove the header itself
                    desc_text = full_text.replace(h3.get_text(strip=True), '', 1).strip()

                    # Clean up junk text from CSM interactive elements
                    for junk in ['Did you know you can flag iffy content?',
                                 'Adjust limits for', 'in your kid\'s entertainment guide.',
                                 'Get startedClose', 'Get started', 'Close',
                                 'Violence & Scariness', 'Drinking, Drugs & Smoking',
                                 'Language', 'Sex, Romance & Nudity']:
                        desc_text = desc_text.replace(junk, '')
                    desc_text = desc_text.strip()[:300]

                    if desc_text and len(desc_text) > 10:
                        if 'violence' in header_text and not info.violence:
                            info.violence = desc_text
                        elif 'sex' in header_text and not info.sexual_content:
                            info.sexual_content = desc_text
                        elif 'language' in header_text and not info.language:
                            info.language = desc_text
                        elif ('drinking' in header_text or 'drug' in header_text) and not info.drugs_alcohol:
                            info.drugs_alcohol = desc_text
                        elif ('scar' in header_text or 'intense' in header_text or 'frightening' in header_text) and not info.scary_intense:
                            info.scary_intense = desc_text

            # Fallback: HTML parsing for age rating
            if not info.age_rating:
                age_elem = soup.select_one('[data-testid="age-rating"], .age-rating, .review-age')
                if age_elem:
                    info.age_rating = age_elem.get_text(strip=True)

            logger.info(f"Parsed CSM data: age={info.age_rating}, has_content={info.has_data()}, summary={bool(info.summary)}")

        except Exception as e:
            logger.warning(f"Error parsing CSM response: {e}")
            info.error = f"Parse error: {e}"

        return info


class ContentDataFetcher:
    """
    Main content data fetcher that tries multiple sources.

    Usage:
        fetcher = ContentDataFetcher()
        info = fetcher.fetch("The Matrix", "movie", 1999)
        if info.has_data():
            # Use info.to_prompt_context() in AI prompt
    """

    def __init__(self):
        self.csm = CommonSenseMediaFetcher()
        # Future: Add more sources here
        # self.imdb = IMDbParentalGuideFetcher()
        # self.kids_in_mind = KidsInMindFetcher()

    def fetch(
        self,
        title: str,
        media_type: str = "movie",
        year: Optional[int] = None
    ) -> ContentInfo:
        """
        Fetch content data from available sources.

        Args:
            title: Media title
            media_type: "movie" or "tv"
            year: Release year (helps with disambiguation)

        Returns:
            ContentInfo with data from best available source
        """
        # Try Common Sense Media first
        if media_type == "movie":
            info = self.csm.fetch_movie(title, year)
        else:
            info = self.csm.fetch_tv(title, year)

        if info.has_data():
            return info

        # Future: Try other sources if CSM fails
        # info = self.imdb.fetch(title, media_type, year)
        # if info.has_data():
        #     return info

        # Return empty info if no source had data
        return ContentInfo(
            source="none",
            error="No content data found from any source"
        )


# Convenience function
def fetch_content_data(
    title: str,
    media_type: str = "movie",
    year: Optional[int] = None
) -> ContentInfo:
    """Fetch content data for a title"""
    fetcher = ContentDataFetcher()
    return fetcher.fetch(title, media_type, year)
