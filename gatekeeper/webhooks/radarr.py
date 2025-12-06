"""
Radarr Webhook Handler

Handles incoming webhooks from Radarr for:
- MovieAdded: New movie added to library
- Download: Movie file downloaded/imported
- Grab: Release grabbed for download
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

from gatekeeper.models import db, Request, User
from gatekeeper.services.analyzer import get_analyzer
from gatekeeper.services.router import UserRouter, RoutingDecision
from gatekeeper.services.notifier import get_notifier
from gatekeeper.services.radarr import RadarrClient

logger = logging.getLogger(__name__)

radarr_bp = Blueprint('radarr', __name__, url_prefix='/webhook')


@radarr_bp.route('/radarr', methods=['POST'])
def radarr_webhook():
    """
    Handle Radarr webhook events.

    Supported events:
    - MovieAdded: Triggers content analysis
    - Download: Triggers content analysis if not already done
    """
    data = request.json
    event_type = data.get('eventType')

    logger.info(f"Radarr webhook: {event_type}")
    logger.debug(f"Webhook data: {data}")

    # Only process relevant events
    if event_type not in ('Download', 'MovieAdded', 'Grab'):
        logger.debug(f"Ignoring event type: {event_type}")
        return jsonify({'status': 'ignored', 'event': event_type}), 200

    movie = data.get('movie', {})
    title = movie.get('title', 'Unknown')
    overview = movie.get('overview', '')
    year = movie.get('year')
    movie_id = movie.get('id')
    tmdb_id = movie.get('tmdbId')
    imdb_id = movie.get('imdbId')

    # Check if we've already processed this movie
    existing_request = Request.query.filter_by(
        media_type='movie',
        media_id=movie_id
    ).first()

    if existing_request and existing_request.is_resolved():
        logger.info(f"Movie {title} already processed: {existing_request.status}")
        return jsonify({
            'status': 'already_processed',
            'request_id': existing_request.id,
            'decision': existing_request.status
        }), 200

    # Create or update request record
    if existing_request:
        media_request = existing_request
    else:
        media_request = Request(
            media_type='movie',
            media_id=movie_id,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            title=title,
            year=year,
            overview=overview,
            routed_to='radarr',
            requested_at=datetime.utcnow(),
        )
        db.session.add(media_request)

    media_request.status = Request.STATUS_ANALYZING
    db.session.commit()

    # Try to identify the requester from Jellyseerr webhook data
    user = None
    requested_by = None

    # First check if Jellyseerr already sent us this request (by TMDB ID)
    jellyseerr_request = Request.query.filter_by(
        tmdb_id=str(tmdb_id) if tmdb_id else None,
        media_type='movie'
    ).filter(Request.requested_by_username.isnot(None)).first()

    if jellyseerr_request and jellyseerr_request.id != media_request.id:
        # Copy user info from the Jellyseerr-tracked request
        requested_by = jellyseerr_request.requested_by_username
        media_request.requested_by_username = requested_by
        media_request.jellyseerr_request_id = jellyseerr_request.jellyseerr_request_id
        logger.info(f"Linked to Jellyseerr request, requester: {requested_by}")

    # Look up user by username in our database (case-insensitive)
    if requested_by:
        user = User.query.filter(User.username.ilike(requested_by)).first()
        if user:
            media_request.user_id = user.id
            logger.info(f"Found user in database: {user.username} ({user.user_type})")

    # Fallback: Check for tags that might identify requester
    if not requested_by:
        tags = movie.get('tags', [])
        if tags:
            requested_by = f"Tag: {tags[0]}"
            media_request.requested_by_username = requested_by

    # Check if certification is already known from Radarr
    router = UserRouter()
    radarr = RadarrClient()
    certification = radarr.get_certification(movie_id)
    used_ai = False

    if certification:
        # Use known certification for routing decision
        logger.info(f"Using known certification for {title}: {certification}")
        result = router.process_request_by_certification(media_request, certification)

        # If held, get AI summary so parents know WHY content is rated this way
        if result.decision == RoutingDecision.HOLD_FOR_APPROVAL:
            logger.info(f"Content held - fetching AI summary for {title}")
            try:
                analyzer = get_analyzer()
                analysis = analyzer.analyze(title, overview, year)
                # Update request with AI insights (keep metadata rating)
                media_request.ai_summary = analysis.summary
                media_request.ai_concerns = analysis.concerns
                media_request.ai_provider = f"metadata+{analysis.provider}"
                media_request.ai_model = analysis.model
                media_request.analysis_duration_ms = analysis.duration_ms
                db.session.commit()
                used_ai = True
                logger.info(f"AI summary for {title}: {analysis.summary[:100]}...")
            except Exception as e:
                logger.warning(f"AI summary failed for {title}, using metadata only: {e}")
    else:
        # No certification available - fall back to AI analysis
        logger.info(f"No certification for {title}, using AI analysis")
        try:
            analyzer = get_analyzer()
            analysis = analyzer.analyze(title, overview, year)
            logger.info(f"AI Analysis for {title}: {analysis.rating}")
            used_ai = True
        except Exception as e:
            logger.error(f"Analysis failed for {title}: {e}")
            media_request.status = Request.STATUS_ERROR
            media_request.held_reason = f"Analysis error: {str(e)}"
            db.session.commit()
            return jsonify({'status': 'error', 'error': str(e)}), 500

        result = router.process_request(media_request, analysis)

    # Take action based on routing decision
    if result.decision == RoutingDecision.AUTO_APPROVE:
        # Ensure movie is monitored
        radarr.monitor(movie_id)
        logger.info(f"Auto-approved: {title}")

    elif result.decision == RoutingDecision.HOLD_FOR_APPROVAL:
        # Unmonitor to pause downloads
        radarr.unmonitor(movie_id)
        # Send notification
        notifier = get_notifier()
        notifier.notify_held(media_request)
        logger.info(f"Held for approval: {title}")

    elif result.decision == RoutingDecision.BLOCK:
        # Delete the movie
        radarr.delete_movie(movie_id, delete_files=True, add_exclusion=True)
        logger.info(f"Blocked and deleted: {title}")

    return jsonify({
        'status': result.decision.value,
        'request_id': media_request.id,
        'rating': media_request.ai_rating,
        'reason': result.reason,
        'source': media_request.ai_provider,
        'used_ai': used_ai,
    }), 200
