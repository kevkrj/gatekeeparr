"""Approval model for tracking approval decisions and audit trail"""

from gatekeeper.models.base import db, TimestampMixin


class Approval(db.Model, TimestampMixin):
    """
    Audit trail for approval decisions.
    Records who approved/denied what and when.
    """
    __tablename__ = 'approvals'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('requests.id'), nullable=False, index=True)

    # Decision
    action = db.Column(db.String(20), nullable=False)  # 'approve', 'deny', 'auto_approve'
    decided_by = db.Column(db.String(255))  # Username of who clicked the button
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Context
    notes = db.Column(db.Text)
    source = db.Column(db.String(50))  # 'mattermost', 'discord', 'admin_panel', 'auto'

    # Notification tracking
    notification_sent = db.Column(db.Boolean, default=False)
    notification_sent_at = db.Column(db.DateTime)

    # Action constants
    ACTION_APPROVE = 'approve'
    ACTION_DENY = 'deny'
    ACTION_AUTO_APPROVE = 'auto_approve'

    # Relationship to the user who made the decision
    decided_by_user = db.relationship('User', foreign_keys=[decided_by_user_id])

    def to_dict(self) -> dict:
        """Convert approval to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'request_id': self.request_id,
            'action': self.action,
            'decided_by': self.decided_by,
            'notes': self.notes,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<Approval {self.action} by {self.decided_by}>'
