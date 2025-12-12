"""API endpoints for request management"""

from flask import Blueprint, request, jsonify
from gatekeeper.models import db
from gatekeeper.models.request import Request
from gatekeeper.models.user import User
from gatekeeper.models.approval import Approval
from sqlalchemy import desc, func
from datetime import datetime, timedelta

requests_bp = Blueprint('requests', __name__, url_prefix='/api/requests')


@requests_bp.route('', methods=['GET'])
def list_requests():
    """
    List requests with optional filtering.

    Query params:
        status: Filter by status (pending, held, approved, denied, auto_approved, error)
        media_type: Filter by media type (movie, series)
        user_id: Filter by user ID
        days: Only show requests from last N days
        limit: Max results (default 50)
        offset: Pagination offset (default 0)
    """
    # Get query params
    status = request.args.get('status')
    media_type = request.args.get('media_type')
    user_id = request.args.get('user_id', type=int)
    days = request.args.get('days', type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    # Build query
    query = Request.query

    if status:
        query = query.filter(Request.status == status)
    if media_type:
        query = query.filter(Request.media_type == media_type)
    if user_id:
        query = query.filter(Request.user_id == user_id)
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Request.created_at >= cutoff)

    # Get total count before pagination
    total = query.count()

    # Apply pagination and ordering
    requests_list = query.order_by(desc(Request.created_at)).offset(offset).limit(limit).all()

    return jsonify({
        'requests': [r.to_dict() for r in requests_list],
        'total': total,
        'limit': limit,
        'offset': offset
    })


@requests_bp.route('/held', methods=['GET'])
def list_held_requests():
    """List all requests currently held for approval."""
    held = Request.query.filter(Request.status == Request.STATUS_HELD).order_by(desc(Request.created_at)).all()
    return jsonify({
        'requests': [r.to_dict() for r in held],
        'total': len(held)
    })


@requests_bp.route('/<int:request_id>', methods=['GET'])
def get_request(request_id):
    """Get a single request with full details."""
    req = Request.query.get_or_404(request_id)

    # Include approval history
    approvals = Approval.query.filter_by(request_id=request_id).order_by(desc(Approval.created_at)).all()

    data = req.to_dict(include_analysis=True)
    data['approvals'] = [a.to_dict() for a in approvals]

    return jsonify(data)


@requests_bp.route('/<int:request_id>/approve', methods=['POST'])
def approve_request(request_id):
    """Approve a held request via Jellyseerr API."""
    from gatekeeper.services.jellyseerr import JellyseerrClient

    req = Request.query.get_or_404(request_id)

    if req.status != Request.STATUS_HELD:
        return jsonify({'error': f'Request is not held (status: {req.status})'}), 400

    # Get optional notes from request body
    data = request.get_json() or {}
    notes = data.get('notes', '')
    decided_by = data.get('decided_by', 'admin_panel')

    # Approve in Jellyseerr
    if not req.jellyseerr_request_id:
        return jsonify({'error': 'No Jellyseerr request ID'}), 400

    try:
        jellyseerr = JellyseerrClient()
        if not jellyseerr.approve_request(req.jellyseerr_request_id):
            return jsonify({'error': 'Failed to approve in Jellyseerr'}), 500
    except Exception as e:
        return jsonify({'error': f'Jellyseerr error: {str(e)}'}), 500

    # Update request status
    req.status = Request.STATUS_APPROVED

    # Create approval record
    approval = Approval(
        request_id=request_id,
        action='approve',
        decided_by=decided_by,
        notes=notes,
        source='admin_panel'
    )
    db.session.add(approval)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Approved: {req.title}',
        'request': req.to_dict()
    })


@requests_bp.route('/<int:request_id>/deny', methods=['POST'])
def deny_request(request_id):
    """Deny a held request via Jellyseerr API."""
    from gatekeeper.services.jellyseerr import JellyseerrClient

    req = Request.query.get_or_404(request_id)

    if req.status != Request.STATUS_HELD:
        return jsonify({'error': f'Request is not held (status: {req.status})'}), 400

    # Get optional notes from request body
    data = request.get_json() or {}
    notes = data.get('notes', '')
    decided_by = data.get('decided_by', 'admin_panel')

    # Decline in Jellyseerr
    if not req.jellyseerr_request_id:
        return jsonify({'error': 'No Jellyseerr request ID'}), 400

    try:
        jellyseerr = JellyseerrClient()
        if not jellyseerr.decline_request(req.jellyseerr_request_id):
            return jsonify({'error': 'Failed to decline in Jellyseerr'}), 500
    except Exception as e:
        return jsonify({'error': f'Jellyseerr error: {str(e)}'}), 500

    # Update request status
    req.status = Request.STATUS_DENIED

    # Create approval record
    approval = Approval(
        request_id=request_id,
        action='deny',
        decided_by=decided_by,
        notes=notes,
        source='admin_panel'
    )
    db.session.add(approval)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Denied: {req.title}',
        'request': req.to_dict()
    })


@requests_bp.route('/<int:request_id>', methods=['DELETE'])
def delete_request(request_id):
    """Delete a request (for cleaning up test data)."""
    from gatekeeper.models.notification import Notification

    req = Request.query.get_or_404(request_id)
    title = req.title

    # Delete associated records first
    Approval.query.filter_by(request_id=request_id).delete()
    Notification.query.filter_by(request_id=request_id).delete()

    db.session.delete(req)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Deleted: {title}'
    })
