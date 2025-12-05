"""
Action Handler

Handles callback actions from notification buttons (Mattermost, Discord, etc.)
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

from gatekeeper.models import db, Request, Approval
from gatekeeper.services.radarr import RadarrClient
from gatekeeper.services.sonarr import SonarrClient

logger = logging.getLogger(__name__)

actions_bp = Blueprint('actions', __name__)


@actions_bp.route('/action', methods=['POST'])
def handle_action():
    """
    Handle approval/deny actions from notification buttons.

    Expected payload (from Mattermost):
    {
        "context": {
            "action": "approve" | "deny",
            "media_type": "movie" | "series",
            "media_id": 123,
            "request_id": 456,
            "title": "Movie Title"
        },
        "user_name": "username_who_clicked"
    }
    """
    try:
        data = request.json
        logger.info(f"Action received: {data}")

        context = data.get('context', {})
        action = context.get('action')
        media_type = context.get('media_type')
        media_id = context.get('media_id')
        request_id = context.get('request_id')
        title = context.get('title', 'Unknown')
        user = data.get('user_name', 'Unknown')

        # Find the request
        media_request = None
        if request_id:
            media_request = Request.query.get(request_id)
        if not media_request and media_id:
            media_request = Request.query.filter_by(
                media_type=media_type,
                media_id=media_id
            ).first()

        if action == 'approve':
            return _handle_approve(media_request, media_type, media_id, title, user)
        elif action == 'deny':
            return _handle_deny(media_request, media_type, media_id, title, user)
        else:
            return jsonify({'ephemeral_text': f'Unknown action: {action}'}), 400

    except Exception as e:
        logger.error(f"Error handling action: {e}")
        return jsonify({'ephemeral_text': f'Error: {str(e)}'}), 500


def _handle_approve(media_request, media_type, media_id, title, user):
    """Handle approval action"""
    success = False

    # Re-enable monitoring
    if media_type == 'movie':
        radarr = RadarrClient()
        success = radarr.monitor(media_id)
    elif media_type == 'series':
        sonarr = SonarrClient()
        success = sonarr.monitor(media_id)

    # Update request status
    if media_request:
        media_request.status = Request.STATUS_APPROVED
        media_request.updated_at = datetime.utcnow()

        # Create approval record
        approval = Approval(
            request_id=media_request.id,
            action=Approval.ACTION_APPROVE,
            decided_by=user,
            source='mattermost',
        )
        db.session.add(approval)
        db.session.commit()

    if success:
        logger.info(f"Approved {title} by {user}")
        return jsonify({
            'update': {'message': f'✅ **{title}** approved by {user}'},
            'ephemeral_text': f'You approved {title}'
        })
    else:
        return jsonify({'ephemeral_text': f'Error approving {title}'})


def _handle_deny(media_request, media_type, media_id, title, user):
    """Handle deny action"""
    success = False

    # Delete from *arr
    if media_type == 'movie':
        radarr = RadarrClient()
        success = radarr.delete_movie(media_id, delete_files=True)
    elif media_type == 'series':
        sonarr = SonarrClient()
        success = sonarr.delete_series(media_id, delete_files=True)

    # Update request status
    if media_request:
        media_request.status = Request.STATUS_DENIED
        media_request.updated_at = datetime.utcnow()

        # Create approval record
        approval = Approval(
            request_id=media_request.id,
            action=Approval.ACTION_DENY,
            decided_by=user,
            source='mattermost',
        )
        db.session.add(approval)
        db.session.commit()

    if success:
        logger.info(f"Denied {title} by {user}")
        return jsonify({
            'update': {'message': f'❌ **{title}** denied and deleted by {user}'},
            'ephemeral_text': f'You denied {title}'
        })
    else:
        return jsonify({'ephemeral_text': f'Error deleting {title}'})


@actions_bp.route('/action/approve/<int:request_id>', methods=['POST'])
def approve_by_id(request_id):
    """Direct approve endpoint for API/admin panel"""
    media_request = Request.query.get_or_404(request_id)
    user = request.json.get('user', 'API')

    return _handle_approve(
        media_request,
        media_request.media_type,
        media_request.media_id,
        media_request.title,
        user
    )


@actions_bp.route('/action/deny/<int:request_id>', methods=['POST'])
def deny_by_id(request_id):
    """Direct deny endpoint for API/admin panel"""
    media_request = Request.query.get_or_404(request_id)
    user = request.json.get('user', 'API')

    return _handle_deny(
        media_request,
        media_request.media_type,
        media_request.media_id,
        media_request.title,
        user
    )
