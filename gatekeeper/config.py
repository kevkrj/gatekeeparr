"""Configuration management for Gatekeeper"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AIConfig:
    """AI provider configuration"""
    provider: str = "claude"  # claude, ollama, openai, grok
    api_key: Optional[str] = None
    base_url: Optional[str] = None  # For Ollama or custom endpoints
    model: Optional[str] = None  # Model override



@dataclass
class JellyseerrConfig:
    """Jellyseerr connection configuration"""
    url: str = "http://localhost:5055"
    api_key: Optional[str] = None


@dataclass
class RadarrConfig:
    """Radarr connection configuration"""
    url: str = "http://localhost:7878"
    api_key: Optional[str] = None


@dataclass
class SonarrConfig:
    """Sonarr connection configuration"""
    url: str = "http://localhost:8989"
    api_key: Optional[str] = None


@dataclass
class TMDBConfig:
    """TMDB API configuration for direct rating lookups"""
    api_key: Optional[str] = None
    base_url: str = "https://api.themoviedb.org/3"


@dataclass
class JellyfinConfig:
    """Jellyfin connection configuration"""
    url: str = "http://localhost:8096"
    api_key: Optional[str] = None
    kids_collection_id: Optional[str] = None


@dataclass
class NotificationConfig:
    """Notification channel configuration"""
    mattermost_webhook: Optional[str] = None
    discord_webhook: Optional[str] = None
    generic_webhooks: list = field(default_factory=list)  # List of webhook URLs


@dataclass
class Config:
    """Main application configuration"""
    # Server
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "sqlite:///gatekeeper.db"

    # External URL for callbacks (Mattermost buttons, etc.)
    external_url: str = "http://localhost:5000"

    # Services
    ai: AIConfig = field(default_factory=AIConfig)
    jellyseerr: JellyseerrConfig = field(default_factory=JellyseerrConfig)
    jellyfin: JellyfinConfig = field(default_factory=JellyfinConfig)
    radarr: RadarrConfig = field(default_factory=RadarrConfig)
    sonarr: SonarrConfig = field(default_factory=SonarrConfig)
    tmdb: TMDBConfig = field(default_factory=TMDBConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

    # Content filtering defaults
    restricted_movie_ratings: list = field(default_factory=lambda: ["PG-13", "R", "NC-17"])
    restricted_tv_ratings: list = field(default_factory=lambda: ["TV-14", "TV-MA"])
    blocked_ratings: list = field(default_factory=lambda: ["NC-17", "X", "XXX", "NR"])  # Always block

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        return cls(
            host=os.getenv("GATEKEEPER_HOST", "0.0.0.0"),
            port=int(os.getenv("GATEKEEPER_PORT", "5000")),
            debug=os.getenv("GATEKEEPER_DEBUG", "").lower() == "true",
            secret_key=os.getenv("GATEKEEPER_SECRET_KEY", "change-me-in-production"),
            database_url=os.getenv("DATABASE_URL", "sqlite:///gatekeeper.db"),
            external_url=os.getenv("GATEKEEPER_URL", "http://localhost:5000"),
            ai=AIConfig(
                provider=os.getenv("AI_PROVIDER", "claude"),
                api_key=os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"),
                base_url=os.getenv("AI_BASE_URL"),
                model=os.getenv("AI_MODEL"),
            ),
            jellyseerr=JellyseerrConfig(
                url=os.getenv("JELLYSEERR_URL", "http://localhost:5055"),
                api_key=os.getenv("JELLYSEERR_API_KEY"),
            ),
            jellyfin=JellyfinConfig(
                url=os.getenv("JELLYFIN_URL", "http://localhost:8096"),
                api_key=os.getenv("JELLYFIN_API_KEY"),
                kids_collection_id=os.getenv("JELLYFIN_KIDS_COLLECTION_ID"),
            ),
            radarr=RadarrConfig(
                url=os.getenv("RADARR_URL", "http://localhost:7878"),
                api_key=os.getenv("RADARR_API_KEY"),
            ),
            sonarr=SonarrConfig(
                url=os.getenv("SONARR_URL", "http://localhost:8989"),
                api_key=os.getenv("SONARR_API_KEY"),
            ),
            tmdb=TMDBConfig(
                api_key=os.getenv("TMDB_API_KEY"),
            ),
            notifications=NotificationConfig(
                mattermost_webhook=os.getenv("MATTERMOST_WEBHOOK"),
                discord_webhook=os.getenv("DISCORD_WEBHOOK"),
                generic_webhooks=os.getenv("GENERIC_WEBHOOKS", "").split(",") if os.getenv("GENERIC_WEBHOOKS") else [],
            ),
        )


# Global config instance
config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global config instance"""
    global config
    if config is None:
        config = Config.from_env()
    return config


def set_config(new_config: Config) -> None:
    """Set the global config instance (useful for testing)"""
    global config
    config = new_config
