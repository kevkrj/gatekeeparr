"""Request model for tracking media request lifecycle"""

from gatekeeper.models.base import db, TimestampMixin
import json


class Request(db.Model, TimestampMixin):
    """
    Tracks the full lifecycle of a media request from Jellyseerr
    through analysis, approval, and final routing.
    """
    __tablename__ = 'requests'

    id = db.Column(db.Integer, primary_key=True)

    # External IDs
    jellyseerr_request_id = db.Column(db.Integer, index=True)
    media_type = db.Column(db.String(20), nullable=False)  # 'movie', 'series'
    media_id = db.Column(db.Integer)  # Radarr/Sonarr ID
    tmdb_id = db.Column(db.Integer, index=True)
    imdb_id = db.Column(db.String(20))

    # Media info
    title = db.Column(db.String(500), nullable=False)
    year = db.Column(db.Integer)
    overview = db.Column(db.Text)
    poster_url = db.Column(db.String(500))

    # Requester
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    requested_by_username = db.Column(db.String(255))  # Fallback if user not in DB
    requested_at = db.Column(db.DateTime)

    # AI Analysis results
    ai_rating = db.Column(db.String(20))  # Claude's determined rating
    ai_summary = db.Column(db.Text)
    _ai_concerns = db.Column('ai_concerns', db.Text)  # JSON array stored as text
    analyzed_at = db.Column(db.DateTime)
    ai_provider = db.Column(db.String(50))  # Which AI analyzed this
    ai_model = db.Column(db.String(100))

    # Status tracking
    status = db.Column(db.String(30), default='pending', index=True)
    # Statuses: pending, analyzing, held, approved, denied, auto_approved, error

    # Routing info
    routed_to = db.Column(db.String(20))  # 'radarr', 'sonarr'
    held_reason = db.Column(db.String(255))

    # Timing metrics (for admin panel)
    analysis_duration_ms = db.Column(db.Integer)
    total_duration_ms = db.Column(db.Integer)

    # Relationships
    approvals = db.relationship('Approval', backref='request', lazy='dynamic')
    notifications = db.relationship('Notification', backref='request', lazy='dynamic')

    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_ANALYZING = 'analyzing'
    STATUS_HELD = 'held'
    STATUS_APPROVED = 'approved'
    STATUS_DENIED = 'denied'
    STATUS_AUTO_APPROVED = 'auto_approved'
    STATUS_ERROR = 'error'

    @property
    def ai_concerns(self) -> list:
        """Get AI concerns as a list"""
        if self._ai_concerns:
            try:
                return json.loads(self._ai_concerns)
            except json.JSONDecodeError:
                return []
        return []

    @ai_concerns.setter
    def ai_concerns(self, value: list):
        """Set AI concerns from a list"""
        self._ai_concerns = json.dumps(value) if value else None

    def to_dict(self, include_analysis: bool = True) -> dict:
        """Convert request to dictionary for JSON serialization"""
        data = {
            'id': self.id,
            'jellyseerr_request_id': self.jellyseerr_request_id,
            'media_type': self.media_type,
            'media_id': self.media_id,
            'tmdb_id': self.tmdb_id,
            'title': self.title,
            'year': self.year,
            'poster_url': self.poster_url,
            'status': self.status,
            'requested_by': self.requested_by_username,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_analysis:
            data.update({
                'ai_rating': self.ai_rating,
                'ai_summary': self.ai_summary,
                'ai_concerns': self.ai_concerns,
                'analyzed_at': self.analyzed_at.isoformat() if self.analyzed_at else None,
                'ai_provider': self.ai_provider,
                'held_reason': self.held_reason,
            })

        if self.user:
            data['user'] = {
                'id': self.user.id,
                'username': self.user.username,
                'user_type': self.user.user_type,
            }

        return data

    def __repr__(self):
        return f'<Request {self.title} ({self.status})>'
