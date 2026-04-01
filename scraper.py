"""
══════════════════════════════════════════════════════════════
Reddit Scraper — Core Logic
══════════════════════════════════════════════════════════════
Handles all Reddit API interaction, comment tree construction,
analytics generation, and data export. This module contains
NO printing or display logic — it only produces structured data.
══════════════════════════════════════════════════════════════
"""

import json
import csv
import logging
from typing import Optional, Any

import praw
from praw.models import MoreComments
from praw.exceptions import PRAWException

from config import RedditCredentials, ScraperConfig, AppConfig
from utils import (
    safe_author,
    validate_reddit_url,
    CommentIDGenerator,
    format_timestamp,
    format_relative_time,
    truncate_text,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Section 1: Reddit Connection
# ══════════════════════════════════════════════════════════════

def create_reddit_instance(credentials: RedditCredentials) -> praw.Reddit:
    """
    Create and validate a PRAW Reddit instance.

    Args:
        credentials: RedditCredentials with API keys

    Returns:
        Authenticated praw.Reddit instance

    Raises:
        EnvironmentError: If credentials are invalid
        ConnectionError: If Reddit API is unreachable
    """
    credentials.validate()

    try:
        reddit = praw.Reddit(
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            user_agent=credentials.user_agent,
            username=credentials.username,
        )

        # Test the connection by accessing a lightweight attribute
        _ = reddit.read_only
        logger.info("Reddit API connection established (read-only mode)")
        return reddit

    except PRAWException as e:
        raise ConnectionError(f"Failed to connect to Reddit API: {e}")
    except Exception as e:
        raise ConnectionError(
            f"Unexpected error connecting to Reddit: {e}\n"
            f"Check your internet connection and credentials."
        )


# ══════════════════════════════════════════════════════════════
# Section 2: Post Fetching
# ══════════════════════════════════════════════════════════════

def fetch_post(reddit: praw.Reddit, url: str, config: ScraperConfig) -> praw.models.Submission:
    """
    Fetch a Reddit post and expand its comment tree.

    Args:
        reddit: Authenticated PRAW Reddit instance
        url: Validated Reddit post URL
        config: Scraper configuration

    Returns:
        PRAW Submission object with expanded comments

    Raises:
        ValueError: If URL is invalid or post not found
        PermissionError: If post is inaccessible
        ConnectionError: If API rate limit hit or network error
    """
    validated_url = validate_reddit_url(url)
    logger.info(f"Fetching post: {validated_url}")

    try:
        post = reddit.submission(url=validated_url)
        # Force-load the post to trigger any access errors early
        _ = post.title
        logger.info(f"Post loaded: '{post.title}' ({post.num_comments} comments)")

    except praw.exceptions.InvalidURL:
        raise ValueError(f"PRAW could not parse URL: {validated_url}")

    except PRAWException as e:
        error_msg = str(e).lower()
        if "403" in error_msg or "forbidden" in error_msg:
            raise PermissionError(
                "Cannot access this post. It may be deleted, "
                "in a private subreddit, or quarantined."
            )
        elif "404" in error_msg or "not found" in error_msg:
            raise ValueError(f"Post not found: {validated_url}")
        elif "429" in error_msg or "rate" in error_msg:
            raise ConnectionError(
                "Reddit API rate limit exceeded. "
                "Please wait a few minutes and try again."
            )
        else:
            raise ConnectionError(f"Reddit API error: {e}")

    except Exception as e:
        raise ConnectionError(f"Failed to fetch post: {e}")

    # Expand MoreComments objects
    more_limit = config.more_comments_limit
    if more_limit == -1:
        more_limit = None  # PRAW convention: None = expand all

    try:
        logger.info(f"Expanding comment tree (limit={config.more_comments_limit})...")
        post.comments.replace_more(limit=more_limit)
        logger.info(f"Comment tree expanded: {len(post.comments)} top-level comments")
    except Exception as e:
        logger.warning(
            f"Could not fully expand comments: {e}. "
            f"Some nested replies may be missing."
        )

    # Set sort order
    post.comment_sort = config.comment_sort
    logger.info(f"Comment sort order: {config.comment_sort}")

    return post


# ══════════════════════════════════════════════════════════════
# Section 3: Comment Tree Construction
# ══════════════════════════════════════════════════════════════

def build_comment_tree(
    comments,
    config: ScraperConfig,
    parent_number: str = '',
    depth: int = 0,
) -> list[dict[str, Any]]:
    """
    Build a structured, nested comment tree from PRAW comment objects.

    This is the core recursive function. It produces pure data with
    NO side effects (no printing, no file I/O). The returned structure
    can be rendered to terminal, HTML, JSON, or any other format.

    Args:
        comments: Iterable of PRAW Comment objects
        config: ScraperConfig controlling depth, filtering, etc.
        parent_number: Hierarchy string of the parent (e.g., '1.2')
        depth: Current recursion depth

    Returns:
        List of comment dictionaries with nested 'replies' lists

    Comment dictionary structure:
        {
            "hierarchy": "1.2.3",
            "id": None,  (assigned later by CommentIDGenerator)
            "author": "username",
            "score": 42,
            "body": "comment text...",
            "created_utc": 1700000000.0,
            "created_readable": "2023-11-14 22:13:20 UTC",
            "created_relative": "3 months ago",
            "depth": 2,
            "is_op": False,
            "is_deleted": False,
            "gilded": 0,
            "permalink": "https://reddit.com/...",
            "replies": [...]
        }
    """
    # Depth limit check
    if depth >= config.max_depth:
        return [{"_truncated": True, "depth": depth}]

    result = []
    reply_index = 0

    for comment in comments:
        # Skip MoreComments objects that weren't fully expanded
        if isinstance(comment, MoreComments):
            logger.debug(f"Skipping unexpanded MoreComments at depth {depth}")
            continue

        # Safety check: ensure the comment has a body
        if not hasattr(comment, 'body'):
            logger.debug(f"Skipping comment without body at depth {depth}")
            continue

        # Determine author and deletion status
        author = safe_author(comment)
        is_deleted = (author == "[deleted]")

        # Apply filters
        if config.skip_deleted and is_deleted:
            continue
        if config.min_score is not None and comment.score < config.min_score:
            continue

        # Increment index only for comments that pass filters
        reply_index += 1
        hierarchy = f"{parent_number}.{reply_index}" if parent_number else str(reply_index)

        # Optionally truncate body
        body = comment.body
        if config.max_body_length is not None:
            body = truncate_text(body, config.max_body_length)

        # Build the comment data dictionary
        comment_data = {
            "hierarchy": hierarchy,
            "id": None,  # Will be assigned by CommentIDGenerator
            "author": author,
            "score": comment.score,
            "body": body,
            "created_utc": comment.created_utc,
            "created_readable": format_timestamp(comment.created_utc),
            "created_relative": format_relative_time(comment.created_utc),
            "depth": depth,
            "is_op": getattr(comment, 'is_submitter', False),
            "is_deleted": is_deleted,
            "gilded": getattr(comment, 'gilded', 0),
            "permalink": f"https://reddit.com{comment.permalink}",
            "replies": [],
        }

        # Recursively process replies
        if comment.replies:
            comment_data["replies"] = build_comment_tree(
                comment.replies,
                config=config,
                parent_number=hierarchy,
                depth=depth + 1,
            )

        result.append(comment_data)

    return result


def assign_ids(tree: list[dict], id_generator: CommentIDGenerator) -> None:
    """
    Walk the comment tree and assign unique IDs to every comment.

    This mutates the dictionaries in-place, setting the 'id' field.

    Args:
        tree: List of comment dictionaries (output of build_comment_tree)
        id_generator: CommentIDGenerator instance for this thread
    """
    for comment in tree:
        if "_truncated" in comment:
            continue
        comment["id"] = id_generator.generate(comment["hierarchy"])
        assign_ids(comment.get("replies", []), id_generator)


# ══════════════════════════════════════════════════════════════
# Section 4: Post Metadata Extraction
# ══════════════════════════════════════════════════════════════

def extract_post_metadata(post: praw.models.Submission) -> dict[str, Any]:
    """
    Extract structured metadata from a Reddit post.

    Args:
        post: PRAW Submission object

    Returns:
        Dictionary with post metadata
    """
    author = "[deleted]"
    if post.author is not None:
        try:
            author = post.author.name
        except AttributeError:
            author = "[unknown]"

    return {
        "title": post.title,
        "body": post.selftext if post.selftext else "",
        "author": author,
        "score": post.score,
        "upvote_ratio": getattr(post, 'upvote_ratio', None),
        "num_comments": post.num_comments,
        "num_top_level": len(post.comments),
        "subreddit": str(post.subreddit),
        "url": post.url,
        "permalink": f"https://reddit.com{post.permalink}",
        "created_utc": post.created_utc,
        "created_readable": format_timestamp(post.created_utc),
        "created_relative": format_relative_time(post.created_utc),
        "is_nsfw": post.over_18,
        "is_locked": post.locked,
        "is_archived": post.archived,
        "flair": post.link_flair_text,
    }


# ══════════════════════════════════════════════════════════════
# Section 5: Analytics
# ══════════════════════════════════════════════════════════════

def analyze_thread(tree: list[dict]) -> dict[str, Any]:
    """
    Generate analytics for a comment thread.

    Walks the entire comment tree and computes summary statistics.

    Args:
        tree: Structured comment tree (output of build_comment_tree)

    Returns:
        Dictionary of thread statistics
    """
    stats = {
        "total_comments": 0,
        "total_score": 0,
        "max_depth_reached": 0,
        "unique_authors": set(),
        "deleted_count": 0,
        "op_replies": 0,
        "gilded_count": 0,
        "truncated_branches": 0,
        "negative_score_count": 0,
        "top_comment_author": None,
        "top_comment_score": -float('inf'),
    }

    def _walk(comments: list[dict]) -> None:
        for c in comments:
            if "_truncated" in c:
                stats["truncated_branches"] += 1
                continue

            stats["total_comments"] += 1
            stats["total_score"] += c["score"]
            stats["max_depth_reached"] = max(stats["max_depth_reached"], c["depth"])
            stats["unique_authors"].add(c["author"])

            if c["is_deleted"]:
                stats["deleted_count"] += 1
            if c.get("is_op"):
                stats["op_replies"] += 1
            if c.get("gilded", 0) > 0:
                stats["gilded_count"] += 1
            if c["score"] < 0:
                stats["negative_score_count"] += 1

            # Track top scoring comment
            if c["score"] > stats["top_comment_score"]:
                stats["top_comment_score"] = c["score"]
                stats["top_comment_author"] = c["author"]

            _walk(c.get("replies", []))

    _walk(tree)

    # Compute derived stats
    total = stats["total_comments"]
    stats["unique_author_count"] = len(stats["unique_authors"])

    if total > 0:
        stats["avg_score"] = round(stats["total_score"] / total, 1)
    else:
        stats["avg_score"] = 0
        stats["top_comment_author"] = None
        stats["top_comment_score"] = 0

    # Convert set to count for JSON serialization
    del stats["unique_authors"]

    return stats


# ══════════════════════════════════════════════════════════════
# Section 6: Data Export
# ══════════════════════════════════════════════════════════════

def export_json(
    post_meta: dict,
    tree: list[dict],
    analytics: dict,
    filepath: str,
) -> str:
    """
    Export the full scrape result as a JSON file.

    Args:
        post_meta: Post metadata dictionary
        tree: Comment tree
        analytics: Thread analytics
        filepath: Output file path

    Returns:
        Absolute path of the exported file
    """
    output = {
        "post": post_meta,
        "comments": tree,
        "analytics": analytics,
        "export_info": {
            "format": "json",
            "exported_at": format_timestamp(
                __import__('time').time()
            ),
        },
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"JSON exported to: {filepath}")
    return filepath


def export_csv(tree: list[dict], filepath: str) -> str:
    """
    Export flattened comment data as a CSV file.

    The nested tree is flattened into rows, one per comment.

    Args:
        tree: Comment tree
        filepath: Output file path

    Returns:
        Absolute path of the exported file
    """
    flat = _flatten_tree(tree)

    if not flat:
        logger.warning("No comments to export")
        return filepath

    fieldnames = [
        'id', 'hierarchy', 'depth', 'author', 'score',
        'body', 'is_op', 'is_deleted', 'gilded',
        'created_readable', 'permalink',
    ]

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(flat)

    logger.info(f"CSV exported to: {filepath} ({len(flat)} rows)")
    return filepath


def export_txt(
    post_meta: dict,
    tree: list[dict],
    analytics: dict,
    filepath: str,
) -> str:
    """
    Export the thread as a formatted plain-text file.

    Args:
        post_meta: Post metadata dictionary
        tree: Comment tree
        analytics: Thread analytics
        filepath: Output file path

    Returns:
        Absolute path of the exported file
    """
    lines = []

    # Post header
    lines.append("=" * 70)
    lines.append(f"Title: {post_meta['title']}")
    lines.append(f"Author: u/{post_meta['author']} | r/{post_meta['subreddit']}")
    lines.append(f"Score: {post_meta['score']} | Comments: {post_meta['num_comments']}")
    lines.append(f"Posted: {post_meta['created_readable']}")
    lines.append("=" * 70)

    if post_meta['body']:
        lines.append("")
        lines.append(post_meta['body'])

    lines.append("")
    lines.append("-" * 70)
    lines.append("COMMENTS")
    lines.append("-" * 70)

    # Comments
    def _write_tree(comments: list[dict]) -> None:
        for c in comments:
            if "_truncated" in c:
                indent = "  " * c["depth"]
                lines.append(f"{indent}[... truncated at depth {c['depth']} ...]")
                continue

            indent = "  " * c["depth"]
            label = "Comment" if c["depth"] == 0 else "Reply"
            op_tag = " [OP]" if c.get("is_op") else ""

            lines.append("")
            lines.append(
                f"{indent}{label} {c['hierarchy']} by {c['author']}{op_tag} "
                f"({c['score']} pts)"
            )
            for body_line in c['body'].split('\n'):
                lines.append(f"{indent}  {body_line}")

            _write_tree(c.get("replies", []))

    _write_tree(tree)

    # Analytics
    lines.append("")
    lines.append("=" * 70)
    lines.append("ANALYTICS")
    lines.append("=" * 70)
    for key, value in analytics.items():
        lines.append(f"  {key}: {value}")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    logger.info(f"TXT exported to: {filepath}")
    return filepath


def _flatten_tree(tree: list[dict], result: Optional[list] = None) -> list[dict]:
    """
    Flatten a nested comment tree into a flat list.

    Args:
        tree: Nested comment tree
        result: Accumulator (used internally for recursion)

    Returns:
        Flat list of comment dictionaries (without nested replies)
    """
    if result is None:
        result = []

    for comment in tree:
        if "_truncated" in comment:
            continue

        # Create a shallow copy without the nested replies
        flat = {k: v for k, v in comment.items() if k != 'replies'}
        # Truncate body for CSV cells
        flat['body'] = truncate_text(flat.get('body', ''), max_length=1000)
        result.append(flat)

        _flatten_tree(comment.get("replies", []), result)

    return result