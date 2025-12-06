"""
Sonarr Webhook Handler

Handles incoming webhooks from Sonarr for:
- SeriesAdd: New series added to library
- Download: Episode file downloaded/imported
- Grab: Release grabbed for download
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

from gatekeeper.models import db, Request
from gatekeeper.services.analyzer import get_analyzer
from gatekeeper.services.router import UserRouter, RoutingDecision
from gatekeeper.services.notifier import get_notifier
from gatekeeper.services.sonarr import SonarrClient

logger = logging.getLogger(__name__)

sonarr_bp = Blueprint('sonarr', __name__, url_prefix='/webhook')


@sonarr_bp.route('/sonarr', methods=['POST'])
def sonarr_webhook():
    """
    Handle Sonarr webhook events.

    Supported events:
    - SeriesAdd: Triggers content analysis
    - Download: Triggers content analysis if not already done
    """
    data = request.json
    event_type = data.get('eventType')

    logger.info(f"Sonarr webhook: {event_type}")
    logger.debug(f"Webhook data: {data}")

    # Only process relevant events
    if event_type not in ('Download', 'SeriesAdd', 'Grab'):
        logger.debug(f"Ignoring event type: {event_type}")
        return jsonify({'status': 'ignored', 'event': event_type}), 200

    series = data.get('series', {})
    title = series.get('title', 'Unknown')
    overview = series.get('overview', '')
    year = series.get('year')
    series_id = series.get('id')
    tvdb_id = series.get('tvdbId')
    imdb_id = series.get('imdbId')

    # Check if we've already processed this series
    existing_request = Request.query.filter_by(
        media_type='series',
        media_id=series_id
    ).first()

    if existing_request and existing_request.is_resolved():
        logger.info(f"Series {title} already processed: {existing_request.status}")
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
            media_type='series',
            media_id=series_id,
            tmdb_id=tvdb_id,  # Note: Sonarr uses TVDB, storing in tmdb_id field for now
            imdb_id=imdb_id,
            title=title,
            year=year,
            overview=overview,
            routed_to='sonarr',
            requested_at=datetime.utcnow(),
        )
        db.session.add(media_request)

    media_request.status = Request.STATUS_ANALYZING
    db.session.commit()

    # Try to identify the requester
    requested_by = None
    tags = series.get('tags', [])
    if tags:
        requested_by = f"Tag: {tags[0]}"
        media_request.requested_by_username = requested_by

    # Check if certification is already known from Sonarr
    router = UserRouter()
    sonarr = SonarrClient()
    certification = sonarr.get_certification(series_id)
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
        # Ensure series is monitored and trigger search
        sonarr.monitor(series_id)
        sonarr.search_series(series_id)
        logger.info(f"Auto-approved and searching: {title}")

    elif result.decision == RoutingDecision.HOLD_FOR_APPROVAL:
        # Unmonitor to pause downloads
        sonarr.unmonitor(series_id)
        # Send notification
        notifier = get_notifier()
        notifier.notify_held(media_request)
        logger.info(f"Held for approval: {title}")

    elif result.decision == RoutingDecision.BLOCK:
        # Delete the series
        sonarr.delete_series(series_id, delete_files=True, add_exclusion=True)
        logger.info(f"Blocked and deleted: {title}")

    return jsonify({
        'status': result.decision.value,
        'request_id': media_request.id,
        'rating': media_request.ai_rating,
        'reason': result.reason,
        'source': media_request.ai_provider,
        'used_ai': used_ai,
    }), 200
