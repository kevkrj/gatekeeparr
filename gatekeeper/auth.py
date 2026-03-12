"""
Authentication module for Gatekeeper admin panel.

Authenticates users against Jellyseerr/Seerr's local auth endpoint and manages
Flask sessions. Only admins get full access; non-admins get read-only dashboard
access.
"""

import functools
import logging

import requests as http_requests
from flask import session, redirect, url_for, request, jsonify

from gatekeeper.config import get_config

logger = logging.getLogger(__name__)


def login_via_jellyseerr(email: str, password: str) -> dict | None:
    """
    Authenticate against Jellyseerr's local auth endpoint.

    Args:
        email: Username or email address
        password: User's password

    Returns:
        User dict from Jellyseerr on success, None on failure
    """
    config = get_config()
    base_url = config.jellyseerr.url.rstrip('/')
    auth_url = f"{base_url}/api/v1/auth/local"

    try:
        resp = http_requests.post(
            auth_url,
            json={"email": email, "password": password},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=15,
        )

        if resp.status_code == 200:
            user_data = resp.json()
            logger.info(
                "Jellyseerr auth success for user %s (id=%s)",
                user_data.get("username") or user_data.get("email"),
                user_data.get("id"),
            )
            return user_data

        logger.warning(
            "Jellyseerr auth failed for %s: HTTP %s", email, resp.status_code
        )
        return None

    except http_requests.RequestException as e:
        logger.error("Jellyseerr auth request error: %s", e)
        return None


def get_current_user() -> dict | None:
    """
    Get the authenticated user from the Flask session.

    Returns:
        User info dict or None if not authenticated
    """
    return session.get("user")


def is_admin() -> bool:
    """Check if the current session user is an admin."""
    user = get_current_user()
    if not user:
        return False
    # Jellyseerr permission bit 2 = admin
    return bool(user.get("permissions", 0) & 2)


def require_auth(f):
    """
    Decorator that redirects to login page if not authenticated.
    For use on HTML-serving routes.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def require_auth_api(f):
    """
    Decorator that returns 401 JSON if not authenticated.
    For use on API (JSON) routes.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """
    Decorator that checks the user is a Jellyseerr admin.
    Returns 403 for non-admin users. Must be used after require_auth.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not is_admin():
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated
