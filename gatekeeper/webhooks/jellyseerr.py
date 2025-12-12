"""
Jellyseerr Webhook Handler

Handles incoming webhooks from Jellyseerr and makes parental content decisions.
This is the PRIMARY decision point - all filtering happens here, before
content reaches Radarr/Sonarr.

Flow:
1. MEDIA_PENDING webhook received
2. Look up user, fetch TMDB rating
3. Route decision: approve, hold, or block
4. If approve: call Jellyseerr approve API -> flows to Radarr/Sonarr
5. If hold: run AI analysis, send MM notification, leave in pending
6. If block: call Jellyseerr decline API -> user sees "Declined"
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

from gatekeeper.models import db, Request, User
from gatekeeper.services.router import UserRouter, RoutingDecision
from gatekeeper.services.jellyseerr import JellyseerrClient
from gatekeeper.services.tmdb import get_tmdb_client
from gatekeeper.services.notifier import get_notifier
from gatekeeper.services.analyzer import get_analyzer
from gatekeeper.services.content_data import fetch_content_data

logger = logging.getLogger(__name__)

jellyseerr_bp = Blueprint('jellyseerr', __name__, url_prefix='/webhook')


def _lookup_user(username: str) -> User | None:
    """Look up user by username or jellyseerr_username"""
    return User.query.filter(
        db.or_(
            User.username.ilike(username),
            User.jellyseerr_username.ilike(username)
        )
    ).first()


def _get_or_create_request(
    jellyseerr_request_id: int,
    media_type: str,
    tmdb_id: int,
    title: str,
    username: str,
    user: User | None
) -> Request:
    """Get existing request or create new one"""
    media_request = Request.query.filter_by(
        jellyseerr_request_id=jellyseerr_request_id
    ).first()

    if not media_request:
        media_request = Request(
            jellyseerr_request_id=jellyseerr_request_id,
            media_type='movie' if media_type == 'movie' else 'series',
            tmdb_id=tmdb_id,
            title=title,
            requested_by_username=username,
            requested_at=datetime.utcnow(),
            status=Request.STATUS_PENDING,
        )
        if user:
            media_request.user_id = user.id
        db.session.add(media_request)
        db.session.commit()

    return media_request


def _run_ai_analysis(media_request: Request, rating: str, media_type: str) -> None:
    """Run AI analysis and store results on the request"""
    tmdb = get_tmdb_client()
    details = tmdb.get_details(int(media_request.tmdb_id), media_type)

    title = details.get('title', media_request.title) if details else media_request.title
    overview = details.get('overview', '') if details else ''
    year = details.get('year') if details else None

    # Fetch Common Sense Media data for better analysis
    content_info = fetch_content_data(title, media_type, year)
    content_data = content_info.to_prompt_context() if content_info else None

    # Run AI summary
    analyzer = get_analyzer()
    result = analyzer.summarize_content(
        title=title,
        overview=overview,
        rating=rating,
        media_type=media_type,
        year=year,
        content_data=content_data
    )

    # Store analysis on request
    media_request.ai_rating = rating  # Use official rating
    media_request.ai_summary = result.summary
    media_request.ai_concerns = result.concerns
    media_request.analyzed_at = result.analyzed_at
    media_request.ai_provider = result.provider
    media_request.ai_model = result.model
    media_request.analysis_duration_ms = result.duration_ms

    if content_info and content_info.age_rating:
        media_request.ai_summary = f"[{content_info.age_rating}] {result.summary}"

    db.session.commit()


@jellyseerr_bp.route('/jellyseerr', methods=['POST'])
def jellyseerr_webhook():
    """
    Handle Jellyseerr webhook events and make parental content decisions.

    For MEDIA_PENDING:
    - Admin/adult users: Auto-approve in Jellyseerr
    - Kids requesting G/PG: Auto-approve
    - Kids requesting PG-13: Hold, AI analysis, send notification
    - Kids requesting R+: Auto-decline in Jellyseerr
    """
    data = request.json
    notification_type = data.get('notification_type')

    logger.info(f"Jellyseerr webhook: {notification_type}")
    logger.debug(f"Webhook data: {data}")

    # Only process pending requests - that's where we make decisions
    if notification_type not in ('MEDIA_PENDING',):
        logger.debug(f"Ignoring notification type: {notification_type}")
        return jsonify({'status': 'ignored', 'type': notification_type}), 200

    # Extract request info - support multiple payload formats
    # Format 1: Nested structure with 'media' and 'request' objects
    # Format 2: Flat structure with all fields at top level
    # Format 3: Minimal structure with camelCase keys
    media = data.get('media', {})
    request_info = data.get('request', {})

    # Get media type - try all possible field names
    media_type = (
        media.get('media_type') or
        data.get('media_type') or
        data.get('mediaType') or
        'movie'
    )

    # Get TMDB ID - try all possible field names
    tmdb_id = (
        media.get('tmdbId') or
        data.get('tmdbId') or
        data.get('tmdb_id')
    )

    # Get request ID - try all possible field names
    jellyseerr_request_id = (
        request_info.get('request_id') or
        data.get('request_id') or
        data.get('requestId')
    )

    # Get username - try all possible field names
    username = (
        request_info.get('requestedBy_username') or
        request_info.get('requestedBy_email') or
        data.get('requestedBy_username') or
        data.get('requestedBy_email') or
        data.get('user') or
        'Unknown'
    )

    title = data.get('subject', 'Unknown')

    # Look up user
    user = _lookup_user(username)
    if user:
        logger.info(f"Found user: {user.username} ({user.user_type})")
    else:
        logger.warning(f"Unknown user: {username}")

    # Create/get request record
    media_request = _get_or_create_request(
        jellyseerr_request_id=jellyseerr_request_id,
        media_type=media_type,
        tmdb_id=tmdb_id,
        title=title,
        username=username,
        user=user
    )

    # Get TMDB rating
    tmdb = get_tmdb_client()
    rating = tmdb.get_rating(tmdb_id, media_type)
    logger.info(f"TMDB rating for {title}: {rating}")

    # If no rating found, hold for review
    if not rating:
        logger.warning(f"No TMDB rating for {title}, holding for review")
        rating = "UNKNOWN"

    # Store rating on request
    media_request.ai_rating = rating
    db.session.commit()

    # Get routing decision
    router = UserRouter()
    result = router.route_by_certification(user, rating, media_type)
    logger.info(f"Routing decision for {title}: {result.decision.value} - {result.reason}")

    # Initialize Jellyseerr client
    jellyseerr = JellyseerrClient()

    # Execute decision
    if result.decision == RoutingDecision.AUTO_APPROVE:
        # Approve in Jellyseerr - will flow to Radarr/Sonarr
        media_request.status = Request.STATUS_AUTO_APPROVED
        db.session.commit()

        if jellyseerr.approve_request(jellyseerr_request_id):
            logger.info(f"Auto-approved {title} in Jellyseerr")
            return jsonify({
                'status': 'approved',
                'request_id': media_request.id,
                'rating': rating,
                'reason': result.reason,
            }), 200
        else:
            logger.error(f"Failed to approve {title} in Jellyseerr")
            return jsonify({'status': 'error', 'message': 'Failed to approve'}), 500

    elif result.decision == RoutingDecision.BLOCK:
        # Decline in Jellyseerr - user sees "Declined"
        media_request.status = Request.STATUS_DENIED
        media_request.held_reason = result.reason
        db.session.commit()

        if jellyseerr.decline_request(jellyseerr_request_id):
            logger.info(f"Declined {title} in Jellyseerr - {result.reason}")
            return jsonify({
                'status': 'declined',
                'request_id': media_request.id,
                'rating': rating,
                'reason': result.reason,
            }), 200
        else:
            logger.error(f"Failed to decline {title} in Jellyseerr")
            return jsonify({'status': 'error', 'message': 'Failed to decline'}), 500

    else:  # HOLD_FOR_APPROVAL
        # Run AI analysis for parents
        _run_ai_analysis(media_request, rating, media_type)

        # Update status
        media_request.status = Request.STATUS_HELD
        media_request.held_reason = result.reason
        db.session.commit()

        # Send notification to parents
        notifier = get_notifier()
        notifier.notify_held(media_request)

        logger.info(f"Held {title} for approval, sent notification")
        return jsonify({
            'status': 'held',
            'request_id': media_request.id,
            'rating': rating,
            'reason': result.reason,
            'summary': media_request.ai_summary,
        }), 200


@jellyseerr_bp.route('/jellyseerr/test', methods=['POST', 'GET'])
def jellyseerr_test():
    """Test endpoint for Jellyseerr webhook configuration"""
    if request.method == 'GET':
        return jsonify({'status': 'ok', 'message': 'Jellyseerr webhook endpoint ready'}), 200

    data = request.json
    logger.info(f"Jellyseerr test webhook received: {data}")
    return jsonify({'status': 'ok', 'message': 'Test received'}), 200
