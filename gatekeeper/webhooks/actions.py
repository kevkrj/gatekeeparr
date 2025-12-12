"""
Action Handler

Handles callback actions from notification buttons (Mattermost, Discord, etc.)
Now uses Jellyseerr API to approve/decline requests.
"""

import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

from gatekeeper.models import db, Request, Approval
from gatekeeper.services.jellyseerr import JellyseerrClient

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
        request_id = context.get('request_id')
        title = context.get('title', 'Unknown')
        user = data.get('user_name', 'Unknown')

        # Find the request
        media_request = None
        if request_id:
            media_request = Request.query.get(request_id)

        if not media_request:
            return jsonify({'ephemeral_text': f'Request not found'}), 404

        if action == 'approve':
            return _handle_approve(media_request, title, user)
        elif action == 'deny':
            return _handle_deny(media_request, title, user)
        else:
            return jsonify({'ephemeral_text': f'Unknown action: {action}'}), 400

    except Exception as e:
        logger.error(f"Error handling action: {e}")
        return jsonify({'ephemeral_text': f'Error: {str(e)}'}), 500


def _handle_approve(media_request: Request, title: str, user: str):
    """Handle approval action - approve in Jellyseerr"""
    jellyseerr = JellyseerrClient()

    # Approve in Jellyseerr using the stored request ID
    jellyseerr_id = media_request.jellyseerr_request_id
    if not jellyseerr_id:
        logger.error(f"No Jellyseerr request ID for request {media_request.id}")
        return jsonify({'ephemeral_text': f'Error: No Jellyseerr request ID'}), 400

    success = jellyseerr.approve_request(jellyseerr_id)

    # Update request status
    if success:
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

        logger.info(f"Approved {title} by {user} (Jellyseerr #{jellyseerr_id})")

        # Format response message
        return _format_approved_message(media_request, title, user)
    else:
        return jsonify({'ephemeral_text': f'Error approving {title} in Jellyseerr'})


def _handle_deny(media_request: Request, title: str, user: str):
    """Handle deny action - decline in Jellyseerr"""
    jellyseerr = JellyseerrClient()

    # Decline in Jellyseerr
    jellyseerr_id = media_request.jellyseerr_request_id
    if not jellyseerr_id:
        logger.error(f"No Jellyseerr request ID for request {media_request.id}")
        return jsonify({'ephemeral_text': f'Error: No Jellyseerr request ID'}), 400

    success = jellyseerr.decline_request(jellyseerr_id)

    # Update request status
    if success:
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

        logger.info(f"Denied {title} by {user} (Jellyseerr #{jellyseerr_id})")

        # Format response message
        return _format_denied_message(media_request, title, user)
    else:
        return jsonify({'ephemeral_text': f'Error declining {title} in Jellyseerr'})


def _format_approved_message(media_request: Request, title: str, user: str):
    """Format the approval response for Mattermost"""
    summary = media_request.ai_summary or ''
    concerns = media_request.ai_concerns or []
    rating = media_request.ai_rating or ''
    requester = media_request.requested_by_username or ''

    if isinstance(concerns, str):
        try:
            concerns = json.loads(concerns)
        except:
            concerns = [concerns] if concerns else []

    concerns_text = "\n".join([f"• {c}" for c in concerns]) if concerns else ""
    requester_text = f"\n**Requested by:** {requester}" if requester else ""

    text = f'**Approved by {user}**\n\n_{summary}_{requester_text}'
    if concerns_text:
        text += f'\n\n**Parental Concerns:**\n{concerns_text}'

    return jsonify({
        'update': {
            'props': {
                'attachments': [{
                    'color': '#00CC00',  # Green
                    'title': f'APPROVED - {title} ({rating})',
                    'text': text,
                }]
            }
        }
    })


def _format_denied_message(media_request: Request, title: str, user: str):
    """Format the denial response for Mattermost"""
    summary = media_request.ai_summary or ''
    concerns = media_request.ai_concerns or []
    rating = media_request.ai_rating or ''
    requester = media_request.requested_by_username or ''

    if isinstance(concerns, str):
        try:
            concerns = json.loads(concerns)
        except:
            concerns = [concerns] if concerns else []

    concerns_text = "\n".join([f"• {c}" for c in concerns]) if concerns else ""
    requester_text = f"\n**Requested by:** {requester}" if requester else ""

    text = f'**Denied by {user}**\n\n_{summary}_{requester_text}'
    if concerns_text:
        text += f'\n\n**Parental Concerns:**\n{concerns_text}'

    return jsonify({
        'update': {
            'props': {
                'attachments': [{
                    'color': '#FF0000',  # Red
                    'title': f'DENIED - {title} ({rating})',
                    'text': text,
                }]
            }
        }
    })


@actions_bp.route('/action/approve/<int:request_id>', methods=['POST'])
def approve_by_id(request_id):
    """Direct approve endpoint for API/admin panel"""
    media_request = Request.query.get_or_404(request_id)
    user = request.json.get('user', 'API') if request.json else 'API'

    return _handle_approve(media_request, media_request.title, user)


@actions_bp.route('/action/deny/<int:request_id>', methods=['POST'])
def deny_by_id(request_id):
    """Direct deny endpoint for API/admin panel"""
    media_request = Request.query.get_or_404(request_id)
    user = request.json.get('user', 'API') if request.json else 'API'

    return _handle_deny(media_request, media_request.title, user)
