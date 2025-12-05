"""
Jellyseerr API Client

Handles communication with Jellyseerr for:
- User information lookup
- Request details
- Authentication verification
"""

import logging
from typing import Optional
from dataclasses import dataclass

import requests

from gatekeeper.config import get_config

logger = logging.getLogger(__name__)


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


@dataclass
class JellyseerrRequest:
    """Media request from Jellyseerr"""
    id: int
    status: int  # 1 = pending, 2 = approved, 3 = declined, 4 = available
    media_type: str  # 'movie' or 'tv'
    media_id: int  # TMDB ID
    requested_by: JellyseerrUser
    created_at: str
    updated_at: str

    # Status constants
    STATUS_PENDING = 1
    STATUS_APPROVED = 2
    STATUS_DECLINED = 3
    STATUS_AVAILABLE = 4

    @classmethod
    def from_api(cls, data: dict) -> "JellyseerrRequest":
        """Create from API response"""
        return cls(
            id=data.get('id'),
            status=data.get('status', 0),
            media_type=data.get('type', 'movie'),
            media_id=data.get('media', {}).get('tmdbId'),
            requested_by=JellyseerrUser.from_api(data.get('requestedBy', {})),
            created_at=data.get('createdAt', ''),
            updated_at=data.get('updatedAt', ''),
        )


class JellyseerrClient:
    """Client for Jellyseerr API"""

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize Jellyseerr client.

        Args:
            url: Jellyseerr base URL (e.g., http://localhost:5055)
            api_key: Jellyseerr API key
        """
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

    def get_user(self, user_id: int) -> Optional[JellyseerrUser]:
        """
        Get user by ID.

        Args:
            user_id: Jellyseerr user ID

        Returns:
            JellyseerrUser or None if not found
        """
        try:
            data = self._get(f"/user/{user_id}")
            return JellyseerrUser.from_api(data)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_users(self, take: int = 100, skip: int = 0) -> list[JellyseerrUser]:
        """
        Get list of users.

        Args:
            take: Number of users to fetch
            skip: Number of users to skip

        Returns:
            List of JellyseerrUser objects
        """
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

    def get_request(self, request_id: int) -> Optional[JellyseerrRequest]:
        """
        Get request by ID.

        Args:
            request_id: Jellyseerr request ID

        Returns:
            JellyseerrRequest or None if not found
        """
        try:
            data = self._get(f"/request/{request_id}")
            return JellyseerrRequest.from_api(data)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_requests(self, status: str = None, take: int = 100, skip: int = 0) -> list[JellyseerrRequest]:
        """
        Get list of requests.

        Args:
            status: Filter by status ('pending', 'approved', 'declined', 'available')
            take: Number of requests to fetch
            skip: Number of requests to skip

        Returns:
            List of JellyseerrRequest objects
        """
        params = {'take': take, 'skip': skip}
        if status:
            params['filter'] = status

        data = self._get("/request", params=params)
        results = data.get('results', [])
        return [JellyseerrRequest.from_api(r) for r in results]

    def authenticate(self, email: str, password: str) -> Optional[dict]:
        """
        Authenticate a user with Jellyseerr.

        Args:
            email: User email
            password: User password

        Returns:
            User data dict if successful, None otherwise
        """
        try:
            data = self._post("/auth/local", {'email': email, 'password': password})
            return data
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                return None
            raise

    def verify_session(self, cookie: str) -> Optional[JellyseerrUser]:
        """
        Verify a session cookie and get the authenticated user.

        Args:
            cookie: Session cookie value

        Returns:
            JellyseerrUser if session is valid, None otherwise
        """
        try:
            # Make request with the cookie
            response = self.session.get(
                f"{self.base_url}/api/v1/auth/me",
                cookies={'connect.sid': cookie},
                timeout=30
            )
            response.raise_for_status()
            return JellyseerrUser.from_api(response.json())
        except requests.HTTPError:
            return None

    def get_movie_details(self, tmdb_id: int) -> Optional[dict]:
        """
        Get movie details from Jellyseerr (cached TMDB data).

        Args:
            tmdb_id: TMDB movie ID

        Returns:
            Movie details dict or None
        """
        try:
            return self._get(f"/movie/{tmdb_id}")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_tv_details(self, tmdb_id: int) -> Optional[dict]:
        """
        Get TV show details from Jellyseerr (cached TMDB data).

        Args:
            tmdb_id: TMDB TV show ID

        Returns:
            TV show details dict or None
        """
        try:
            return self._get(f"/tv/{tmdb_id}")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def test_connection(self) -> bool:
        """Test connection to Jellyseerr"""
        try:
            self._get("/status")
            return True
        except Exception as e:
            logger.error(f"Jellyseerr connection test failed: {e}")
            return False
