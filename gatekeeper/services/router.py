"""
User Router Service

Determines how content requests should be routed based on:
- User type (kid, teen, adult, admin)
- Content rating
- User-specific settings
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from gatekeeper.models import db, User
from gatekeeper.services.jellyseerr import JellyseerrClient, JellyseerrUser
from gatekeeper.config import get_config

logger = logging.getLogger(__name__)


class RoutingDecision(Enum):
    """Possible routing decisions"""
    AUTO_APPROVE = "auto_approve"
    HOLD_FOR_APPROVAL = "hold"
    BLOCK = "block"


@dataclass
class RoutingResult:
    """Result of routing decision"""
    decision: RoutingDecision
    reason: str
    user: Optional[User] = None
    requires_notification: bool = False

    def to_dict(self) -> dict:
        return {
            'decision': self.decision.value,
            'reason': self.reason,
            'user': self.user.to_dict() if self.user else None,
            'requires_notification': self.requires_notification,
        }


class UserRouter:
    """
    Routes content requests based on user type and content rating.

    Routing rules:
    1. Admins: Always auto-approve
    2. Adults (not flagged): Always auto-approve
    3. Adults (flagged): Hold for approval
    4. Teens: Auto-approve PG-13 and below, hold R+
    5. Kids: Auto-approve PG and below, hold PG-13+
    6. Blocked ratings (NC-17, X): Always block
    """

    def __init__(self, jellyseerr_client: Optional[JellyseerrClient] = None):
        self.jellyseerr = jellyseerr_client or JellyseerrClient()
        self.config = get_config()

    # -------------------------------------------------------------------------
    # User Management
    # -------------------------------------------------------------------------

    def get_or_create_user(self, jellyseerr_user: JellyseerrUser) -> User:
        """
        Get or create a local user from Jellyseerr user info.

        Args:
            jellyseerr_user: User from Jellyseerr API

        Returns:
            Local User model instance
        """
        user = User.query.filter_by(jellyseerr_id=jellyseerr_user.id).first()

        if user:
            # Update user info
            user.username = jellyseerr_user.username or jellyseerr_user.email
            user.email = jellyseerr_user.email
            user.display_name = jellyseerr_user.display_name
            user.jellyfin_id = jellyseerr_user.jellyfin_user_id
            db.session.commit()
            return user

        # Create new user with default settings
        # New users default to 'adult' - admin should classify kids
        user = User(
            jellyseerr_id=jellyseerr_user.id,
            jellyfin_id=jellyseerr_user.jellyfin_user_id,
            username=jellyseerr_user.username or jellyseerr_user.email,
            email=jellyseerr_user.email,
            display_name=jellyseerr_user.display_name,
            user_type=User.TYPE_ADMIN if jellyseerr_user.is_admin else User.TYPE_ADULT,
            requires_approval=False,
        )
        db.session.add(user)
        db.session.commit()

        logger.info(f"Created new user: {user.username} (type: {user.user_type})")
        return user

    def sync_users_from_jellyseerr(self) -> list[User]:
        """
        Sync all users from Jellyseerr to local database.

        Returns:
            List of synced users
        """
        try:
            jellyseerr_users = self.jellyseerr.get_all_users()
            synced = []

            for js_user in jellyseerr_users:
                user = self.get_or_create_user(js_user)
                synced.append(user)

            logger.info(f"Synced {len(synced)} users from Jellyseerr")
            return synced

        except Exception as e:
            logger.error(f"Failed to sync users from Jellyseerr: {e}")
            return []

    # -------------------------------------------------------------------------
    # Routing Logic
    # -------------------------------------------------------------------------

    def is_rating_blocked(self, rating: str) -> bool:
        """Check if a rating is in the blocked list (always denied)"""
        if not rating:
            return False
        return rating.upper() in [r.upper() for r in self.config.blocked_ratings]

    def route_by_certification(
        self,
        user: Optional[User],
        certification: str,
        media_type: str = "movie"
    ) -> RoutingResult:
        """
        Route a request based on known certification.

        Args:
            user: User who made the request (None if unknown)
            certification: Known certification (e.g., 'PG', 'TV-MA')
            media_type: 'movie' or 'tv'

        Returns:
            RoutingResult with decision and reason
        """
        rating = certification.upper() if certification else "UNKNOWN"

        # Rule 1: Blocked ratings are always blocked
        if self.is_rating_blocked(rating):
            return RoutingResult(
                decision=RoutingDecision.BLOCK,
                reason=f"Rating {rating} is blocked",
                user=user,
                requires_notification=True,
            )

        # Rule 2: Unknown user - hold for approval
        if user is None:
            return RoutingResult(
                decision=RoutingDecision.HOLD_FOR_APPROVAL,
                reason="Unknown requester - held for review",
                requires_notification=True,
            )

        # Rule 3: Admins always auto-approve
        if user.is_admin():
            return RoutingResult(
                decision=RoutingDecision.AUTO_APPROVE,
                reason=f"Admin user - auto-approved ({rating})",
                user=user,
            )

        # Rule 4: Adults without approval flag - auto-approve
        if user.is_adult() and not user.requires_approval:
            return RoutingResult(
                decision=RoutingDecision.AUTO_APPROVE,
                reason=f"Adult user - auto-approved ({rating})",
                user=user,
            )

        # Rule 5: Auto-deny R-rated content for kids
        if user.is_kid() and rating in ('R', 'TV-MA'):
            return RoutingResult(
                decision=RoutingDecision.BLOCK,
                reason=f"{rating} content auto-denied for kid user",
                user=user,
                requires_notification=True,
            )

        # Rule 6: Check if rating requires approval for this user
        if user.needs_approval_for_rating(rating):
            return RoutingResult(
                decision=RoutingDecision.HOLD_FOR_APPROVAL,
                reason=f"{rating} content requires approval for {user.user_type} user",
                user=user,
                requires_notification=True,
            )

        # Rule 7: Rating is within user's allowed range
        return RoutingResult(
            decision=RoutingDecision.AUTO_APPROVE,
            reason=f"{rating} is within allowed ratings for {user.user_type}",
            user=user,
        )
