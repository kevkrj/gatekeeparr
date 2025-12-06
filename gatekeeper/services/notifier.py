"""
Pluggable Notification System

Supports multiple notification channels:
- Mattermost (with interactive buttons)
- Discord (with components)
- Generic webhooks (JSON POST)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

from gatekeeper.models import db, Request, Notification
from gatekeeper.services.analyzer import AnalysisResult
from gatekeeper.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class NotificationPayload:
    """Standard notification payload"""
    title: str
    rating: str
    summary: str
    concerns: list[str]
    media_type: str
    media_id: int
    request_id: int
    requested_by: Optional[str] = None
    poster_url: Optional[str] = None


class NotificationChannel(ABC):
    """Abstract base class for notification channels"""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Return channel name"""
        pass

    @abstractmethod
    def send(self, payload: NotificationPayload, callback_url: str) -> bool:
        """
        Send notification.

        Args:
            payload: Notification payload
            callback_url: URL for approval/deny callbacks

        Returns:
            True if sent successfully
        """
        pass


class MattermostChannel(NotificationChannel):
    """Mattermost notification channel with interactive buttons"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    @property
    def channel_name(self) -> str:
        return "mattermost"

    def send(self, payload: NotificationPayload, callback_url: str) -> bool:
        concerns_text = "\n".join([f"• {c}" for c in payload.concerns]) if payload.concerns else "• None identified"
        requester_text = f"\n**Requested by:** {payload.requested_by}" if payload.requested_by else ""

        message = {
            "attachments": [{
                "fallback": f"Content Review: {payload.title} ({payload.rating})",
                "color": self._get_color(payload.rating),
                "title": f"⚠️ {payload.title} ({payload.rating})",
                "text": f"_{payload.summary}_{requester_text}\n\n**Parental Concerns:**\n{concerns_text}",
                "actions": [
                    {
                        "id": "approve",
                        "name": "✅ Approve",
                        "integration": {
                            "url": f"{callback_url}/action",
                            "context": {
                                "action": "approve",
                                "media_type": payload.media_type,
                                "media_id": payload.media_id,
                                "request_id": payload.request_id,
                                "title": payload.title
                            }
                        }
                    },
                    {
                        "id": "deny",
                        "name": "❌ Deny & Delete",
                        "style": "danger",
                        "integration": {
                            "url": f"{callback_url}/action",
                            "context": {
                                "action": "deny",
                                "media_type": payload.media_type,
                                "media_id": payload.media_id,
                                "request_id": payload.request_id,
                                "title": payload.title
                            }
                        }
                    }
                ]
            }]
        }

        try:
            response = requests.post(self.webhook_url, json=message, timeout=30)
            response.raise_for_status()
            logger.info(f"Sent Mattermost notification for {payload.title}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Mattermost notification: {e}")
            return False

    def _get_color(self, rating: str) -> str:
        """Get color based on rating severity"""
        rating = rating.upper() if rating else ""
        if rating in ("NC-17", "X", "XXX", "TV-MA"):
            return "#FF0000"  # Red
        elif rating in ("R",):
            return "#FF6600"  # Orange
        elif rating in ("PG-13", "TV-14"):
            return "#FFCC00"  # Yellow
        return "#00CC00"  # Green


class DiscordChannel(NotificationChannel):
    """Discord notification channel with components"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    @property
    def channel_name(self) -> str:
        return "discord"

    def send(self, payload: NotificationPayload, callback_url: str) -> bool:
        concerns_text = "\n".join([f"• {c}" for c in payload.concerns]) if payload.concerns else "• None identified"
        requester_text = f"\n**Requested by:** {payload.requested_by}" if payload.requested_by else ""

        message = {
            "embeds": [{
                "title": f"⚠️ Content Review: {payload.title}",
                "description": f"**Rating:** {payload.rating}\n\n{payload.summary}{requester_text}",
                "color": self._get_color_int(payload.rating),
                "fields": [
                    {
                        "name": "Parental Concerns",
                        "value": concerns_text,
                        "inline": False
                    }
                ],
                "footer": {
                    "text": f"Request ID: {payload.request_id} | {payload.media_type.title()}"
                },
                "thumbnail": {"url": payload.poster_url} if payload.poster_url else None
            }],
            "components": [
                {
                    "type": 1,  # Action row
                    "components": [
                        {
                            "type": 2,  # Button
                            "style": 3,  # Success (green)
                            "label": "Approve",
                            "custom_id": f"approve_{payload.request_id}",
                            "emoji": {"name": "✅"}
                        },
                        {
                            "type": 2,  # Button
                            "style": 4,  # Danger (red)
                            "label": "Deny & Delete",
                            "custom_id": f"deny_{payload.request_id}",
                            "emoji": {"name": "❌"}
                        }
                    ]
                }
            ]
        }

        # Note: Discord webhooks don't support interactive buttons
        # This is for illustration - real Discord bot integration needed for buttons
        # Removing components for basic webhook
        del message["components"]

        try:
            response = requests.post(self.webhook_url, json=message, timeout=30)
            response.raise_for_status()
            logger.info(f"Sent Discord notification for {payload.title}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False

    def _get_color_int(self, rating: str) -> int:
        """Get Discord color integer based on rating"""
        rating = rating.upper() if rating else ""
        if rating in ("NC-17", "X", "XXX", "TV-MA"):
            return 0xFF0000  # Red
        elif rating in ("R",):
            return 0xFF6600  # Orange
        elif rating in ("PG-13", "TV-14"):
            return 0xFFCC00  # Yellow
        return 0x00CC00  # Green


class GenericWebhookChannel(NotificationChannel):
    """Generic webhook channel - POSTs JSON to any URL"""

    def __init__(self, webhook_url: str, name: str = "webhook"):
        self.webhook_url = webhook_url
        self._name = name

    @property
    def channel_name(self) -> str:
        return self._name

    def send(self, payload: NotificationPayload, callback_url: str) -> bool:
        message = {
            "event": "content_held",
            "title": payload.title,
            "rating": payload.rating,
            "summary": payload.summary,
            "concerns": payload.concerns,
            "media_type": payload.media_type,
            "media_id": payload.media_id,
            "request_id": payload.request_id,
            "requested_by": payload.requested_by,
            "poster_url": payload.poster_url,
            "callback_url": callback_url,
            "approve_url": f"{callback_url}/action",
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=message,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Sent webhook notification to {self.webhook_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return False


class Notifier:
    """
    Main notification service that manages multiple channels.
    """

    def __init__(self, channels: Optional[list[NotificationChannel]] = None):
        """
        Initialize notifier with channels.

        Args:
            channels: List of notification channels. If None, initializes from config.
        """
        if channels is not None:
            self.channels = channels
        else:
            self.channels = self._init_channels_from_config()

    def _init_channels_from_config(self) -> list[NotificationChannel]:
        """Initialize channels from application config"""
        config = get_config()
        channels = []

        if config.notifications.mattermost_webhook:
            channels.append(MattermostChannel(config.notifications.mattermost_webhook))

        if config.notifications.discord_webhook:
            channels.append(DiscordChannel(config.notifications.discord_webhook))

        for i, url in enumerate(config.notifications.generic_webhooks):
            if url and url.strip():
                channels.append(GenericWebhookChannel(url.strip(), f"webhook_{i}"))

        return channels

    def notify(
        self,
        request: Request,
        analysis: AnalysisResult,
    ) -> list[Notification]:
        """
        Send notifications for a held request to all configured channels.

        Args:
            request: The held request
            analysis: AI analysis result

        Returns:
            List of Notification records
        """
        config = get_config()
        callback_url = config.external_url.rstrip('/')

        payload = NotificationPayload(
            title=request.title,
            rating=analysis.rating,
            summary=analysis.summary,
            concerns=analysis.concerns,
            media_type=request.media_type,
            media_id=request.media_id,
            request_id=request.id,
            requested_by=request.requested_by_username,
            poster_url=request.poster_url,
        )

        notifications = []

        for channel in self.channels:
            notification = Notification(
                request_id=request.id,
                channel=channel.channel_name,
                channel_url=getattr(channel, 'webhook_url', None),
            )
            notification.payload = payload.__dict__

            try:
                success = channel.send(payload, callback_url)
                if success:
                    notification.status = Notification.STATUS_SENT
                    notification.sent_at = datetime.utcnow()
                else:
                    notification.status = Notification.STATUS_FAILED
                    notification.error = "Send returned False"
            except Exception as e:
                notification.status = Notification.STATUS_FAILED
                notification.error = str(e)
                logger.error(f"Notification to {channel.channel_name} failed: {e}")

            db.session.add(notification)
            notifications.append(notification)

        db.session.commit()
        return notifications

    def notify_held(
        self,
        request: Request,
    ) -> list[Notification]:
        """
        Send notifications for a held request using stored request data.

        This is used when routing by certification (no AnalysisResult object).

        Args:
            request: The held request (must have ai_rating and ai_summary set)

        Returns:
            List of Notification records
        """
        config = get_config()
        callback_url = config.external_url.rstrip('/')

        # Parse concerns from request if stored as JSON string
        concerns = request.ai_concerns if request.ai_concerns else []
        if isinstance(concerns, str):
            try:
                import json
                concerns = json.loads(concerns)
            except (json.JSONDecodeError, TypeError):
                concerns = [concerns] if concerns else []

        payload = NotificationPayload(
            title=request.title,
            rating=request.ai_rating,
            summary=request.ai_summary or f"Rating: {request.ai_rating}",
            concerns=concerns,
            media_type=request.media_type,
            media_id=request.media_id,
            request_id=request.id,
            requested_by=request.requested_by_username,
            poster_url=request.poster_url,
        )

        notifications = []

        for channel in self.channels:
            notification = Notification(
                request_id=request.id,
                channel=channel.channel_name,
                channel_url=getattr(channel, 'webhook_url', None),
            )
            notification.payload = payload.__dict__

            try:
                success = channel.send(payload, callback_url)
                if success:
                    notification.status = Notification.STATUS_SENT
                    notification.sent_at = datetime.utcnow()
                else:
                    notification.status = Notification.STATUS_FAILED
                    notification.error = "Send returned False"
            except Exception as e:
                notification.status = Notification.STATUS_FAILED
                notification.error = str(e)
                logger.error(f"Notification to {channel.channel_name} failed: {e}")

            db.session.add(notification)
            notifications.append(notification)

        db.session.commit()
        return notifications

    def add_channel(self, channel: NotificationChannel):
        """Add a notification channel"""
        self.channels.append(channel)

    def remove_channel(self, channel_name: str):
        """Remove a notification channel by name"""
        self.channels = [c for c in self.channels if c.channel_name != channel_name]


# Global notifier instance
_notifier: Optional[Notifier] = None


def get_notifier() -> Notifier:
    """Get or create the global notifier instance"""
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier


def reset_notifier():
    """Reset the global notifier (for testing or config changes)"""
    global _notifier
    _notifier = None
