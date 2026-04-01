#!/usr/bin/env bash
# ══════════════════════════════════════════════
# Reddit Discussion Explorer — Launcher (Unix)
# ══════════════════════════════════════════════

set -e

echo "=========================================="
echo "  Reddit Discussion Explorer - Launcher"
echo "=========================================="
echo ""

# Check Python
if ! command -v py &> /dev/null; then
    echo "[ERROR] Python 3 is not installed."
    echo "Install it via your package manager (e.g., sudo apt install python3)"
    exit 1
fi

# Create venv if needed
if [ ! -d "venv" ]; then
    echo "[INFO] Creating virtual environment..."
    py -m venv venv
fi

# Activate
source venv/bin/activate

# Install deps
echo "[INFO] Installing dependencies..."
py -m pip install -r requirements.txt --quiet

# Check .env
if [ ! -f ".env" ]; then
    echo ""
    echo "[WARNING] No .env file found!"
    echo "Please copy .env.example to .env and add your Reddit API credentials."
    echo ""
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "[INFO] Copied .env.example to .env — please edit it."
        echo ""
    fi
    read -p "Press Enter to continue after editing .env..."
fi

echo ""
echo "[INFO] Starting server at http://localhost:5000"
echo ""

# Open browser (background, non-blocking)
(sleep 2 && py -c "import webbrowser; webbrowser.open('http://localhost:5000')") &

# Start server
py server.py