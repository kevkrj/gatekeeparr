"""API endpoints for approval history"""

from flask import Blueprint, request, jsonify
from gatekeeper.models import db
from gatekeeper.models.approval import Approval
from gatekeeper.models.request import Request
from gatekeeper.auth import require_auth_api, require_admin
from sqlalchemy import desc
from datetime import datetime, timedelta

approvals_bp = Blueprint('approvals', __name__, url_prefix='/api/approvals')


@approvals_bp.route('', methods=['GET'])
@require_auth_api
@require_admin
def list_approvals():
    """
    List approval history with optional filtering.

    Query params:
        action: Filter by action (approve, deny, auto_approve)
        source: Filter by source (mattermost, discord, admin_panel, auto)
        decided_by: Filter by who made the decision
        days: Only show approvals from last N days
        limit: Max results (default 50)
        offset: Pagination offset (default 0)
    """
    action = request.args.get('action')
    source = request.args.get('source')
    decided_by = request.args.get('decided_by')
    days = request.args.get('days', type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    query = Approval.query

    if action:
        query = query.filter(Approval.action == action)
    if source:
        query = query.filter(Approval.source == source)
    if decided_by:
        query = query.filter(Approval.decided_by == decided_by)
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Approval.created_at >= cutoff)

    total = query.count()
    approvals = query.order_by(desc(Approval.created_at)).offset(offset).limit(limit).all()

    # Include request info with each approval
    result = []
    for approval in approvals:
        approval_dict = approval.to_dict()
        if approval.request:
            approval_dict['request'] = {
                'id': approval.request.id,
                'title': approval.request.title,
                'media_type': approval.request.media_type,
                'ai_rating': approval.request.ai_rating,
                'requested_by': approval.request.requested_by_username
            }
        result.append(approval_dict)

    return jsonify({
        'approvals': result,
        'total': total,
        'limit': limit,
        'offset': offset
    })


@approvals_bp.route('/request/<int:request_id>', methods=['GET'])
@require_auth_api
@require_admin
def get_approvals_for_request(request_id):
    """Get all approvals for a specific request."""
    approvals = Approval.query.filter_by(request_id=request_id).order_by(desc(Approval.created_at)).all()

    return jsonify({
        'approvals': [a.to_dict() for a in approvals],
        'total': len(approvals)
    })


@approvals_bp.route('/recent', methods=['GET'])
@require_auth_api
@require_admin
def recent_approvals():
    """Get recent approval activity (last 24 hours)."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    approvals = Approval.query.filter(Approval.created_at >= cutoff).order_by(desc(Approval.created_at)).all()

    result = []
    for approval in approvals:
        approval_dict = approval.to_dict()
        if approval.request:
            approval_dict['request'] = {
                'id': approval.request.id,
                'title': approval.request.title,
                'media_type': approval.request.media_type,
            }
        result.append(approval_dict)

    return jsonify({
        'approvals': result,
        'total': len(result),
        'period': '24h'
    })
