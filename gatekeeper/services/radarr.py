"""
Radarr API Client

Minimal client for connection testing.
"""

import logging
from typing import Optional

import requests

from gatekeeper.config import get_config

logger = logging.getLogger(__name__)


class RadarrClient:
    """Client for Radarr API"""

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None):
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

    def test_connection(self) -> bool:
        """Test connection to Radarr"""
        try:
            self._get("/system/status")
            return True
        except Exception as e:
            logger.error(f"Radarr connection test failed: {e}")
            return False
