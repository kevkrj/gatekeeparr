"""API endpoints for user management"""

from flask import Blueprint, request, jsonify
from gatekeeper.models import db
from gatekeeper.models.user import User
from gatekeeper.models.request import Request
from gatekeeper.services.router import UserRouter
from sqlalchemy import func

users_bp = Blueprint('users', __name__, url_prefix='/api/users')


@users_bp.route('', methods=['GET'])
def list_users():
    """List all users with their settings."""
    users = User.query.order_by(User.username).all()

    # Add request counts for each user
    result = []
    for user in users:
        user_dict = user.to_dict()
        user_dict['request_count'] = Request.query.filter_by(user_id=user.id).count()
        result.append(user_dict)

    return jsonify({
        'users': result,
        'total': len(result)
    })


@users_bp.route('/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get a single user with their request history."""
    user = User.query.get_or_404(user_id)

    user_dict = user.to_dict()

    # Get request stats
    user_dict['stats'] = {
        'total_requests': Request.query.filter_by(user_id=user_id).count(),
        'approved': Request.query.filter_by(user_id=user_id, status=Request.STATUS_APPROVED).count(),
        'auto_approved': Request.query.filter_by(user_id=user_id, status=Request.STATUS_AUTO_APPROVED).count(),
        'denied': Request.query.filter_by(user_id=user_id, status=Request.STATUS_DENIED).count(),
        'held': Request.query.filter_by(user_id=user_id, status=Request.STATUS_HELD).count(),
    }

    # Get recent requests
    recent = Request.query.filter_by(user_id=user_id).order_by(Request.created_at.desc()).limit(10).all()
    user_dict['recent_requests'] = [r.to_dict(include_analysis=False) for r in recent]

    return jsonify(user_dict)


@users_bp.route('/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """Update user settings."""
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Allowed fields to update
    allowed_fields = [
        'user_type', 'requires_approval', 'max_rating',
        'quota_daily', 'quota_weekly', 'quota_monthly',
        'display_name', 'jellyseerr_username'
    ]

    # Validate user_type
    valid_user_types = ['kid', 'teen', 'adult', 'admin']
    if 'user_type' in data and data['user_type'] not in valid_user_types:
        return jsonify({'error': f'Invalid user_type. Must be one of: {valid_user_types}'}), 400

    # Validate max_rating
    valid_ratings = ['G', 'PG', 'PG-13', 'R', 'NC-17', 'TV-Y', 'TV-Y7', 'TV-G', 'TV-PG', 'TV-14', 'TV-MA', None]
    if 'max_rating' in data and data['max_rating'] not in valid_ratings:
        return jsonify({'error': f'Invalid max_rating'}), 400

    # Update fields
    for field in allowed_fields:
        if field in data:
            setattr(user, field, data[field])

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Updated user: {user.username}',
        'user': user.to_dict()
    })


@users_bp.route('', methods=['POST'])
def create_user():
    """Create a new user manually."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required_fields = ['username']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Check if username already exists
    existing = User.query.filter_by(username=data['username']).first()
    if existing:
        return jsonify({'error': 'Username already exists'}), 400

    user = User(
        username=data['username'],
        email=data.get('email'),
        display_name=data.get('display_name'),
        user_type=data.get('user_type', 'adult'),
        requires_approval=data.get('requires_approval', False),
        max_rating=data.get('max_rating'),
        jellyseerr_id=data.get('jellyseerr_id'),
        jellyseerr_username=data.get('jellyseerr_username'),
        jellyfin_id=data.get('jellyfin_id'),
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Created user: {user.username}',
        'user': user.to_dict()
    }), 201


@users_bp.route('/sync', methods=['POST'])
def sync_users():
    """Sync users from Jellyseerr."""
    try:
        router = UserRouter()
        synced = router.sync_users_from_jellyseerr()
        return jsonify({
            'success': True,
            'message': f'Synced {len(synced)} users from Jellyseerr',
            'synced_count': len(synced)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to sync users: {str(e)}'}), 500


@users_bp.route('/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user (does not delete their requests)."""
    user = User.query.get_or_404(user_id)
    username = user.username

    # Don't delete, just remove - requests keep the username fallback
    db.session.delete(user)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Deleted user: {username}'
    })
