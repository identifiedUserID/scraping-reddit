"""
══════════════════════════════════════════════════════════════
Flask Backend Server — Version 2
══════════════════════════════════════════════════════════════
REST API for the HTML frontend. Now includes sentiment data,
user analytics, engagement duration, and TXT export endpoint.

Endpoints:
    GET  /              → Serve the HTML frontend
    POST /api/fetch     → Fetch and process a Reddit thread
    GET  /api/health    → Health check
    POST /api/export/txt → Generate and return TXT export
══════════════════════════════════════════════════════════════
"""

import os
import sys
import logging
import time
from io import StringIO

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
    export_txt,
    ScraperConfig,
)
from utils import CommentIDGenerator, validate_reddit_url, format_timestamp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

_reddit_instance = None
_app_config = None


def get_reddit():
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
    return send_from_directory('.', 'index.html')


@app.route("/api/health", methods=["GET"])
def health_check():
    try:
        reddit = get_reddit()
        return jsonify({
            "status": "ok",
            "reddit_connected": True,
            "read_only": reddit.read_only,
            "version": 2,
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
    Now returns sentiment data, user analytics, and engagement duration.
    """
    start_time = time.time()

    data = request.get_json(silent=True)
    if not data:
        return _error_response("Request body must be JSON", 400)

    url = data.get("url", "").strip()
    if not url:
        return _error_response("'url' field is required", 400)

    try:
        validated_url = validate_reddit_url(url)
    except ValueError as e:
        return _error_response(str(e), 400)

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
        post_meta = extract_post_metadata(post)
        tree = build_comment_tree(post.comments, config=scraper_config)

        id_gen = CommentIDGenerator()
        assign_ids(tree, id_gen)

        analytics = analyze_thread(tree, post_meta=post_meta)

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


@app.route("/api/export/txt", methods=["POST"])
def export_txt_endpoint():
    """
    Generate a TXT export from previously fetched data.
    Accepts the same data structure returned by /api/fetch.
    """
    data = request.get_json(silent=True)
    if not data:
        return _error_response("Request body must be JSON", 400)

    post_meta = data.get("post")
    tree = data.get("comments")
    analytics = data.get("analytics")

    if not post_meta or not tree or not analytics:
        return _error_response("Missing 'post', 'comments', or 'analytics' in request body", 400)

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp:
            filepath = tmp.name

        export_txt(post_meta, tree, analytics, filepath)

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        os.unlink(filepath)

        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename=reddit_thread_{data.get("thread_id", "export")}.txt'}
        )

    except Exception as e:
        logger.exception("Error generating TXT export")
        return _error_response(f"Export error: {e}", 500)


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════

def _error_response(message: str, status_code: int) -> tuple:
    logger.warning(f"API error ({status_code}): {message}")
    return jsonify({"error": message}), status_code


def _clamp(value, min_val, max_val):
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
        config.credentials.validate()
        logger.info("Credentials validated")
        get_reddit()

        print(f"\n{'='*50}")
        print(f"  Reddit Discussion Explorer v2 — Server")
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