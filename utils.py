"""
══════════════════════════════════════════════════════════════
Utility Functions
══════════════════════════════════════════════════════════════
Terminal formatting, URL validation, ID generation, and other
shared utilities used across the application.
══════════════════════════════════════════════════════════════
"""

import os
import re
import sys
import random
import string
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Section 1: Terminal Formatting
# ══════════════════════════════════════════════════════════════

def _supports_ansi() -> bool:
    """
    Detect whether the current terminal supports ANSI escape codes.

    Returns:
        True if ANSI codes will render correctly
    """
    # If output is being piped/redirected, skip ANSI
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False

    # Windows 10+ supports ANSI in modern terminals
    if os.name == 'nt':
        try:
            os.system('')  # Enables ANSI escape processing on Windows CMD
            return True
        except Exception:
            return False

    # Unix-like systems generally support ANSI
    return True


# Set formatting functions based on terminal capability
_ANSI_SUPPORTED = _supports_ansi()


def bold(text: str) -> str:
    """Apply bold formatting to text for terminal output."""
    if _ANSI_SUPPORTED:
        return f"\033[1m{text}\033[0m"
    return f"**{text}**"


def underline(text: str) -> str:
    """Apply underline formatting to text for terminal output."""
    if _ANSI_SUPPORTED:
        return f"\033[4m{text}\033[0m"
    return f"__{text}__"


def dim(text: str) -> str:
    """Apply dim/muted formatting to text for terminal output."""
    if _ANSI_SUPPORTED:
        return f"\033[2m{text}\033[0m"
    return text


def colored(text: str, color: str) -> str:
    """
    Apply color to text for terminal output.

    Supported colors: red, green, yellow, blue, magenta, cyan
    """
    if not _ANSI_SUPPORTED:
        return text

    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
    }

    code = colors.get(color.lower(), "")
    if code:
        return f"{code}{text}\033[0m"
    return text


# ══════════════════════════════════════════════════════════════
# Section 2: URL Validation
# ══════════════════════════════════════════════════════════════

# Compiled patterns for performance
_REDDIT_URL_PATTERNS = [
    re.compile(r'^https?://(www\.)?reddit\.com/r/\w+/comments/\w+', re.IGNORECASE),
    re.compile(r'^https?://old\.reddit\.com/r/\w+/comments/\w+', re.IGNORECASE),
    re.compile(r'^https?://new\.reddit\.com/r/\w+/comments/\w+', re.IGNORECASE),
    re.compile(r'^https?://redd\.it/\w+', re.IGNORECASE),
]


def validate_reddit_url(url: str) -> str:
    """
    Validate that a string is a proper Reddit post URL.

    Args:
        url: The URL string to validate

    Returns:
        The validated URL (stripped of whitespace)

    Raises:
        ValueError: If the URL is not a valid Reddit post URL
    """
    if not url:
        raise ValueError("URL cannot be empty")

    url = url.strip()

    for pattern in _REDDIT_URL_PATTERNS:
        if pattern.match(url):
            logger.debug(f"URL validated: {url}")
            return url

    raise ValueError(
        f"Invalid Reddit URL: {url}\n"
        f"Expected formats:\n"
        f"  https://www.reddit.com/r/subreddit/comments/id/title/\n"
        f"  https://old.reddit.com/r/subreddit/comments/id/title/\n"
        f"  https://redd.it/id\n"
    )


# ══════════════════════════════════════════════════════════════
# Section 3: Comment ID Generation
# ══════════════════════════════════════════════════════════════

class CommentIDGenerator:
    """
    Generates unique, hierarchy-preserving comment IDs for a thread.

    Each thread gets a random base ID. Individual comment IDs combine
    the base with the hierarchical position to create unique,
    collision-free identifiers.

    Format: {base}-{hierarchy}
    Example: A7X9K2-1.2.3

    Attributes:
        base: The random thread-level base string
    """

    def __init__(self, base_length: int = 6):
        """
        Initialize the ID generator with a random base.

        Args:
            base_length: Number of characters in the random base (4-12)
        """
        if base_length < 4 or base_length > 12:
            raise ValueError(f"base_length must be between 4 and 12, got {base_length}")

        self._base = ''.join(
            random.choices(string.ascii_uppercase + string.digits, k=base_length)
        )
        self._counter = 0

    @property
    def thread_id(self) -> str:
        """The thread-level base ID."""
        return self._base

    def generate(self, hierarchy_string: str) -> str:
        """
        Generate an ID from a hierarchy string.

        Args:
            hierarchy_string: Dot-separated hierarchy (e.g., '1.2.3')

        Returns:
            Unique comment ID (e.g., 'A7X9K2-1.2.3')
        """
        self._counter += 1
        return f"{self._base}-{hierarchy_string}"

    def generate_sequential(self) -> str:
        """
        Generate a purely sequential fallback ID.

        Returns:
            Sequential ID (e.g., 'A7X9K2-SEQ0001')
        """
        self._counter += 1
        return f"{self._base}-SEQ{self._counter:04d}"


# ══════════════════════════════════════════════════════════════
# Section 4: Time Formatting
# ══════════════════════════════════════════════════════════════

def format_timestamp(utc_timestamp: float) -> str:
    """
    Convert a UTC timestamp to a human-readable string.

    Args:
        utc_timestamp: Unix timestamp (seconds since epoch)

    Returns:
        Formatted datetime string
    """
    try:
        dt = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OSError, ValueError, OverflowError):
        return "Unknown date"


def format_relative_time(utc_timestamp: float) -> str:
    """
    Convert a UTC timestamp to a relative time string (e.g., '2 hours ago').

    Args:
        utc_timestamp: Unix timestamp (seconds since epoch)

    Returns:
        Relative time string
    """
    try:
        now = datetime.now(tz=timezone.utc)
        dt = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
        delta = now - dt

        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 2592000:
            days = seconds // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds < 31536000:
            months = seconds // 2592000
            return f"{months} month{'s' if months != 1 else ''} ago"
        else:
            years = seconds // 31536000
            return f"{years} year{'s' if years != 1 else ''} ago"
    except (OSError, ValueError, OverflowError):
        return "Unknown"


# ══════════════════════════════════════════════════════════════
# Section 5: Text Utilities
# ══════════════════════════════════════════════════════════════

def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length, adding a suffix if truncated.

    Args:
        text: The text to truncate
        max_length: Maximum number of characters
        suffix: String to append when truncated

    Returns:
        Original or truncated text
    """
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def safe_author(comment) -> str:
    """
    Safely extract the author name from a PRAW comment object.

    Args:
        comment: PRAW Comment object

    Returns:
        Author username or '[deleted]'/'[unknown]'
    """
    if comment.author is None:
        return "[deleted]"
    try:
        return comment.author.name
    except AttributeError:
        return "[unknown]"