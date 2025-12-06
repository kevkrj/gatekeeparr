"""
Sonarr API Client

Handles communication with Sonarr for:
- Series monitoring control
- Series deletion
- Queue management
"""

import logging
from typing import Optional
from dataclasses import dataclass

import requests

from gatekeeper.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class SonarrSeries:
    """Series information from Sonarr"""
    id: int
    title: str
    year: int
    tvdb_id: int
    imdb_id: Optional[str]
    overview: str
    monitored: bool
    path: str
    size_on_disk: int
    tags: list[int]
    seasons: list[dict]
    certification: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> "SonarrSeries":
        """Create from API response"""
        return cls(
            id=data.get('id'),
            title=data.get('title', ''),
            year=data.get('year', 0),
            tvdb_id=data.get('tvdbId'),
            imdb_id=data.get('imdbId'),
            overview=data.get('overview', ''),
            monitored=data.get('monitored', False),
            path=data.get('path', ''),
            size_on_disk=data.get('statistics', {}).get('sizeOnDisk', 0),
            tags=data.get('tags', []),
            seasons=data.get('seasons', []),
            certification=data.get('certification'),
        )


class SonarrClient:
    """Client for Sonarr API"""

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize Sonarr client.

        Args:
            url: Sonarr base URL (e.g., http://localhost:8989)
            api_key: Sonarr API key
        """
        config = get_config()
        self.base_url = (url or config.sonarr.url).rstrip('/')
        self.api_key = api_key or config.sonarr.api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Api-Key': self.api_key,
        })

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make GET request to Sonarr API"""
        url = f"{self.base_url}/api/v3{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Sonarr API error: {e}")
            raise

    def _put(self, endpoint: str, data: dict) -> dict:
        """Make PUT request to Sonarr API"""
        url = f"{self.base_url}/api/v3{endpoint}"
        try:
            response = self.session.put(url, json=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Sonarr API error: {e}")
            raise

    def _post(self, endpoint: str, data: dict = None) -> dict:
        """Make POST request to Sonarr API"""
        url = f"{self.base_url}/api/v3{endpoint}"
        try:
            response = self.session.post(url, json=data or {}, timeout=30)
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.RequestException as e:
            logger.error(f"Sonarr API error: {e}")
            raise

    def _delete(self, endpoint: str, params: dict = None) -> bool:
        """Make DELETE request to Sonarr API"""
        url = f"{self.base_url}/api/v3{endpoint}"
        try:
            response = self.session.delete(url, params=params, timeout=30)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Sonarr API error: {e}")
            raise

    def get_series(self, series_id: int) -> Optional[SonarrSeries]:
        """
        Get series by Sonarr ID.

        Args:
            series_id: Sonarr series ID

        Returns:
            SonarrSeries or None if not found
        """
        try:
            data = self._get(f"/series/{series_id}")
            return SonarrSeries.from_api(data)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_series_by_tvdb(self, tvdb_id: int) -> Optional[SonarrSeries]:
        """
        Get series by TVDB ID.

        Args:
            tvdb_id: TVDB series ID

        Returns:
            SonarrSeries or None if not found
        """
        try:
            data = self._get("/series", params={'tvdbId': tvdb_id})
            if data and len(data) > 0:
                return SonarrSeries.from_api(data[0])
            return None
        except requests.HTTPError:
            return None

    def get_certification(self, series_id: int) -> Optional[str]:
        """
        Get series certification/rating.

        Args:
            series_id: Sonarr series ID

        Returns:
            Certification string (e.g., 'TV-MA', 'TV-PG') or None
        """
        try:
            data = self._get(f"/series/{series_id}")
            return data.get('certification')
        except requests.HTTPError:
            return None

    def set_monitored(self, series_id: int, monitored: bool) -> bool:
        """
        Set series monitored status.

        Args:
            series_id: Sonarr series ID
            monitored: True to monitor, False to unmonitor

        Returns:
            True if successful
        """
        try:
            series = self._get(f"/series/{series_id}")
            series['monitored'] = monitored
            self._put(f"/series/{series_id}", series)
            logger.info(f"Set series {series_id} monitored={monitored}")
            return True
        except Exception as e:
            logger.error(f"Failed to set monitored for series {series_id}: {e}")
            return False

    def monitor(self, series_id: int) -> bool:
        """Enable monitoring for a series"""
        return self.set_monitored(series_id, True)

    def unmonitor(self, series_id: int) -> bool:
        """Disable monitoring for a series"""
        return self.set_monitored(series_id, False)

    def search_series(self, series_id: int) -> bool:
        """
        Trigger a search for a series.

        Args:
            series_id: Sonarr series ID

        Returns:
            True if search was triggered successfully
        """
        try:
            self._post("/command", {
                "name": "SeriesSearch",
                "seriesId": series_id
            })
            logger.info(f"Triggered search for series {series_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to trigger search for series {series_id}: {e}")
            return False

    def delete_series(self, series_id: int, delete_files: bool = True, add_exclusion: bool = False) -> bool:
        """
        Delete a series from Sonarr.

        Args:
            series_id: Sonarr series ID
            delete_files: Also delete downloaded files
            add_exclusion: Add to exclusion list to prevent re-adding

        Returns:
            True if successful
        """
        try:
            params = {
                'deleteFiles': str(delete_files).lower(),
                'addImportListExclusion': str(add_exclusion).lower(),
            }
            self._delete(f"/series/{series_id}", params=params)
            logger.info(f"Deleted series {series_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete series {series_id}: {e}")
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
        """Test connection to Sonarr"""
        try:
            self._get("/system/status")
            return True
        except Exception as e:
            logger.error(f"Sonarr connection test failed: {e}")
            return False
