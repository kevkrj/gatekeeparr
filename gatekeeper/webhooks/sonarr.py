"""
Sonarr Webhook Handler

Handles download completion events from Sonarr.
Creates symlinks in the Kids Approved library for:
1. Any TV-Y/TV-Y7/TV-G/TV-PG rated series (auto-add)
2. Approved kid requests for TV-14+ series
"""

import logging
from pathlib import Path
from flask import Blueprint, request, jsonify
import requests as http_requests

from gatekeeper.models import db, Request
from gatekeeper.services.tmdb import TMDBClient
from gatekeeper.config import get_config

logger = logging.getLogger(__name__)

# Ratings that are automatically kid-safe
KIDS_SAFE_RATINGS = ['G', 'PG', 'TV-Y', 'TV-Y7', 'TV-G', 'TV-PG']

sonarr_bp = Blueprint('sonarr', __name__)

# Path configuration - where symlinks go
KIDS_APPROVED_TV_PATH = '/media/kids-approved/tv'
TV_PATH = '/media/tv'

# Path translation: *arr containers use different mount points
# Sonarr uses /tv, Gatekeeper uses /media/tv
PATH_MAPPINGS = [
    ('/tv/', '/media/tv/'),
    ('/tv', '/media/tv'),
]


def _translate_path(path: str) -> str:
    """Translate *arr container paths to Gatekeeper paths."""
    for arr_path, local_path in PATH_MAPPINGS:
        if path.startswith(arr_path):
            return path.replace(arr_path, local_path, 1)
    return path


@sonarr_bp.route('/webhook/sonarr', methods=['POST'])
def handle_sonarr_webhook():
    """
    Handle Sonarr webhook events.

    We only care about 'Download' events (on import).
    When an episode finishes downloading, check if the series should be
    in kids-approved and create a symlink if so.

    Sonarr webhook payload for Download:
    {
        "eventType": "Download",
        "series": {
            "id": 123,
            "title": "Series Title",
            "year": 2024,
            "tvdbId": 456789,
            "tvMazeId": 12345,
            "imdbId": "tt1234567",
            "path": "/media/tv/Series Title (2024)"
        },
        "episodes": [...],
        "episodeFile": {
            "relativePath": "Season 01/Series Title - S01E01 - Episode Name.mkv",
            "path": "/media/tv/Series Title (2024)/Season 01/..."
        },
        "isUpgrade": false
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON data'}), 400

        event_type = data.get('eventType')
        logger.info(f"Sonarr webhook received: {event_type}")

        # Only process Download events (on import)
        if event_type != 'Download':
            logger.debug(f"Ignoring event type: {event_type}")
            return jsonify({'status': 'ignored', 'reason': f'Event type {event_type} not handled'})

        return _handle_download(data)

    except Exception as e:
        logger.error(f"Error handling Sonarr webhook: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


def _handle_download(data: dict):
    """Handle a series episode download completion event."""
    series = data.get('series', {})
    tvdb_id = series.get('tvdbId')
    title = series.get('title', 'Unknown')
    folder_path = series.get('path')

    if not folder_path:
        logger.warning(f"No folder path in Sonarr download event for {title}")
        return jsonify({'status': 'ignored', 'reason': 'No folder path'})

    # Translate Sonarr's container path to Gatekeeper's path
    folder_path = _translate_path(folder_path)
    logger.debug(f"Translated path for {title}: {folder_path}")

    # Check 1: Is this a kids-safe rated series? Auto-add to kids approved
    # Try TMDB first (need to look up by TVDB ID or title)
    try:
        tmdb = TMDBClient()
        # Sonarr provides tvdbId, we need to get TMDB rating
        # First try to find TMDB ID from our request records
        media_request = Request.query.filter_by(
            media_type='series'
        ).filter(
            Request.title.ilike(f"%{title}%")
        ).order_by(Request.created_at.desc()).first()

        tmdb_id = media_request.tmdb_id if media_request else None
        rating = None

        if tmdb_id:
            rating = tmdb.get_tv_rating(tmdb_id)
            logger.info(f"TMDB rating for {title}: {rating}")

        if rating and rating in KIDS_SAFE_RATINGS:
            success = _create_symlink(folder_path, title)
            if success:
                logger.info(f"Auto-added {title} to Kids Approved (rating: {rating})")
                _refresh_jellyfin_library(folder_path, title)
                return jsonify({
                    'status': 'ok',
                    'symlink': True,
                    'title': title,
                    'reason': f'Auto-added: {rating} rating'
                })
    except Exception as e:
        logger.warning(f"Could not check TMDB rating for {title}: {e}")

    # Check 2: Was this an approved kid request?
    media_request = Request.query.filter_by(
        media_type='series'
    ).filter(
        Request.title.ilike(f"%{title}%")
    ).order_by(Request.created_at.desc()).first()

    if not media_request:
        logger.debug(f"No request found for series {title}")
        return jsonify({'status': 'ok', 'symlink': False, 'reason': 'No matching request and not kids-safe rating'})

    # Only create symlink for approved requests
    if media_request.status not in (Request.STATUS_APPROVED, Request.STATUS_AUTO_APPROVED):
        logger.debug(f"Request {media_request.id} status is {media_request.status}, not approved")
        return jsonify({
            'status': 'ok',
            'symlink': False,
            'reason': f'Request status is {media_request.status}'
        })

    # Check if the user was a kid (only kids need symlinks for non-kids-safe content)
    if media_request.user and media_request.user.user_type != 'kid':
        logger.debug(f"Request by {media_request.user.username} is not a kid, skipping symlink")
        return jsonify({
            'status': 'ok',
            'symlink': False,
            'reason': f'Requester is {media_request.user.user_type}, not kid'
        })

    # Create symlink for approved kid request
    success = _create_symlink(folder_path, title)

    if success:
        logger.info(f"Created Kids Approved symlink for {title} (approved kid request)")
        _refresh_jellyfin_library(folder_path, title)
        return jsonify({'status': 'ok', 'symlink': True, 'title': title})
    else:
        return jsonify({'status': 'ok', 'symlink': False, 'reason': 'Symlink creation failed'})


def _create_symlink(source_folder: str, title: str) -> bool:
    """
    Create a symlink from the source series folder to kids-approved.

    Args:
        source_folder: Full path to series folder in /media/tv/
        title: Series title (for logging)

    Returns:
        True if symlink created successfully
    """
    try:
        source = Path(source_folder)

        if not source.exists():
            logger.error(f"Source folder does not exist: {source_folder}")
            return False

        # Create symlink with same folder name
        link_name = source.name
        link_path = Path(KIDS_APPROVED_TV_PATH) / link_name

        # Don't create if already exists
        if link_path.exists() or link_path.is_symlink():
            logger.info(f"Symlink already exists: {link_path}")
            return True

        # Create symlink
        link_path.symlink_to(source)
        logger.info(f"Created symlink: {link_path} -> {source}")
        return True

    except Exception as e:
        logger.error(f"Failed to create symlink for {title}: {e}")
        return False


def _refresh_jellyfin_library(series_path: str, title: str):
    """
    Notify Jellyfin to rescan the Kids TV library for new content.

    Args:
        series_path: Path to the series in kids-approved folder
        title: Series title (for logging)
    """
    config = get_config()
    if not config.jellyfin.api_key:
        logger.debug("Jellyfin API key not configured, skipping refresh")
        return

    try:
        # Trigger a library scan - Jellyfin will detect the new content
        url = f"{config.jellyfin.url}/Library/Refresh"
        response = http_requests.post(
            url,
            headers={"X-Emby-Token": config.jellyfin.api_key},
            timeout=10
        )
        if response.status_code in (200, 204):
            logger.info(f"Triggered Jellyfin library refresh for {title}")
        else:
            logger.warning(f"Jellyfin refresh returned {response.status_code}")
    except Exception as e:
        logger.warning(f"Failed to refresh Jellyfin library: {e}")
