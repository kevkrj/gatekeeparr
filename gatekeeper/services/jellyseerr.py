"""
Jellyseerr API Client

Handles communication with Jellyseerr for:
- User information lookup
- Request approval/decline
- Connection testing
"""

import logging
from typing import Optional
from dataclasses import dataclass

import requests

from gatekeeper.config import get_config

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class JellyseerrUser:
    """User information from Jellyseerr"""
    id: int
    email: str
    username: Optional[str]
    display_name: Optional[str]
    jellyfin_user_id: Optional[str]
    user_type: int  # 1 = Plex, 2 = Local, 3 = Jellyfin
    permissions: int
    avatar: Optional[str]
    created_at: str

    @property
    def is_admin(self) -> bool:
        """Check if user has admin permissions (permission bit 2)"""
        return bool(self.permissions & 2)

    @classmethod
    def from_api(cls, data: dict) -> "JellyseerrUser":
        """Create from API response"""
        return cls(
            id=data.get('id'),
            email=data.get('email', ''),
            username=data.get('username'),
            display_name=data.get('displayName'),
            jellyfin_user_id=data.get('jellyfinUserId'),
            user_type=data.get('userType', 0),
            permissions=data.get('permissions', 0),
            avatar=data.get('avatar'),
            created_at=data.get('createdAt', ''),
        )


# =============================================================================
# Client
# =============================================================================

class JellyseerrClient:
    """Client for Jellyseerr API"""

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None):
        config = get_config()
        self.base_url = (url or config.jellyseerr.url).rstrip('/')
        self.api_key = api_key or config.jellyseerr.api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })
        if self.api_key:
            self.session.headers['X-Api-Key'] = self.api_key

    # -------------------------------------------------------------------------
    # HTTP Methods
    # -------------------------------------------------------------------------

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make GET request to Jellyseerr API"""
        url = f"{self.base_url}/api/v1{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Jellyseerr API error: {e}")
            raise

    def _post(self, endpoint: str, data: dict = None) -> dict:
        """Make POST request to Jellyseerr API"""
        url = f"{self.base_url}/api/v1{endpoint}"
        try:
            response = self.session.post(url, json=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Jellyseerr API error: {e}")
            raise

    # -------------------------------------------------------------------------
    # User Methods
    # -------------------------------------------------------------------------

    def get_user(self, user_id: int) -> Optional[JellyseerrUser]:
        """Get user by ID"""
        try:
            data = self._get(f"/user/{user_id}")
            return JellyseerrUser.from_api(data)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_users(self, take: int = 100, skip: int = 0) -> list[JellyseerrUser]:
        """Get paginated list of users"""
        data = self._get("/user", params={'take': take, 'skip': skip})
        results = data.get('results', [])
        return [JellyseerrUser.from_api(u) for u in results]

    def get_all_users(self) -> list[JellyseerrUser]:
        """Get all users from Jellyseerr"""
        users = []
        skip = 0
        take = 100

        while True:
            batch = self.get_users(take=take, skip=skip)
            users.extend(batch)
            if len(batch) < take:
                break
            skip += take

        return users

    # -------------------------------------------------------------------------
    # Request Methods
    # -------------------------------------------------------------------------

    def approve_request(self, request_id: int) -> bool:
        """Approve a pending request in Jellyseerr"""
        try:
            self._post(f"/request/{request_id}/approve")
            logger.info(f"Approved Jellyseerr request {request_id}")
            return True
        except requests.HTTPError as e:
            logger.error(f"Failed to approve request {request_id}: {e}")
            return False

    def decline_request(self, request_id: int) -> bool:
        """Decline a pending request in Jellyseerr"""
        try:
            self._post(f"/request/{request_id}/decline")
            logger.info(f"Declined Jellyseerr request {request_id}")
            return True
        except requests.HTTPError as e:
            logger.error(f"Failed to decline request {request_id}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Connection Test
    # -------------------------------------------------------------------------

    def test_connection(self) -> bool:
        """Test connection to Jellyseerr"""
        try:
            self._get("/status")
            return True
        except Exception as e:
            logger.error(f"Jellyseerr connection test failed: {e}")
            return False
