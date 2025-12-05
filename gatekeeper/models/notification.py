"""Notification model for tracking sent notifications"""

from gatekeeper.models.base import db, TimestampMixin
import json


class Notification(db.Model, TimestampMixin):
    """
    Tracks notifications sent for requests.
    Useful for debugging and avoiding duplicate notifications.
    """
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('requests.id'), nullable=False, index=True)

    # Channel info
    channel = db.Column(db.String(50), nullable=False)  # 'mattermost', 'discord', 'webhook'
    channel_url = db.Column(db.String(500))

    # Payload
    _payload = db.Column('payload', db.Text)  # JSON of what was sent

    # Status
    status = db.Column(db.String(20), default='pending')  # 'pending', 'sent', 'failed'
    sent_at = db.Column(db.DateTime)
    error = db.Column(db.Text)

    # Response tracking
    response_code = db.Column(db.Integer)
    response_body = db.Column(db.Text)

    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'

    @property
    def payload(self) -> dict:
        """Get payload as a dictionary"""
        if self._payload:
            try:
                return json.loads(self._payload)
            except json.JSONDecodeError:
                return {}
        return {}

    @payload.setter
    def payload(self, value: dict):
        """Set payload from a dictionary"""
        self._payload = json.dumps(value) if value else None

    def to_dict(self) -> dict:
        """Convert notification to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'request_id': self.request_id,
            'channel': self.channel,
            'status': self.status,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<Notification {self.channel} ({self.status})>'
