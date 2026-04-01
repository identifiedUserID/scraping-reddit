"""
══════════════════════════════════════════════════════════════
Flask Backend Server
══════════════════════════════════════════════════════════════
Provides a REST API for the HTML frontend to fetch and process
Reddit threads. Handles all Reddit API interaction server-side
to keep credentials secure.

Endpoints:
    GET  /              → Serve the HTML frontend
    POST /api/fetch     → Fetch and process a Reddit thread
    GET  /api/health    → Health check
══════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import logging
import time
from typing import Optional

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

from config import load_config
from scraper import (
    create_reddit_instance,
    fetch_post,
    build_comment_tree,
    assign_ids,
    extract_post_metadata,
    analyze_thread,
    ScraperConfig,
)
from utils import CommentIDGenerator, validate_reddit_url

# ══════════════════════════════════════════════════════════════
# Application Setup
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ── Global State ──
_reddit_instance = None
_app_config = None


def get_reddit():
    """
    Lazily initialize and cache the Reddit instance.

    Returns:
        praw.Reddit instance

    Raises:
        RuntimeError if credentials are missing
    """
    global _reddit_instance, _app_config

    if _reddit_instance is None:
        _app_config = load_config()
        _reddit_instance = create_reddit_instance(_app_config.credentials)
        logger.info("Reddit instance initialized")

    return _reddit_instance


# ══════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Serve the HTML frontend."""
    return send_from_directory('.', 'index.html')


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    try:
        reddit = get_reddit()
        return jsonify({
            "status": "ok",
            "reddit_connected": True,
            "read_only": reddit.read_only,
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "reddit_connected": False,
            "error": str(e),
        }), 503


@app.route("/api/fetch", methods=["POST"])
def fetch_thread():
    """
    Fetch and process a Reddit thread.

    Request JSON body:
        {
            "url": "https://www.reddit.com/r/.../comments/.../...",
            "depth": 10,           (optional, default 10)
            "sort": "best",        (optional, default "best")
            "min_score": null,     (optional)
            "skip_deleted": false, (optional)
            "more_limit": 0        (optional, default 0)
        }

    Response JSON:
        {
            "post": { ... },
            "comments": [ ... ],
            "analytics": { ... },
            "thread_id": "A7X9K2",
            "fetch_time_ms": 1234
        }
    """
    start_time = time.time()

    # ── Parse request ──
    data = request.get_json(silent=True)
    if not data:
        return _error_response("Request body must be JSON", 400)

    url = data.get("url", "").strip()
    if not url:
        return _error_response("'url' field is required", 400)

    # ── Validate URL ──
    try:
        validated_url = validate_reddit_url(url)
    except ValueError as e:
        return _error_response(str(e), 400)

    # ── Build scraper config ──
    try:
        scraper_config = ScraperConfig(
            max_depth=_clamp(data.get("depth", 10), 1, 50),
            min_score=data.get("min_score"),
            comment_sort=data.get("sort", "best"),
            more_comments_limit=_clamp(data.get("more_limit", 0), -1, 100),
            skip_deleted=bool(data.get("skip_deleted", False)),
            max_body_length=data.get("max_body_length"),
        )
        scraper_config.validate()
    except ValueError as e:
        return _error_response(f"Invalid configuration: {e}", 400)

    # ── Fetch and process ──
    try:
        reddit = get_reddit()
    except (EnvironmentError, ConnectionError) as e:
        return _error_response(f"Reddit connection failed: {e}", 503)

    try:
        post = fetch_post(reddit, validated_url, scraper_config)
    except ValueError as e:
        return _error_response(str(e), 400)
    except PermissionError as e:
        return _error_response(str(e), 403)
    except ConnectionError as e:
        return _error_response(str(e), 503)
    except Exception as e:
        logger.exception("Unexpected error fetching post")
        return _error_response(f"Unexpected error: {e}", 500)

    try:
        # Extract metadata
        post_meta = extract_post_metadata(post)

        # Build tree
        tree = build_comment_tree(post.comments, config=scraper_config)

        # Assign IDs
        id_gen = CommentIDGenerator()
        assign_ids(tree, id_gen)

        # Analytics
        analytics = analyze_thread(tree)

        elapsed_ms = int((time.time() - start_time) * 1000)

        return jsonify({
            "post": post_meta,
            "comments": tree,
            "analytics": analytics,
            "thread_id": id_gen.thread_id,
            "fetch_time_ms": elapsed_ms,
        })

    except Exception as e:
        logger.exception("Unexpected error processing comments")
        return _error_response(f"Error processing comments: {e}", 500)


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════

def _error_response(message: str, status_code: int) -> tuple[Response, int]:
    """Create a standardized error response."""
    logger.warning(f"API error ({status_code}): {message}")
    return jsonify({"error": message}), status_code


def _clamp(value, min_val, max_val):
    """Clamp a numeric value between min and max."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return min_val
    return max(min_val, min(value, max_val))


# ══════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        config = load_config()

        # Validate credentials before starting server
        config.credentials.validate()
        logger.info("Credentials validated")

        # Pre-initialize Reddit connection
        get_reddit()

        print(f"\n{'='*50}")
        print(f"  Reddit Discussion Explorer — Server")
        print(f"{'='*50}")
        print(f"  URL:  http://localhost:{config.server.port}")
        print(f"  API:  http://localhost:{config.server.port}/api/fetch")
        print(f"{'='*50}\n")

        app.run(
            host="0.0.0.0",
            port=config.server.port,
            debug=config.server.debug,
        )

    except EnvironmentError as e:
        print(f"\n❌ Configuration Error:\n{e}")
        sys.exit(1)
    except ConnectionError as e:
        print(f"\n❌ Connection Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Startup Error: {e}")
        logger.exception("Failed to start server")
        sys.exit(1)