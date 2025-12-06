"""API endpoints for dashboard statistics"""

from flask import Blueprint, jsonify
from gatekeeper.models import db
from gatekeeper.models.request import Request
from gatekeeper.models.user import User
from gatekeeper.models.approval import Approval
from sqlalchemy import func, desc
from datetime import datetime, timedelta

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')


@stats_bp.route('', methods=['GET'])
def get_stats():
    """Get comprehensive dashboard statistics."""

    # Request counts by status
    status_counts = db.session.query(
        Request.status,
        func.count(Request.id)
    ).group_by(Request.status).all()

    status_dict = {status: count for status, count in status_counts}

    # Request counts by media type
    media_counts = db.session.query(
        Request.media_type,
        func.count(Request.id)
    ).group_by(Request.media_type).all()

    media_dict = {media_type: count for media_type, count in media_counts}

    # Requests by AI rating
    rating_counts = db.session.query(
        Request.ai_rating,
        func.count(Request.id)
    ).filter(Request.ai_rating.isnot(None)).group_by(Request.ai_rating).all()

    rating_dict = {rating: count for rating, count in rating_counts}

    # Average analysis time
    avg_analysis = db.session.query(
        func.avg(Request.analysis_duration_ms)
    ).filter(Request.analysis_duration_ms.isnot(None)).scalar() or 0

    # Total counts
    total_requests = Request.query.count()
    total_users = User.query.count()
    total_approvals = Approval.query.count()

    # Currently held requests
    held_count = Request.query.filter_by(status=Request.STATUS_HELD).count()

    # Requests in last 7 days
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_requests = Request.query.filter(Request.created_at >= week_ago).count()

    # Approval rate (auto-approved vs manual)
    auto_approved = status_dict.get('auto_approved', 0)
    manually_approved = status_dict.get('approved', 0)
    denied = status_dict.get('denied', 0)
    total_resolved = auto_approved + manually_approved + denied

    approval_rate = {
        'auto_approved_pct': round((auto_approved / total_resolved * 100) if total_resolved > 0 else 0, 1),
        'manually_approved_pct': round((manually_approved / total_resolved * 100) if total_resolved > 0 else 0, 1),
        'denied_pct': round((denied / total_resolved * 100) if total_resolved > 0 else 0, 1),
    }

    return jsonify({
        'totals': {
            'requests': total_requests,
            'users': total_users,
            'approvals': total_approvals,
            'held': held_count,
            'recent_7d': recent_requests
        },
        'by_status': status_dict,
        'by_media_type': media_dict,
        'by_rating': rating_dict,
        'approval_rate': approval_rate,
        'avg_analysis_ms': round(avg_analysis, 0)
    })


@stats_bp.route('/timeline', methods=['GET'])
def get_timeline():
    """Get request timeline for the last 30 days."""
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # Group by date
    daily_counts = db.session.query(
        func.date(Request.created_at).label('date'),
        func.count(Request.id).label('count')
    ).filter(
        Request.created_at >= thirty_days_ago
    ).group_by(
        func.date(Request.created_at)
    ).order_by('date').all()

    timeline = [{'date': str(date), 'count': count} for date, count in daily_counts]

    return jsonify({
        'timeline': timeline,
        'period': '30d'
    })


@stats_bp.route('/top-users', methods=['GET'])
def get_top_users():
    """Get users with most requests."""
    top_users = db.session.query(
        User.username,
        User.user_type,
        func.count(Request.id).label('request_count')
    ).join(Request, User.id == Request.user_id).group_by(
        User.id, User.username, User.user_type
    ).order_by(desc('request_count')).limit(10).all()

    result = [
        {'username': username, 'user_type': user_type, 'request_count': count}
        for username, user_type, count in top_users
    ]

    return jsonify({'top_users': result})


@stats_bp.route('/recent-activity', methods=['GET'])
def get_recent_activity():
    """Get recent activity feed (last 20 events)."""
    # Get recent requests
    recent_requests = Request.query.order_by(desc(Request.created_at)).limit(10).all()

    # Get recent approvals
    recent_approvals = Approval.query.order_by(desc(Approval.created_at)).limit(10).all()

    # Combine and sort
    activity = []

    for req in recent_requests:
        activity.append({
            'type': 'request',
            'timestamp': req.created_at.isoformat() if req.created_at else None,
            'title': req.title,
            'media_type': req.media_type,
            'status': req.status,
            'user': req.requested_by_username,
            'rating': req.ai_rating
        })

    for appr in recent_approvals:
        activity.append({
            'type': 'approval',
            'timestamp': appr.created_at.isoformat() if appr.created_at else None,
            'action': appr.action,
            'decided_by': appr.decided_by,
            'source': appr.source,
            'request_title': appr.request.title if appr.request else None
        })

    # Sort by timestamp descending
    activity.sort(key=lambda x: x['timestamp'] or '', reverse=True)

    return jsonify({'activity': activity[:20]})
