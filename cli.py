"""
══════════════════════════════════════════════════════════════
Command-Line Interface
══════════════════════════════════════════════════════════════
Provides a rich terminal-based interface for the Reddit scraper.
Handles argument parsing, terminal rendering of comment trees,
and interactive output.
══════════════════════════════════════════════════════════════
"""

import sys
import os
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
    """
    Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv if None)

    Returns:
        Parsed argument namespace
    """
    parser = argparse.ArgumentParser(
        prog="reddit-explorer",
        description="Reddit Discussion Explorer — Fetch, analyze, and display Reddit comment threads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url https://www.reddit.com/r/AskReddit/comments/abc123/title/
  %(prog)s -u https://redd.it/abc123 --depth 5 --sort top
  %(prog)s -u <url> --format json --output thread.json
  %(prog)s -u <url> --min-score 10 --skip-deleted
  %(prog)s --about
        """,
    )

    # ── Core Arguments ──
    parser.add_argument(
        "--url", "-u",
        type=str,
        default=None,
        help="Reddit post URL to scrape",
    )
    parser.add_argument(
        "--about",
        action="store_true",
        help="Show detailed information about this tool",
    )

    # ── Scraping Options ──
    scrape_group = parser.add_argument_group("Scraping Options")
    scrape_group.add_argument(
        "--depth", "-d",
        type=int,
        default=10,
        help="Maximum reply depth to fetch (default: 10, max: 50)",
    )
    scrape_group.add_argument(
        "--sort", "-s",
        choices=["best", "top", "new", "controversial", "old", "qa"],
        default="best",
        help="Comment sort order (default: best)",
    )
    scrape_group.add_argument(
        "--more-comments", "-m",
        type=int,
        default=0,
        help="Number of 'MoreComments' to expand (0=none, -1=all, default: 0)",
    )

    # ── Filtering Options ──
    filter_group = parser.add_argument_group("Filtering Options")
    filter_group.add_argument(
        "--min-score",
        type=int,
        default=None,
        help="Only show comments with at least this score",
    )
    filter_group.add_argument(
        "--skip-deleted",
        action="store_true",
        help="Skip comments by deleted users",
    )
    filter_group.add_argument(
        "--max-body-length",
        type=int,
        default=None,
        help="Truncate comment bodies to this many characters",
    )

    # ── Output Options ──
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "--format", "-f",
        choices=["tree", "indent", "json", "csv", "txt"],
        default="tree",
        help="Output format (default: tree)",
    )
    output_group.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file path (default: stdout for tree/indent, auto-named for json/csv/txt)",
    )
    output_group.add_argument(
        "--no-body",
        action="store_true",
        help="Hide comment bodies (show metadata only)",
    )
    output_group.add_argument(
        "--no-analytics",
        action="store_true",
        help="Hide thread analytics summary",
    )

    # ── Logging ──
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )

    args = parser.parse_args(argv)

    # Validation
    if not args.about and not args.url:
        parser.error("--url is required (or use --about for info)")

    if args.depth < 1 or args.depth > 50:
        parser.error("--depth must be between 1 and 50")

    return args


# ══════════════════════════════════════════════════════════════
# Section 2: About / Help
# ══════════════════════════════════════════════════════════════

def print_about():
    """Display detailed information about the tool."""
    print()
    print(bold("═" * 65))
    print(bold("  Reddit Discussion Explorer — About"))
    print(bold("═" * 65))
    print("""
  This tool fetches comments from Reddit posts and displays them
  in a structured, hierarchical format with unique IDs, filtering,
  analytics, and export capabilities.

  FEATURES
  ────────
  • Hierarchical comment tree with proper numbering (1, 1.1, 1.1.1)
  • Unique collision-free comment IDs (e.g., A7X9K2-1.2.3)
  • Multiple output formats: tree, indented, JSON, CSV, TXT
  • Comment filtering by score, deleted status
  • Thread analytics (avg score, max depth, unique authors, etc.)
  • Tree-style visual rendering with expand indicators
  • Secure credential management via .env files

  NUMBERING SYSTEM
  ────────────────
  • Top-level comments: 1, 2, 3, ...
  • Direct replies:     1.1, 1.2, 1.3, ...
  • Nested replies:     1.1.1, 1.1.2, 1.2.1, ...

  Each comment also gets a unique thread-scoped ID:
    {ThreadBase}-{Hierarchy}  →  A7X9K2-1.2.3

  SETUP
  ─────
  1. Copy .env.example to .env
  2. Add your Reddit API credentials
  3. Install dependencies: pip install -r requirements.txt
  4. Run: python cli.py --url <reddit_post_url>

  Get API credentials: https://www.reddit.com/prefs/apps/
""")
    print(bold("═" * 65))


# ══════════════════════════════════════════════════════════════
# Section 3: Terminal Tree Rendering
# ══════════════════════════════════════════════════════════════

def render_tree(tree: list[dict], show_body: bool = True) -> None:
    """
    Render a comment tree with box-drawing characters.

    Produces output like:
        Comment 1 by user123 [OP] (45 pts)
        │  This is the comment body text...
        │
        ├── Reply 1.1 by user456 (12 pts)
        │   │  Reply body text...
        │   │
        │   ├── Reply 1.1.1 by user789 (3 pts)
        │   │   │  Nested reply body...
        │   │
        │   └── Reply 1.1.2 by user101 (1 pts)
        │       │  Another nested reply...
        │
        └── Reply 1.2 by user202 (8 pts)
            │  Second reply body...

    Args:
        tree: List of comment dictionaries
        show_body: Whether to display comment body text
    """
    _render_tree_recursive(tree, prefix="", show_body=show_body)


def _render_tree_recursive(
    comments: list[dict],
    prefix: str = "",
    show_body: bool = True,
) -> None:
    """Internal recursive tree renderer."""
    for i, comment in enumerate(comments):
        is_last = (i == len(comments) - 1)
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "

        # Handle truncated branches
        if "_truncated" in comment:
            print(
                f"{prefix}{connector}"
                f"{dim(f'[... truncated at depth {comment[\"depth\"]} ...]')}"
            )
            continue

        # Build the header line
        depth = comment["depth"]
        hierarchy = comment["hierarchy"]
        author = comment["author"]
        score = comment["score"]
        is_op = comment.get("is_op", False)

        label = "Comment" if depth == 0 else "Reply"
        op_tag = colored(" [OP]", "cyan") if is_op else ""

        # Color-code the score
        if score >= 50:
            score_str = colored(f"({score} pts)", "green")
        elif score < 0:
            score_str = colored(f"({score} pts)", "red")
        else:
            score_str = f"({score} pts)"

        # Print the comment header
        header = f"{label} {hierarchy} by {author}{op_tag} {score_str}"
        print(f"{prefix}{connector}{bold(header)}")

        # Print the body
        if show_body and comment.get("body"):
            body_prefix = f"{prefix}{extension}│  "
            body_lines = comment["body"].split('\n')
            for line in body_lines:
                print(f"{body_prefix}{line}")
            print(f"{prefix}{extension}│")

        # Print the ID in dim text
        if comment.get("id"):
            print(f"{prefix}{extension}{dim(f'ID: {comment[\"id\"]}')}")

        # Recursively render replies
        replies = comment.get("replies", [])
        if replies:
            _render_tree_recursive(
                replies,
                prefix=f"{prefix}{extension}",
                show_body=show_body,
            )


def render_indented(tree: list[dict], show_body: bool = True) -> None:
    """
    Render a comment tree with simple indentation.

    A simpler alternative to the box-drawing tree renderer.

    Args:
        tree: List of comment dictionaries
        show_body: Whether to display comment body text
    """
    for comment in tree:
        if "_truncated" in comment:
            indent = "  " * comment["depth"]
            print(f"{indent}{dim('[... truncated ...]')}")
            continue

        indent = "  " * comment["depth"]
        label = "Comment" if comment["depth"] == 0 else "Reply"
        op_tag = colored(" [OP]", "cyan") if comment.get("is_op") else ""

        print(
            f"{indent}{bold(f'{label} {comment[\"hierarchy\"]}')} "
            f"by {comment['author']}{op_tag} ({comment['score']}↑)"
        )

        if show_body and comment.get("body"):
            for line in comment["body"].split('\n'):
                print(f"{indent}  {line}")
            print()

        if comment.get("id"):
            print(f"{indent}  {dim(f'ID: {comment[\"id\"]}')}")

        render_indented(comment.get("replies", []), show_body=show_body)


# ══════════════════════════════════════════════════════════════
# Section 4: Analytics Display
# ══════════════════════════════════════════════════════════════

def render_analytics(analytics: dict) -> None:
    """
    Render thread analytics to the terminal.

    Args:
        analytics: Dictionary of thread statistics
    """
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

    print(bold("═" * 50))


# ══════════════════════════════════════════════════════════════
# Section 5: Main Entry Point
# ══════════════════════════════════════════════════════════════

def main(argv: Optional[list] = None) -> int:
    """
    Main entry point for the CLI application.

    Args:
        argv: Optional argument list (for testing). Uses sys.argv if None.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    args = parse_args(argv)

    # ── Configure logging ──
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Handle --about ──
    if args.about:
        print_about()
        return 0

    # ── Load configuration ──
    try:
        app_config = load_config()
    except Exception as e:
        print(colored(f"\n✗ Configuration error: {e}", "red"))
        return 1

    # ── Build scraper config from CLI args ──
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

    # ── Connect to Reddit ──
    try:
        print(dim("\n⏳ Connecting to Reddit API..."))
        reddit = create_reddit_instance(app_config.credentials)
    except EnvironmentError as e:
        print(colored(f"\n✗ {e}", "red"))
        return 1
    except ConnectionError as e:
        print(colored(f"\n✗ Connection failed: {e}", "red"))
        return 1

    # ── Fetch post ──
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

    # ── Extract post metadata ──
    post_meta = extract_post_metadata(post)

    # ── Build comment tree ──
    print(dim("⏳ Building comment tree..."))
    tree = build_comment_tree(post.comments, config=scraper_config)

    # ── Assign IDs ──
    id_gen = CommentIDGenerator(base_length=scraper_config.id_base_length)
    assign_ids(tree, id_gen)

    # ── Compute analytics ──
    analytics = analyze_thread(tree)

    # ── Output ──
    show_body = not args.no_body

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
        render_indented(tree, show_body=show_body)
        if not args.no_analytics:
            render_analytics(analytics)

    else:  # tree (default)
        _print_post_header(post_meta, id_gen)
        render_tree(tree, show_body=show_body)
        if not args.no_analytics:
            render_analytics(analytics)

    return 0


def _print_post_header(post_meta: dict, id_gen: CommentIDGenerator) -> None:
    """Print the post header section to the terminal."""
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


# ══════════════════════════════════════════════════════════════
# Guard: Script Entry Point
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    sys.exit(main())