"""
══════════════════════════════════════════════════════════════
Configuration Management
══════════════════════════════════════════════════════════════
Loads and validates configuration from environment variables.
Provides a single source of truth for all application settings.
══════════════════════════════════════════════════════════════
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Configuration Data Classes
# ══════════════════════════════════════════════════════════════

@dataclass
class RedditCredentials:
    """Reddit API authentication credentials."""
    client_id: str
    client_secret: str
    user_agent: str = "reddit_explorer/1.0"
    username: Optional[str] = None

    def validate(self):
        """Validate that required credentials are present and non-empty."""
        errors = []

        if not self.client_id or self.client_id == "your_client_id_here":
            errors.append("REDDIT_CLIENT_ID")
        if not self.client_secret or self.client_secret == "your_client_secret_here":
            errors.append("REDDIT_CLIENT_SECRET")

        if errors:
            raise EnvironmentError(
                f"Missing or invalid Reddit API credentials: {', '.join(errors)}\n"
                f"\n"
                f"To fix this:\n"
                f"  1. Copy .env.example to .env\n"
                f"  2. Fill in your Reddit API credentials\n"
                f"  3. Get credentials at https://www.reddit.com/prefs/apps/\n"
            )

        return True


@dataclass
class ScraperConfig:
    """Configuration for the scraping behavior."""
    max_depth: int = 10
    min_score: Optional[int] = None
    comment_sort: str = "best"
    more_comments_limit: int = 0
    id_base_length: int = 6
    skip_deleted: bool = False
    max_body_length: Optional[int] = None

    def validate(self):
        """Validate scraper configuration values."""
        if self.max_depth < 1 or self.max_depth > 50:
            raise ValueError(f"max_depth must be between 1 and 50, got {self.max_depth}")
        if self.comment_sort not in ("best", "top", "new", "controversial", "old", "qa"):
            raise ValueError(f"Invalid comment_sort: {self.comment_sort}")
        if self.id_base_length < 4 or self.id_base_length > 12:
            raise ValueError(f"id_base_length must be between 4 and 12, got {self.id_base_length}")
        return True


@dataclass
class ServerConfig:
    """Configuration for the Flask server."""
    port: int = 5000
    debug: bool = False
    rate_limit: str = "10 per minute"


@dataclass
class AppConfig:
    """Top-level application configuration."""
    credentials: RedditCredentials = field(default_factory=RedditCredentials)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


# ══════════════════════════════════════════════════════════════
# Configuration Loading
# ══════════════════════════════════════════════════════════════

def load_config() -> AppConfig:
    """
    Load application configuration from environment variables.

    Returns:
        AppConfig with all settings populated

    Raises:
        EnvironmentError: If required credentials are missing
    """
    credentials = RedditCredentials(
        client_id=os.getenv("REDDIT_CLIENT_ID", ""),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        user_agent=os.getenv("REDDIT_USER_AGENT", "reddit_explorer/1.0"),
        username=os.getenv("REDDIT_USERNAME"),
    )

    server = ServerConfig(
        port=int(os.getenv("SERVER_PORT", "5000")),
        debug=os.getenv("SERVER_DEBUG", "false").lower() in ("true", "1", "yes"),
    )

    config = AppConfig(
        credentials=credentials,
        scraper=ScraperConfig(),
        server=server,
    )

    logger.info("Configuration loaded successfully")
    return config