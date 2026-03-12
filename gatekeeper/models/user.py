"""User model for tracking requesters and their permissions"""

from gatekeeper.models.base import db, TimestampMixin


class User(db.Model, TimestampMixin):
    """
    User profiles mapped from Jellyseerr.
    Determines routing behavior for content requests.
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    jellyseerr_id = db.Column(db.Integer, unique=True, index=True)
    jellyseerr_username = db.Column(db.String(255), index=True)  # Username in Jellyseerr (may differ from local)
    jellyfin_id = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))
    display_name = db.Column(db.String(255))

    # User classification
    user_type = db.Column(db.String(20), default='adult')  # 'kid', 'teen', 'adult', 'admin'

    # Content filtering
    requires_approval = db.Column(db.Boolean, default=False)
    max_rating = db.Column(db.String(10))  # 'G', 'PG', 'PG-13', 'R', NULL (no limit)

    # Quotas (NULL = unlimited)
    quota_daily = db.Column(db.Integer)
    quota_weekly = db.Column(db.Integer)
    quota_monthly = db.Column(db.Integer)  # Monthly movie request limit
    quota_monthly_tv = db.Column(db.Integer)  # Monthly TV series request limit

    # Relationships
    requests = db.relationship('Request', backref='user', lazy='dynamic')

    # User type constants
    TYPE_KID = 'kid'
    TYPE_TEEN = 'teen'
    TYPE_ADULT = 'adult'
    TYPE_ADMIN = 'admin'

    # Rating hierarchy for comparison
    RATING_ORDER = {
        'G': 0, 'TV-Y': 0, 'TV-Y7': 1,
        'PG': 2, 'TV-G': 2, 'TV-PG': 3,
        'PG-13': 4, 'TV-14': 4,
        'R': 5, 'TV-MA': 5,
        'NC-17': 6, 'X': 7, 'XXX': 8
    }

    def is_kid(self) -> bool:
        """Check if user is classified as a kid"""
        return self.user_type == self.TYPE_KID

    def is_teen(self) -> bool:
        """Check if user is classified as a teen"""
        return self.user_type == self.TYPE_TEEN

    def is_adult(self) -> bool:
        """Check if user is classified as an adult or admin"""
        return self.user_type in (self.TYPE_ADULT, self.TYPE_ADMIN)

    def is_admin(self) -> bool:
        """Check if user has admin privileges"""
        return self.user_type == self.TYPE_ADMIN

    def needs_approval_for_rating(self, rating: str) -> bool:
        """
        Check if this user needs approval for content with the given rating.
        Adults never need approval. Kids/teens need approval for content
        above their max_rating threshold.
        """
        if self.is_admin():
            return False

        if self.is_adult() and not self.requires_approval:
            return False

        if not self.max_rating:
            # No max rating set, use defaults based on user type
            # Kids auto-approve up to TV-PG, hold PG-13/TV-14, block R/TV-MA
            if self.is_kid():
                max_allowed = 'TV-PG'
            elif self.is_teen():
                max_allowed = 'PG-13'
            else:
                return self.requires_approval
        else:
            max_allowed = self.max_rating

        # Compare ratings
        rating_value = self.RATING_ORDER.get(rating.upper(), 99)
        max_value = self.RATING_ORDER.get(max_allowed.upper(), 99)

        return rating_value > max_value

    def get_monthly_request_count(self, media_type: str) -> int:
        """Count approved/auto-approved requests this month for a media type."""
        from datetime import datetime
        from gatekeeper.models.request import Request
        now = datetime.utcnow()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return self.requests.filter(
            Request.media_type == media_type,
            Request.status.in_(('approved', 'auto_approved')),
            Request.requested_at >= start_of_month,
        ).count()

    def check_quota(self, media_type: str) -> tuple[bool, str]:
        """
        Check if user is within their monthly quota for the given media type.

        Returns:
            (within_quota, reason) - True if allowed, False if over quota
        """
        if media_type == 'movie' and self.quota_monthly is not None:
            count = self.get_monthly_request_count('movie')
            if count >= self.quota_monthly:
                return False, f"Monthly movie quota reached ({count}/{self.quota_monthly})"
        elif media_type == 'tv' and self.quota_monthly_tv is not None:
            count = self.get_monthly_request_count('tv')
            if count >= self.quota_monthly_tv:
                return False, f"Monthly TV quota reached ({count}/{self.quota_monthly_tv})"
        return True, ""

    def to_dict(self) -> dict:
        """Convert user to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'jellyseerr_id': self.jellyseerr_id,
            'jellyseerr_username': self.jellyseerr_username,
            'username': self.username,
            'email': self.email,
            'display_name': self.display_name,
            'user_type': self.user_type,
            'requires_approval': self.requires_approval,
            'max_rating': self.max_rating,
            'quota_daily': self.quota_daily,
            'quota_monthly': self.quota_monthly,
            'quota_monthly_tv': self.quota_monthly_tv,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<User {self.username} ({self.user_type})>'
