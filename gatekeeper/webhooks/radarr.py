"""
Radarr Webhook Handler

Handles download completion events from Radarr.
Creates symlinks in the Kids Approved library for:
1. Any G or PG rated movie (auto-add)
2. Approved kid requests for PG-13+ movies
"""

import logging
import os
from pathlib import Path
from flask import Blueprint, request, jsonify
import requests as http_requests

from gatekeeper.models import db, Request
from gatekeeper.services.tmdb import TMDBClient
from gatekeeper.config import get_config

logger = logging.getLogger(__name__)

# Ratings that are automatically kid-safe
KIDS_SAFE_RATINGS = ['G', 'PG', 'TV-Y', 'TV-Y7', 'TV-G', 'TV-PG']

radarr_bp = Blueprint('radarr', __name__)

# Path configuration - where symlinks go
KIDS_APPROVED_MOVIES_PATH = '/media/kids-approved/movies'
MOVIES_PATH = '/media/movies'

# Path translation: *arr containers use different mount points
# Radarr uses /movies, Gatekeeper uses /media/movies
PATH_MAPPINGS = [
    ('/movies/', '/media/movies/'),
    ('/movies', '/media/movies'),
]


def _translate_path(path: str) -> str:
    """Translate *arr container paths to Gatekeeper paths."""
    for arr_path, local_path in PATH_MAPPINGS:
        if path.startswith(arr_path):
            return path.replace(arr_path, local_path, 1)
    return path


@radarr_bp.route('/webhook/radarr', methods=['POST'])
def handle_radarr_webhook():
    """
    Handle Radarr webhook events.

    We only care about 'Download' events (on import).
    When a movie finishes downloading, check if it was an approved
    kid request and create a symlink if so.

    Radarr webhook payload for Download:
    {
        "eventType": "Download",
        "movie": {
            "id": 123,
            "title": "Movie Title",
            "year": 2024,
            "tmdbId": 456789,
            "imdbId": "tt1234567",
            "folderPath": "/media/movies/Movie Title (2024)"
        },
        "movieFile": {
            "relativePath": "Movie Title (2024).mkv",
            "path": "/media/movies/Movie Title (2024)/Movie Title (2024).mkv"
        },
        "isUpgrade": false
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON data'}), 400

        event_type = data.get('eventType')
        logger.info(f"Radarr webhook received: {event_type}")

        # Only process Download events (on import)
        if event_type != 'Download':
            logger.debug(f"Ignoring event type: {event_type}")
            return jsonify({'status': 'ignored', 'reason': f'Event type {event_type} not handled'})

        return _handle_download(data)

    except Exception as e:
        logger.error(f"Error handling Radarr webhook: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


def _handle_download(data: dict):
    """Handle a movie download completion event."""
    movie = data.get('movie', {})
    tmdb_id = movie.get('tmdbId')
    title = movie.get('title', 'Unknown')
    folder_path = movie.get('folderPath')

    if not tmdb_id:
        logger.warning(f"No TMDB ID in Radarr download event for {title}")
        return jsonify({'status': 'ignored', 'reason': 'No TMDB ID'})

    if not folder_path:
        logger.warning(f"No folder path in Radarr download event for {title}")
        return jsonify({'status': 'ignored', 'reason': 'No folder path'})

    # Translate Radarr's container path to Gatekeeper's path
    folder_path = _translate_path(folder_path)
    logger.debug(f"Translated path for {title}: {folder_path}")

    # Check 1: Is this a G/PG movie? Auto-add to kids approved
    try:
        tmdb = TMDBClient()
        rating = tmdb.get_movie_rating(tmdb_id)
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
        tmdb_id=tmdb_id,
        media_type='movie'
    ).order_by(Request.created_at.desc()).first()

    if not media_request:
        logger.debug(f"No request found for TMDB {tmdb_id} ({title})")
        return jsonify({'status': 'ok', 'symlink': False, 'reason': 'No matching request and not G/PG'})

    # Only create symlink for approved requests
    if media_request.status not in (Request.STATUS_APPROVED, Request.STATUS_AUTO_APPROVED):
        logger.debug(f"Request {media_request.id} status is {media_request.status}, not approved")
        return jsonify({
            'status': 'ok',
            'symlink': False,
            'reason': f'Request status is {media_request.status}'
        })

    # Check if the user was a kid (only kids need symlinks for non-G/PG)
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
    Create a symlink from the source movie folder to kids-approved.

    Args:
        source_folder: Full path to movie folder in /media/movies/
        title: Movie title (for logging)

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
        link_path = Path(KIDS_APPROVED_MOVIES_PATH) / link_name

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


def _refresh_jellyfin_library(movie_path: str, title: str):
    """
    Notify Jellyfin to rescan the Kids Movies library for new content.

    Args:
        movie_path: Path to the movie in kids-approved folder
        title: Movie title (for logging)
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


def cleanup_broken_symlinks() -> int:
    """
    Remove broken symlinks from kids-approved folder.

    Returns:
        Number of broken symlinks removed
    """
    kids_path = Path(KIDS_APPROVED_MOVIES_PATH)
    removed = 0

    if not kids_path.exists():
        logger.warning(f"Kids approved path does not exist: {KIDS_APPROVED_MOVIES_PATH}")
        return 0

    for item in kids_path.iterdir():
        if item.is_symlink() and not item.exists():
            try:
                item.unlink()
                logger.info(f"Removed broken symlink: {item}")
                removed += 1
            except Exception as e:
                logger.error(f"Failed to remove broken symlink {item}: {e}")

    return removed


@radarr_bp.route('/maintenance/cleanup-symlinks', methods=['POST'])
def api_cleanup_symlinks():
    """
    API endpoint to clean up broken symlinks in kids-approved folder.
    Can be called by cron or manually.
    """
    try:
        removed = cleanup_broken_symlinks()
        return jsonify({
            'status': 'ok',
            'removed': removed,
            'message': f'Removed {removed} broken symlinks'
        })
    except Exception as e:
        logger.error(f"Error during symlink cleanup: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500
