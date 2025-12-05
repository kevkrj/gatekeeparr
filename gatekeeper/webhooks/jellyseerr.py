"""
Jellyseerr Webhook Handler

Handles incoming webhooks from Jellyseerr for:
- media.pending: New request pending approval
- media.approved: Request approved in Jellyseerr
- media.available: Media now available

This allows catching requests BEFORE they go to Radarr/Sonarr,
enabling pre-filtering based on user type.
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

from gatekeeper.models import db, Request
from gatekeeper.services.router import UserRouter
from gatekeeper.services.jellyseerr import JellyseerrClient

logger = logging.getLogger(__name__)

jellyseerr_bp = Blueprint('jellyseerr', __name__, url_prefix='/webhook')


@jellyseerr_bp.route('/jellyseerr', methods=['POST'])
def jellyseerr_webhook():
    """
    Handle Jellyseerr webhook events.

    This webhook is optional but recommended for:
    - Early user identification (before Radarr/Sonarr)
    - Pre-request filtering (block before it hits *arr)
    """
    data = request.json
    notification_type = data.get('notification_type')

    logger.info(f"Jellyseerr webhook: {notification_type}")
    logger.info(f"Webhook data: {data}")

    # Only process media request events
    if notification_type not in ('MEDIA_PENDING', 'MEDIA_APPROVED', 'MEDIA_AUTO_APPROVED'):
        logger.debug(f"Ignoring notification type: {notification_type}")
        return jsonify({'status': 'ignored', 'type': notification_type}), 200

    # Extract request info
    media = data.get('media', {})
    media_type = media.get('media_type', 'movie')  # 'movie' or 'tv'
    tmdb_id = media.get('tmdbId')
    tvdb_id = media.get('tvdbId')

    # Extract user info - Jellyseerr uses flat structure with underscores
    request_info = data.get('request', {})
    jellyseerr_request_id = request_info.get('request_id')

    # Jellyseerr webhook uses requestedBy_username, requestedBy_email format
    username = request_info.get('requestedBy_username') or request_info.get('requestedBy_email', 'Unknown')
    jellyseerr_user_id = None  # Not provided in webhook, would need API lookup

    # Get or create user
    router = UserRouter()
    user = None

    if jellyseerr_user_id:
        user = router.lookup_user_by_jellyseerr_id(jellyseerr_user_id)

    # Create request record for tracking
    media_request = Request.query.filter_by(
        jellyseerr_request_id=jellyseerr_request_id
    ).first()

    if not media_request:
        media_request = Request(
            jellyseerr_request_id=jellyseerr_request_id,
            media_type='movie' if media_type == 'movie' else 'series',
            tmdb_id=tmdb_id,
            title=data.get('subject', 'Unknown'),
            requested_by_username=username,
            requested_at=datetime.utcnow(),
            status=Request.STATUS_PENDING,
        )
        if user:
            media_request.user_id = user.id
        db.session.add(media_request)
        db.session.commit()

    logger.info(f"Tracked Jellyseerr request {jellyseerr_request_id} from {username}")

    # At this point, we're just tracking. The actual analysis happens
    # when Radarr/Sonarr sends the webhook after the content is added.
    # This gives us the user info early.

    return jsonify({
        'status': 'tracked',
        'request_id': media_request.id,
        'user': username,
        'user_type': user.user_type if user else 'unknown',
    }), 200


@jellyseerr_bp.route('/jellyseerr/test', methods=['POST', 'GET'])
def jellyseerr_test():
    """Test endpoint for Jellyseerr webhook configuration"""
    if request.method == 'GET':
        return jsonify({'status': 'ok', 'message': 'Jellyseerr webhook endpoint ready'}), 200

    # Log the test payload
    data = request.json
    logger.info(f"Jellyseerr test webhook received: {data}")

    return jsonify({'status': 'ok', 'message': 'Test received'}), 200
