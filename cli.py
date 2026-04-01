"""
══════════════════════════════════════════════════════════════
Command-Line Interface — Version 2
══════════════════════════════════════════════════════════════
Terminal-based interface with sentiment display, user analytics
rendering, engagement duration, and TXT export support.
══════════════════════════════════════════════════════════════
"""

import sys
import argparse
import logging
from typing import Optional

from config import load_config, ScraperConfig
from scraper import (
    create_reddit_instance,
    fetch_post,
    build_comment_tree,
    assign_ids,
    extract_post_metadata,
    analyze_thread,
    export_json,
    export_csv,
    export_txt,
)
from utils import (
    bold,
    underline,
    dim,
    colored,
    CommentIDGenerator,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Section 1: Argument Parsing
# ══════════════════════════════════════════════════════════════

def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="reddit-explorer",
        description="Reddit Discussion Explorer v2 — Fetch, analyze, and display Reddit comment threads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url https://www.reddit.com/r/AskReddit/comments/abc123/title/
  %(prog)s -u https://redd.it/abc123 --depth 5 --sort top
  %(prog)s -u <url> --format json --output thread.json
  %(prog)s -u <url> --format txt --output thread.txt
  %(prog)s -u <url> --min-score 10 --skip-deleted
  %(prog)s --about
        """,
    )

    parser.add_argument("--url", "-u", type=str, default=None, help="Reddit post URL to scrape")
    parser.add_argument("--about", action="store_true", help="Show detailed information about this tool")

    scrape_group = parser.add_argument_group("Scraping Options")
    scrape_group.add_argument("--depth", "-d", type=int, default=10, help="Maximum reply depth (default: 10, max: 50)")
    scrape_group.add_argument("--sort", "-s", choices=["best", "top", "new", "controversial", "old", "qa"], default="best")
    scrape_group.add_argument("--more-comments", "-m", type=int, default=0, help="MoreComments to expand (0=none, -1=all)")

    filter_group = parser.add_argument_group("Filtering Options")
    filter_group.add_argument("--min-score", type=int, default=None)
    filter_group.add_argument("--skip-deleted", action="store_true")
    filter_group.add_argument("--max-body-length", type=int, default=None)

    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument("--format", "-f", choices=["tree", "indent", "json", "csv", "txt"], default="tree")
    output_group.add_argument("--output", "-o", type=str, default=None)
    output_group.add_argument("--no-body", action="store_true")
    output_group.add_argument("--no-analytics", action="store_true")
    output_group.add_argument("--no-sentiment", action="store_true", help="Hide sentiment scores in tree output")

    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args(argv)

    if not args.about and not args.url:
        parser.error("--url is required (or use --about for info)")
    if args.depth < 1 or args.depth > 50:
        parser.error("--depth must be between 1 and 50")

    return args


# ══════════════════════════════════════════════════════════════
# Section 2: About
# ══════════════════════════════════════════════════════════════

def print_about():
    print()
    print(bold("═" * 65))
    print(bold("  Reddit Discussion Explorer v2 — About"))
    print(bold("═" * 65))
    print("""
  Version 2 adds:
  • Keyword-based sentiment analysis with negation handling
  • Per-user analytics (word counts, vocabulary richness, top words)
  • Engagement duration calculation
  • TXT export in human-readable format
  • Improved thread analytics with sentiment distribution

  See README.md for full documentation.
""")
    print(bold("═" * 65))


# ══════════════════════════════════════════════════════════════
# Section 3: Tree Rendering (with sentiment)
# ══════════════════════════════════════════════════════════════

def render_tree(tree: list[dict], show_body: bool = True, show_sentiment: bool = True) -> None:
    _render_tree_recursive(tree, prefix="", show_body=show_body, show_sentiment=show_sentiment)


def _render_tree_recursive(
    comments: list[dict],
    prefix: str = "",
    show_body: bool = True,
    show_sentiment: bool = True,
) -> None:
    for i, comment in enumerate(comments):
        is_last = (i == len(comments) - 1)
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "

        if "_truncated" in comment:
            print(f"{prefix}{connector}{dim(f'[... truncated at depth {comment[\"depth\"]} ...]')}")
            continue

        depth = comment["depth"]
        hierarchy = comment["hierarchy"]
        author = comment["author"]
        score = comment["score"]
        is_op = comment.get("is_op", False)

        label = "Comment" if depth == 0 else "Reply"
        op_tag = colored(" [OP]", "cyan") if is_op else ""

        if score >= 50:
            score_str = colored(f"({score} pts)", "green")
        elif score < 0:
            score_str = colored(f"({score} pts)", "red")
        else:
            score_str = f"({score} pts)"

        # Sentiment indicator
        sent_str = ""
        if show_sentiment:
            sentiment = comment.get("sentiment", {})
            sent_label = sentiment.get("label", "neutral")
            sent_score = sentiment.get("score", 0)
            if sent_label == "positive":
                sent_str = colored(f" [+{sent_score:.2f}]", "green")
            elif sent_label == "negative":
                sent_str = colored(f" [{sent_score:.2f}]", "red")
            else:
                sent_str = dim(f" [~{sent_score:.2f}]")

        header = f"{label} {hierarchy} by {author}{op_tag} {score_str}{sent_str}"
        print(f"{prefix}{connector}{bold(header)}")

        if show_body and comment.get("body"):
            body_prefix = f"{prefix}{extension}│  "
            for line in comment["body"].split('\n'):
                print(f"{body_prefix}{line}")
            print(f"{prefix}{extension}│")

        if comment.get("id"):
            print(f"{prefix}{extension}{dim(f'ID: {comment[\"id\"]}')}")

        replies = comment.get("replies", [])
        if replies:
            _render_tree_recursive(replies, prefix=f"{prefix}{extension}", show_body=show_body, show_sentiment=show_sentiment)


def render_indented(tree: list[dict], show_body: bool = True, show_sentiment: bool = True) -> None:
    for comment in tree:
        if "_truncated" in comment:
            indent = "  " * comment["depth"]
            print(f"{indent}{dim('[... truncated ...]')}")
            continue

        indent = "  " * comment["depth"]
        label = "Comment" if comment["depth"] == 0 else "Reply"
        op_tag = colored(" [OP]", "cyan") if comment.get("is_op") else ""

        sent_str = ""
        if show_sentiment:
            sentiment = comment.get("sentiment", {})
            sent_label = sentiment.get("label", "neutral")
            sent_score = sentiment.get("score", 0)
            sent_str = f" [{sent_label}: {sent_score:.2f}]"

        print(
            f"{indent}{bold(f'{label} {comment[\"hierarchy\"]}')} "
            f"by {comment['author']}{op_tag} ({comment['score']}↑){sent_str}"
        )

        if show_body and comment.get("body"):
            for line in comment["body"].split('\n'):
                print(f"{indent}  {line}")
            print()

        render_indented(comment.get("replies", []), show_body=show_body, show_sentiment=show_sentiment)


# ══════════════════════════════════════════════════════════════
# Section 4: Analytics Display
# ══════════════════════════════════════════════════════════════

def render_analytics(analytics: dict) -> None:
    print()
    print(bold("═" * 50))
    print(bold("  Thread Analytics"))
    print(bold("═" * 50))

    display_map = {
        "total_comments": ("Total Comments", None),
        "unique_author_count": ("Unique Authors", None),
        "avg_score": ("Average Score", None),
        "total_score": ("Total Score", None),
        "max_depth_reached": ("Max Depth Reached", None),
        "op_replies": ("OP Replies", None),
        "deleted_count": ("Deleted Comments", "red"),
        "negative_score_count": ("Negative Score", "red"),
        "gilded_count": ("Gilded Comments", "yellow"),
        "truncated_branches": ("Truncated Branches", "yellow"),
        "top_comment_author": ("Top Comment By", "green"),
        "top_comment_score": ("Top Comment Score", "green"),
    }

    for key, (label, color) in display_map.items():
        value = analytics.get(key, "N/A")
        value_str = str(value)
        if color and value and value != 0:
            value_str = colored(value_str, color)
        print(f"  {label:<24} {value_str}")

    # Engagement
    engagement = analytics.get("engagement_duration", {})
    print(f"  {'Engagement Duration':<24} {engagement.get('text', 'N/A')}")

    # Sentiment
    print()
    print(bold("  Sentiment Distribution"))
    print(f"  {'Overall':<24} {analytics.get('sentiment_overall_label', 'neutral')} ({analytics.get('sentiment_avg', 0)})")
    print(f"  {'Positive':<24} {analytics.get('sentiment_positive_count', 0)}")
    print(f"  {'Neutral':<24} {analytics.get('sentiment_neutral_count', 0)}")
    print(f"  {'Negative':<24} {analytics.get('sentiment_negative_count', 0)}")

    print(bold("═" * 50))


# ══════════════════════════════════════════════════════════════
# Section 5: Main Entry Point
# ══════════════════════════════════════════════════════════════

def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.about:
        print_about()
        return 0

    try:
        app_config = load_config()
    except Exception as e:
        print(colored(f"\n✗ Configuration error: {e}", "red"))
        return 1

    scraper_config = ScraperConfig(
        max_depth=args.depth,
        min_score=args.min_score,
        comment_sort=args.sort,
        more_comments_limit=args.more_comments,
        skip_deleted=args.skip_deleted,
        max_body_length=args.max_body_length,
    )

    try:
        scraper_config.validate()
    except ValueError as e:
        print(colored(f"\n✗ Invalid configuration: {e}", "red"))
        return 1

    try:
        print(dim("\n⏳ Connecting to Reddit API..."))
        reddit = create_reddit_instance(app_config.credentials)
    except EnvironmentError as e:
        print(colored(f"\n✗ {e}", "red"))
        return 1
    except ConnectionError as e:
        print(colored(f"\n✗ Connection failed: {e}", "red"))
        return 1

    try:
        print(dim("⏳ Fetching post and comments..."))
        post = fetch_post(reddit, args.url, scraper_config)
    except ValueError as e:
        print(colored(f"\n✗ Invalid input: {e}", "red"))
        return 1
    except PermissionError as e:
        print(colored(f"\n✗ Access denied: {e}", "red"))
        return 1
    except ConnectionError as e:
        print(colored(f"\n✗ {e}", "red"))
        return 1

    post_meta = extract_post_metadata(post)

    print(dim("⏳ Building comment tree & analyzing sentiment..."))
    tree = build_comment_tree(post.comments, config=scraper_config)

    id_gen = CommentIDGenerator(base_length=scraper_config.id_base_length)
    assign_ids(tree, id_gen)

    analytics = analyze_thread(tree, post_meta=post_meta)

    show_body = not args.no_body
    show_sentiment = not getattr(args, 'no_sentiment', False)

    if args.format == "json":
        filepath = args.output or f"export_{id_gen.thread_id}.json"
        export_json(post_meta, tree, analytics, filepath)
        print(colored(f"\n✓ JSON exported to: {filepath}", "green"))

    elif args.format == "csv":
        filepath = args.output or f"export_{id_gen.thread_id}.csv"
        export_csv(tree, filepath)
        print(colored(f"\n✓ CSV exported to: {filepath}", "green"))

    elif args.format == "txt":
        filepath = args.output or f"export_{id_gen.thread_id}.txt"
        export_txt(post_meta, tree, analytics, filepath)
        print(colored(f"\n✓ TXT exported to: {filepath}", "green"))

    elif args.format == "indent":
        _print_post_header(post_meta, id_gen)
        render_indented(tree, show_body=show_body, show_sentiment=show_sentiment)
        if not args.no_analytics:
            render_analytics(analytics)

    else:
        _print_post_header(post_meta, id_gen)
        render_tree(tree, show_body=show_body, show_sentiment=show_sentiment)
        if not args.no_analytics:
            render_analytics(analytics)

    return 0


def _print_post_header(post_meta: dict, id_gen: CommentIDGenerator) -> None:
    print()
    print(bold("═" * 65))
    print(bold(f"  {post_meta['title']}"))
    print(bold("═" * 65))
    print(
        f"  r/{post_meta['subreddit']} • u/{post_meta['author']} • "
        f"{post_meta['score']} pts • "
        f"{post_meta['num_comments']} comments "
        f"({post_meta['num_top_level']} top-level)"
    )
    print(f"  Posted: {post_meta['created_relative']} ({post_meta['created_readable']})")

    if post_meta.get("flair"):
        print(f"  Flair: {post_meta['flair']}")

    # Post sentiment
    post_sent = post_meta.get("sentiment", {})
    sent_label = post_sent.get("label", "neutral")
    sent_score = post_sent.get("score", 0)
    print(f"  Post Sentiment: {sent_label} ({sent_score})")

    flags = []
    if post_meta.get("is_nsfw"):
        flags.append(colored("NSFW", "red"))
    if post_meta.get("is_locked"):
        flags.append(colored("LOCKED", "yellow"))
    if post_meta.get("is_archived"):
        flags.append(dim("ARCHIVED"))
    if flags:
        print(f"  Flags: {' '.join(flags)}")

    print(f"  Thread ID: {id_gen.thread_id}")
    print(bold("─" * 65))

    if post_meta["body"]:
        print()
        print(f"  {post_meta['body']}")
        print()
        print(bold("─" * 65))

    print()


if __name__ == "__main__":
    sys.exit(main())