"""
TMDB API client for direct rating lookups.

Used to get content ratings at the Jellyseerr webhook stage,
before content is added to Radarr/Sonarr.
"""

import logging
from typing import Optional
import requests

from gatekeeper.config import get_config

logger = logging.getLogger(__name__)


class TMDBClient:
    """TMDB API client for rating lookups"""

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.themoviedb.org/3"):
        config = get_config()
        self.api_key = api_key or config.tmdb.api_key
        self.base_url = base_url.rstrip('/')

        if not self.api_key:
            logger.warning("TMDB API key not configured - rating lookups will fail")

    def _get(self, endpoint: str) -> Optional[dict]:
        """Make GET request to TMDB API"""
        if not self.api_key:
            return None

        try:
            # TMDB v3 API uses api_key query parameter
            separator = "&" if "?" in endpoint else "?"
            url = f"{self.base_url}{endpoint}{separator}api_key={self.api_key}"
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"TMDB API error: {e}")
            return None

    def get_movie_rating(self, tmdb_id: int) -> Optional[str]:
        """
        Get US certification for a movie.

        Args:
            tmdb_id: TMDB movie ID

        Returns:
            US certification string (e.g., "PG-13", "R") or None if not found
        """
        data = self._get(f"/movie/{tmdb_id}/release_dates")
        if not data:
            return None

        # Find US release info
        for result in data.get("results", []):
            if result.get("iso_3166_1") == "US":
                # Get the most relevant certification
                for release in result.get("release_dates", []):
                    cert = release.get("certification")
                    if cert:
                        logger.info(f"TMDB movie {tmdb_id} certification: {cert}")
                        return cert

        logger.warning(f"No US certification found for movie {tmdb_id}")
        return None

    def get_tv_rating(self, tmdb_id: int) -> Optional[str]:
        """
        Get US content rating for a TV series.

        Args:
            tmdb_id: TMDB TV series ID

        Returns:
            US content rating (e.g., "TV-14", "TV-MA") or None if not found
        """
        data = self._get(f"/tv/{tmdb_id}/content_ratings")
        if not data:
            return None

        # Find US rating
        for result in data.get("results", []):
            if result.get("iso_3166_1") == "US":
                rating = result.get("rating")
                if rating:
                    logger.info(f"TMDB TV {tmdb_id} rating: {rating}")
                    return rating

        logger.warning(f"No US content rating found for TV {tmdb_id}")
        return None

    def get_movie_details(self, tmdb_id: int) -> Optional[dict]:
        """
        Get movie details including title, overview, year.

        Args:
            tmdb_id: TMDB movie ID

        Returns:
            Dict with title, overview, year, etc. or None if not found
        """
        data = self._get(f"/movie/{tmdb_id}")
        if not data:
            return None

        return {
            "title": data.get("title"),
            "overview": data.get("overview"),
            "year": int(data.get("release_date", "0000")[:4]) if data.get("release_date") else None,
            "tmdb_id": tmdb_id,
        }

    def get_tv_details(self, tmdb_id: int) -> Optional[dict]:
        """
        Get TV series details including title, overview, year.

        Args:
            tmdb_id: TMDB TV series ID

        Returns:
            Dict with title, overview, year, etc. or None if not found
        """
        data = self._get(f"/tv/{tmdb_id}")
        if not data:
            return None

        return {
            "title": data.get("name"),
            "overview": data.get("overview"),
            "year": int(data.get("first_air_date", "0000")[:4]) if data.get("first_air_date") else None,
            "tmdb_id": tmdb_id,
        }

    def get_rating(self, tmdb_id: int, media_type: str) -> Optional[str]:
        """
        Get rating for movie or TV series.

        Args:
            tmdb_id: TMDB ID
            media_type: "movie" or "tv"

        Returns:
            Rating string or None
        """
        if media_type == "movie":
            return self.get_movie_rating(tmdb_id)
        elif media_type == "tv":
            return self.get_tv_rating(tmdb_id)
        else:
            logger.warning(f"Unknown media type: {media_type}")
            return None

    def get_details(self, tmdb_id: int, media_type: str) -> Optional[dict]:
        """
        Get details for movie or TV series.

        Args:
            tmdb_id: TMDB ID
            media_type: "movie" or "tv"

        Returns:
            Details dict or None
        """
        if media_type == "movie":
            return self.get_movie_details(tmdb_id)
        elif media_type == "tv":
            return self.get_tv_details(tmdb_id)
        else:
            logger.warning(f"Unknown media type: {media_type}")
            return None


# Global client instance
_client: Optional[TMDBClient] = None


def get_tmdb_client() -> TMDBClient:
    """Get or create global TMDB client instance"""
    global _client
    if _client is None:
        _client = TMDBClient()
    return _client
