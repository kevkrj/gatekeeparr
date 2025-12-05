"""
Radarr API Client

Handles communication with Radarr for:
- Movie monitoring control
- Movie deletion
- Queue management
"""

import logging
from typing import Optional
from dataclasses import dataclass

import requests

from gatekeeper.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class RadarrMovie:
    """Movie information from Radarr"""
    id: int
    title: str
    year: int
    tmdb_id: int
    imdb_id: Optional[str]
    overview: str
    monitored: bool
    has_file: bool
    path: str
    size_on_disk: int
    tags: list[int]

    @classmethod
    def from_api(cls, data: dict) -> "RadarrMovie":
        """Create from API response"""
        return cls(
            id=data.get('id'),
            title=data.get('title', ''),
            year=data.get('year', 0),
            tmdb_id=data.get('tmdbId'),
            imdb_id=data.get('imdbId'),
            overview=data.get('overview', ''),
            monitored=data.get('monitored', False),
            has_file=data.get('hasFile', False),
            path=data.get('path', ''),
            size_on_disk=data.get('sizeOnDisk', 0),
            tags=data.get('tags', []),
        )


class RadarrClient:
    """Client for Radarr API"""

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize Radarr client.

        Args:
            url: Radarr base URL (e.g., http://localhost:7878)
            api_key: Radarr API key
        """
        config = get_config()
        self.base_url = (url or config.radarr.url).rstrip('/')
        self.api_key = api_key or config.radarr.api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Api-Key': self.api_key,
        })

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make GET request to Radarr API"""
        url = f"{self.base_url}/api/v3{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Radarr API error: {e}")
            raise

    def _put(self, endpoint: str, data: dict) -> dict:
        """Make PUT request to Radarr API"""
        url = f"{self.base_url}/api/v3{endpoint}"
        try:
            response = self.session.put(url, json=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Radarr API error: {e}")
            raise

    def _delete(self, endpoint: str, params: dict = None) -> bool:
        """Make DELETE request to Radarr API"""
        url = f"{self.base_url}/api/v3{endpoint}"
        try:
            response = self.session.delete(url, params=params, timeout=30)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Radarr API error: {e}")
            raise

    def get_movie(self, movie_id: int) -> Optional[RadarrMovie]:
        """
        Get movie by Radarr ID.

        Args:
            movie_id: Radarr movie ID

        Returns:
            RadarrMovie or None if not found
        """
        try:
            data = self._get(f"/movie/{movie_id}")
            return RadarrMovie.from_api(data)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_movie_by_tmdb(self, tmdb_id: int) -> Optional[RadarrMovie]:
        """
        Get movie by TMDB ID.

        Args:
            tmdb_id: TMDB movie ID

        Returns:
            RadarrMovie or None if not found
        """
        try:
            data = self._get("/movie", params={'tmdbId': tmdb_id})
            if data and len(data) > 0:
                return RadarrMovie.from_api(data[0])
            return None
        except requests.HTTPError:
            return None

    def set_monitored(self, movie_id: int, monitored: bool) -> bool:
        """
        Set movie monitored status.

        Args:
            movie_id: Radarr movie ID
            monitored: True to monitor, False to unmonitor

        Returns:
            True if successful
        """
        try:
            movie = self._get(f"/movie/{movie_id}")
            movie['monitored'] = monitored
            self._put(f"/movie/{movie_id}", movie)
            logger.info(f"Set movie {movie_id} monitored={monitored}")
            return True
        except Exception as e:
            logger.error(f"Failed to set monitored for movie {movie_id}: {e}")
            return False

    def monitor(self, movie_id: int) -> bool:
        """Enable monitoring for a movie"""
        return self.set_monitored(movie_id, True)

    def unmonitor(self, movie_id: int) -> bool:
        """Disable monitoring for a movie"""
        return self.set_monitored(movie_id, False)

    def delete_movie(self, movie_id: int, delete_files: bool = True, add_exclusion: bool = False) -> bool:
        """
        Delete a movie from Radarr.

        Args:
            movie_id: Radarr movie ID
            delete_files: Also delete downloaded files
            add_exclusion: Add to exclusion list to prevent re-adding

        Returns:
            True if successful
        """
        try:
            params = {
                'deleteFiles': str(delete_files).lower(),
                'addImportExclusion': str(add_exclusion).lower(),
            }
            self._delete(f"/movie/{movie_id}", params=params)
            logger.info(f"Deleted movie {movie_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete movie {movie_id}: {e}")
            return False

    def get_queue(self) -> list[dict]:
        """
        Get download queue.

        Returns:
            List of queue items
        """
        data = self._get("/queue", params={'pageSize': 1000})
        return data.get('records', [])

    def delete_queue_item(self, queue_id: int, blocklist: bool = True, remove_from_client: bool = True) -> bool:
        """
        Delete item from download queue.

        Args:
            queue_id: Queue item ID
            blocklist: Add release to blocklist
            remove_from_client: Remove from download client

        Returns:
            True if successful
        """
        try:
            params = {
                'removeFromClient': str(remove_from_client).lower(),
                'blocklist': str(blocklist).lower(),
            }
            self._delete(f"/queue/{queue_id}", params=params)
            logger.info(f"Deleted queue item {queue_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete queue item {queue_id}: {e}")
            return False

    def get_tags(self) -> list[dict]:
        """Get all tags"""
        return self._get("/tag")

    def test_connection(self) -> bool:
        """Test connection to Radarr"""
        try:
            self._get("/system/status")
            return True
        except Exception as e:
            logger.error(f"Radarr connection test failed: {e}")
            return False
