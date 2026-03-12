"""API endpoints for request management"""

from flask import Blueprint, request, jsonify
from gatekeeper.models import db
from gatekeeper.models.request import Request
from gatekeeper.models.user import User
from gatekeeper.models.approval import Approval
from gatekeeper.auth import require_auth_api, require_admin
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
@require_auth_api
@require_admin
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

    # Approve in Seerr (if the request still exists there)
    seerr_note = ''
    if req.jellyseerr_request_id:
        try:
            jellyseerr = JellyseerrClient()
            seerr_req = jellyseerr.get_request(req.jellyseerr_request_id)
            if seerr_req is None:
                seerr_note = 'Request no longer exists in Seerr; updated locally only.'
            elif not jellyseerr.approve_request(req.jellyseerr_request_id):
                return jsonify({'error': 'Failed to approve in Seerr'}), 500
        except Exception as e:
            return jsonify({'error': f'Seerr error: {str(e)}'}), 500
    else:
        seerr_note = 'No Seerr request ID; updated locally only.'

    # Update request status
    req.status = Request.STATUS_APPROVED

    # Create approval record
    approval = Approval(
        request_id=request_id,
        action='approve',
        decided_by=decided_by,
        notes=notes or seerr_note,
        source='admin_panel'
    )
    db.session.add(approval)
    db.session.commit()

    msg = f'Approved: {req.title}'
    if seerr_note:
        msg += f' ({seerr_note})'

    return jsonify({
        'success': True,
        'message': msg,
        'request': req.to_dict()
    })


@requests_bp.route('/<int:request_id>/deny', methods=['POST'])
@require_auth_api
@require_admin
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

    # Decline in Seerr (if the request still exists there)
    seerr_note = ''
    if req.jellyseerr_request_id:
        try:
            jellyseerr = JellyseerrClient()
            seerr_req = jellyseerr.get_request(req.jellyseerr_request_id)
            if seerr_req is None:
                seerr_note = 'Request no longer exists in Seerr; updated locally only.'
            elif not jellyseerr.decline_request(req.jellyseerr_request_id):
                return jsonify({'error': 'Failed to decline in Seerr'}), 500
        except Exception as e:
            return jsonify({'error': f'Seerr error: {str(e)}'}), 500
    else:
        seerr_note = 'No Seerr request ID; updated locally only.'

    # Update request status
    req.status = Request.STATUS_DENIED

    # Create approval record
    approval = Approval(
        request_id=request_id,
        action='deny',
        decided_by=decided_by,
        notes=notes or seerr_note,
        source='admin_panel'
    )
    db.session.add(approval)
    db.session.commit()

    msg = f'Denied: {req.title}'
    if seerr_note:
        msg += f' ({seerr_note})'

    return jsonify({
        'success': True,
        'message': msg,
        'request': req.to_dict()
    })


@requests_bp.route('/<int:request_id>', methods=['DELETE'])
@require_auth_api
@require_admin
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


@requests_bp.route('/sync', methods=['POST'])
@require_auth_api
@require_admin
def sync_requests():
    """
    Sync local requests with Seerr. Removes requests that no longer exist
    in Seerr, and updates status for requests that were resolved externally.
    Also cleans up duplicate pending entries for the same Seerr request.
    """
    import logging
    from gatekeeper.services.jellyseerr import JellyseerrClient
    from gatekeeper.models.notification import Notification

    logger = logging.getLogger(__name__)
    jellyseerr = JellyseerrClient()

    removed = []
    updated = []
    deduped = []

    # Get all local requests that have a Seerr request ID
    local_requests = Request.query.filter(
        Request.jellyseerr_request_id.isnot(None)
    ).order_by(Request.id).all()

    # Group by seerr ID to find duplicates
    seen_seerr_ids = {}
    for req in local_requests:
        seerr_id = req.jellyseerr_request_id
        if seerr_id not in seen_seerr_ids:
            seen_seerr_ids[seerr_id] = []
        seen_seerr_ids[seerr_id].append(req)

    # Deduplicate: keep the most recent non-pending entry, or the latest one
    for seerr_id, dupes in seen_seerr_ids.items():
        if len(dupes) <= 1:
            continue
        # Prefer non-pending records
        non_pending = [r for r in dupes if r.status != Request.STATUS_PENDING]
        keep = non_pending[-1] if non_pending else dupes[-1]
        for req in dupes:
            if req.id != keep.id:
                Approval.query.filter_by(request_id=req.id).delete()
                Notification.query.filter_by(request_id=req.id).delete()
                db.session.delete(req)
                deduped.append(f"{req.title} (id={req.id})")

    db.session.flush()

    # Check remaining requests against Seerr
    remaining = Request.query.filter(
        Request.jellyseerr_request_id.isnot(None),
        Request.status.in_([
            Request.STATUS_PENDING, Request.STATUS_HELD,
            Request.STATUS_ANALYZING
        ])
    ).all()

    seerr_status_map = {1: 'pending', 2: 'approved', 3: 'declined'}

    for req in remaining:
        try:
            seerr_req = jellyseerr.get_request(req.jellyseerr_request_id)
        except Exception as e:
            logger.warning("Failed to check seerr request %s: %s", req.jellyseerr_request_id, e)
            continue

        if seerr_req is None:
            # Request deleted from Seerr - remove locally
            Approval.query.filter_by(request_id=req.id).delete()
            Notification.query.filter_by(request_id=req.id).delete()
            db.session.delete(req)
            removed.append(f"{req.title} (seerr_id={req.jellyseerr_request_id})")
        else:
            # Check if Seerr already resolved it
            seerr_status = seerr_req.get('status')
            if seerr_status == 2 and req.status != Request.STATUS_APPROVED:
                req.status = Request.STATUS_APPROVED
                updated.append(f"{req.title} → approved")
            elif seerr_status == 3 and req.status != Request.STATUS_DENIED:
                req.status = Request.STATUS_DENIED
                updated.append(f"{req.title} → denied")

    db.session.commit()

    return jsonify({
        'success': True,
        'removed': removed,
        'updated': updated,
        'deduped': deduped,
        'summary': f"Removed {len(removed)}, updated {len(updated)}, deduped {len(deduped)}"
    })
