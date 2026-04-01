"""
══════════════════════════════════════════════════════════════
Reddit Scraper — Core Logic — Version 2
══════════════════════════════════════════════════════════════
Handles all Reddit API interaction, comment tree construction,
sentiment analysis, user analytics, engagement duration,
thread analytics, and data export (JSON, CSV, TXT).
This module contains NO printing or display logic.
══════════════════════════════════════════════════════════════
"""

import json
import csv
import time
import logging
from typing import Optional, Any

import praw
from praw.models import MoreComments
from praw.exceptions import PRAWException

from config import RedditCredentials, ScraperConfig
from utils import (
    safe_author,
    validate_reddit_url,
    CommentIDGenerator,
    format_timestamp,
    format_relative_time,
    truncate_text,
    analyze_sentiment,
    analyze_user_activity,
    compute_engagement_duration,
    tokenize_no_stopwords,
    STOPWORDS,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Section 1: Reddit Connection
# ══════════════════════════════════════════════════════════════

def create_reddit_instance(credentials: RedditCredentials) -> praw.Reddit:
    """Create and validate a PRAW Reddit instance."""
    credentials.validate()
    try:
        reddit = praw.Reddit(
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            user_agent=credentials.user_agent,
            username=credentials.username,
        )
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
    """Fetch a Reddit post and expand its comment tree."""
    validated_url = validate_reddit_url(url)
    logger.info(f"Fetching post: {validated_url}")

    try:
        post = reddit.submission(url=validated_url)
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

    more_limit = config.more_comments_limit
    if more_limit == -1:
        more_limit = None
    try:
        logger.info(f"Expanding comment tree (limit={config.more_comments_limit})...")
        post.comments.replace_more(limit=more_limit)
        logger.info(f"Comment tree expanded: {len(post.comments)} top-level comments")
    except Exception as e:
        logger.warning(f"Could not fully expand comments: {e}.")

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
    Now includes per-comment sentiment analysis.
    """
    if depth >= config.max_depth:
        return [{"_truncated": True, "depth": depth}]

    result = []
    reply_index = 0

    for comment in comments:
        if isinstance(comment, MoreComments):
            continue
        if not hasattr(comment, 'body'):
            continue

        author = safe_author(comment)
        is_deleted = (author == "[deleted]")

        if config.skip_deleted and is_deleted:
            continue
        if config.min_score is not None and comment.score < config.min_score:
            continue

        reply_index += 1
        hierarchy = f"{parent_number}.{reply_index}" if parent_number else str(reply_index)

        body = comment.body
        if config.max_body_length is not None:
            body = truncate_text(body, config.max_body_length)

        # Sentiment analysis
        sentiment = analyze_sentiment(body)

        comment_data = {
            "hierarchy": hierarchy,
            "id": None,
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
            "sentiment": sentiment,
            "replies": [],
        }

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
    """Walk the comment tree and assign unique IDs to every comment."""
    for comment in tree:
        if "_truncated" in comment:
            continue
        comment["id"] = id_generator.generate(comment["hierarchy"])
        assign_ids(comment.get("replies", []), id_generator)


# ══════════════════════════════════════════════════════════════
# Section 4: Post Metadata Extraction
# ══════════════════════════════════════════════════════════════

def extract_post_metadata(post: praw.models.Submission) -> dict[str, Any]:
    """Extract structured metadata from a Reddit post, including sentiment."""
    author = "[deleted]"
    if post.author is not None:
        try:
            author = post.author.name
        except AttributeError:
            author = "[unknown]"

    body = post.selftext if post.selftext else ""
    post_sentiment = analyze_sentiment(body) if body else {
        "score": 0.0, "label": "neutral",
        "positive_count": 0, "negative_count": 0,
        "positive_words": [], "negative_words": [],
        "magnitude": 0.0,
    }

    return {
        "title": post.title,
        "body": body,
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
        "sentiment": post_sentiment,
    }


# ══════════════════════════════════════════════════════════════
# Section 5: Analytics
# ══════════════════════════════════════════════════════════════

def analyze_thread(tree: list[dict], post_meta: Optional[dict] = None) -> dict[str, Any]:
    """
    Generate analytics for a comment thread.
    Now includes sentiment distribution, engagement duration,
    and user analytics.
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
        "sentiment_positive_count": 0,
        "sentiment_negative_count": 0,
        "sentiment_neutral_count": 0,
        "sentiment_scores": [],
        "all_timestamps": [],
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
            if c["score"] > stats["top_comment_score"]:
                stats["top_comment_score"] = c["score"]
                stats["top_comment_author"] = c["author"]

            # Sentiment
            sentiment = c.get("sentiment", {})
            label = sentiment.get("label", "neutral")
            if label == "positive":
                stats["sentiment_positive_count"] += 1
            elif label == "negative":
                stats["sentiment_negative_count"] += 1
            else:
                stats["sentiment_neutral_count"] += 1

            score = sentiment.get("score", 0)
            stats["sentiment_scores"].append(score)

            # Timestamps
            created = c.get("created_utc", 0)
            if created > 0:
                stats["all_timestamps"].append(created)

            _walk(c.get("replies", []))

    _walk(tree)

    total = stats["total_comments"]
    stats["unique_author_count"] = len(stats["unique_authors"])

    if total > 0:
        stats["avg_score"] = round(stats["total_score"] / total, 1)
    else:
        stats["avg_score"] = 0
        stats["top_comment_author"] = None
        stats["top_comment_score"] = 0

    # Average sentiment
    sentiment_scores = stats["sentiment_scores"]
    if sentiment_scores:
        stats["sentiment_avg"] = round(sum(sentiment_scores) / len(sentiment_scores), 4)
    else:
        stats["sentiment_avg"] = 0.0

    if stats["sentiment_avg"] > 0.05:
        stats["sentiment_overall_label"] = "positive"
    elif stats["sentiment_avg"] < -0.05:
        stats["sentiment_overall_label"] = "negative"
    else:
        stats["sentiment_overall_label"] = "neutral"

    # Engagement duration
    timestamps = stats["all_timestamps"]
    post_created = post_meta.get("created_utc", 0) if post_meta else 0

    if timestamps:
        earliest = min(min(timestamps), post_created) if post_created > 0 else min(timestamps)
        latest = max(timestamps)
        stats["engagement_duration"] = compute_engagement_duration(earliest, latest)
        stats["earliest_comment_utc"] = earliest
        stats["latest_comment_utc"] = latest
        stats["earliest_comment_readable"] = format_timestamp(earliest)
        stats["latest_comment_readable"] = format_timestamp(latest)
    else:
        stats["engagement_duration"] = {"parts": [], "text": "N/A", "total_seconds": 0}
        stats["earliest_comment_utc"] = 0
        stats["latest_comment_utc"] = 0
        stats["earliest_comment_readable"] = "N/A"
        stats["latest_comment_readable"] = "N/A"

    # User analytics
    post_author = post_meta.get("author", "") if post_meta else ""
    stats["user_analytics"] = analyze_user_activity(tree, post_author=post_author)

    # Clean up non-serializable items
    del stats["unique_authors"]
    del stats["sentiment_scores"]
    del stats["all_timestamps"]

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
    """Export the full scrape result as a JSON file."""
    output = {
        "post": post_meta,
        "comments": tree,
        "analytics": analytics,
        "export_info": {
            "format": "json",
            "exported_at": format_timestamp(time.time()),
        },
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"JSON exported to: {filepath}")
    return filepath


def export_csv(tree: list[dict], filepath: str) -> str:
    """Export flattened comment data as a CSV file."""
    flat = _flatten_tree(tree)
    if not flat:
        logger.warning("No comments to export")
        return filepath

    fieldnames = [
        'id', 'hierarchy', 'depth', 'author', 'score',
        'body', 'is_op', 'is_deleted', 'gilded',
        'sentiment_score', 'sentiment_label',
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
    Export the thread as a human-readable plain-text file.
    Designed to be readable by humans and efficient when
    sent to LLMs (not token-heavy like JSON/CSV).
    """
    lines = []

    # ── Post Header ──
    lines.append("Title of Post")
    lines.append(post_meta.get("title", "Untitled"))
    lines.append("")
    body = post_meta.get("body", "")
    if body:
        lines.append("Body of Post")
        lines.append(body)
    else:
        lines.append("Body of Post")
        lines.append("[This post does not have a body]")
    lines.append("")

    # Post sentiment
    post_sent = post_meta.get("sentiment", {})
    if post_sent:
        lines.append(
            f"Post Sentiment: {post_sent.get('label', 'neutral')} "
            f"(score: {post_sent.get('score', 0)})"
        )
        lines.append("")

    lines.append(
        f"NOTE: This post has {post_meta.get('score', 0)} upvotes "
        f"and has {analytics.get('total_comments', 0)} replies."
    )
    lines.append("")

    # ── Engagement Duration ──
    engagement = analytics.get("engagement_duration", {})
    eng_text = engagement.get("text", "N/A")
    lines.append(f"Total Length of Engagement: {eng_text}")
    lines.append("")

    # ── Comments ──
    lines.append("Comment replies to post:")

    def _write_comment(c: dict, lines_list: list):
        if "_truncated" in c:
            indent = "  " * c.get("depth", 0)
            lines_list.append(f"{indent}[... replies truncated at depth {c['depth']} ...]")
            return

        hierarchy = c.get("hierarchy", "?")
        cid = c.get("id", "?")
        author = c.get("author", "[unknown]")
        score = c.get("score", 0)
        body_text = c.get("body", "")
        depth = c.get("depth", 0)
        sentiment = c.get("sentiment", {})
        sent_label = sentiment.get("label", "neutral")
        sent_score = sentiment.get("score", 0)

        if depth == 0:
            # Top-level comment
            lines_list.append("")
            lines_list.append("-------------------------------")
            lines_list.append(
                f"Comment ID: {cid} (Comment {hierarchy} by {author} "
                f"({score} upvotes)):"
            )
            lines_list.append(body_text)
            lines_list.append(
                f"[Sentiment: {sent_label} ({sent_score})]"
            )
        else:
            # Reply
            lines_list.append("")
            lines_list.append("")
            lines_list.append(
                f"Reply {hierarchy} by {author} ({score} upvotes)):"
            )
            lines_list.append(body_text)
            lines_list.append(
                f"[Sentiment: {sent_label} ({sent_score})]"
            )

        for reply in c.get("replies", []):
            _write_comment(reply, lines_list)

    for comment in tree:
        _write_comment(comment, lines)

    # ── Analytics Summary ──
    lines.append("")
    lines.append("")
    lines.append("=" * 65)
    lines.append("THREAD ANALYTICS")
    lines.append("=" * 65)
    lines.append(f"  Total Comments: {analytics.get('total_comments', 0)}")
    lines.append(f"  Unique Authors: {analytics.get('unique_author_count', 0)}")
    lines.append(f"  Average Score: {analytics.get('avg_score', 0)}")
    lines.append(f"  Total Score: {analytics.get('total_score', 0)}")
    lines.append(f"  Max Depth Reached: {analytics.get('max_depth_reached', 0)}")
    lines.append(f"  OP Replies: {analytics.get('op_replies', 0)}")
    lines.append(f"  Deleted Comments: {analytics.get('deleted_count', 0)}")
    lines.append(f"  Negative Score Comments: {analytics.get('negative_score_count', 0)}")
    lines.append(f"  Gilded Comments: {analytics.get('gilded_count', 0)}")

    top_author = analytics.get("top_comment_author")
    top_score = analytics.get("top_comment_score", 0)
    if top_author:
        lines.append(f"  Top Comment: by {top_author} ({top_score} pts)")

    lines.append(f"  Total Length of Engagement: {eng_text}")
    lines.append("")

    # ── Sentiment Summary ──
    lines.append("-" * 65)
    lines.append("SENTIMENT ANALYSIS")
    lines.append("-" * 65)
    lines.append(f"  Overall Sentiment: {analytics.get('sentiment_overall_label', 'neutral')}")
    lines.append(f"  Average Sentiment Score: {analytics.get('sentiment_avg', 0)}")
    lines.append(f"  Positive Comments: {analytics.get('sentiment_positive_count', 0)}")
    lines.append(f"  Neutral Comments: {analytics.get('sentiment_neutral_count', 0)}")
    lines.append(f"  Negative Comments: {analytics.get('sentiment_negative_count', 0)}")
    lines.append("")

    # ── User Analytics ──
    user_analytics = analytics.get("user_analytics", {})
    if user_analytics:
        lines.append("-" * 65)
        lines.append("USER ANALYTICS")
        lines.append("-" * 65)

        # Sort by total score descending
        sorted_users = sorted(
            user_analytics.items(),
            key=lambda x: x[1].get("total_score", 0),
            reverse=True
        )

        for username, u in sorted_users:
            op_tag = " [OP]" if u.get("is_post_author") else ""
            lines.append("")
            lines.append(f"  User: {username}{op_tag}")
            lines.append(f"    Comments: {u.get('total_comments', 0)}")
            lines.append(f"    Total Score: {u.get('total_score', 0)}")
            lines.append(f"    Average Score: {u.get('avg_score', 0)}")
            lines.append(f"    Total Words: {u.get('total_words', 0)}")
            lines.append(f"    Unique Words: {u.get('unique_words', 0)}")
            lines.append(f"    Vocabulary Richness: {u.get('vocabulary_richness', 0)}")
            lines.append(f"    Deepest Reply Depth: {u.get('deepest_reply', 0)}")
            lines.append(f"    Sentiment: {u.get('sentiment_label', 'neutral')} (avg: {u.get('sentiment_avg', 0)})")

            top_words = u.get("most_used_words", [])
            if top_words:
                word_strs = [f"{w}({c})" for w, c in top_words[:15]]
                lines.append(f"    Top Words: {', '.join(word_strs)}")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    logger.info(f"TXT exported to: {filepath}")
    return filepath


def _flatten_tree(tree: list[dict], result: Optional[list] = None) -> list[dict]:
    """Flatten a nested comment tree into a flat list."""
    if result is None:
        result = []
    for comment in tree:
        if "_truncated" in comment:
            continue
        flat = {k: v for k, v in comment.items() if k != 'replies'}
        flat['body'] = truncate_text(flat.get('body', ''), max_length=1000)
        # Flatten sentiment
        sentiment = flat.pop('sentiment', {})
        flat['sentiment_score'] = sentiment.get('score', 0)
        flat['sentiment_label'] = sentiment.get('label', 'neutral')
        result.append(flat)
        _flatten_tree(comment.get("replies", []), result)

    return result