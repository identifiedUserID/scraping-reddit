# 🔍 Reddit Discussion Explorer

A tool for fetching, analyzing, and visualizing Reddit comment threads with hierarchical tree rendering, analytics, and export capabilities.

## Features

- **Hierarchical Comment Tree** — Comments displayed as `1`, `1.1`, `1.1.1`, etc.
- **Collision-Free IDs** — Each comment gets a unique ID like `A7X9K2-1.2.3`
- **Web UI** — Dark/light mode, expand/collapse, search, breadcrumb navigation
- **CLI** — Full command-line interface with tree/indent/JSON/CSV/TXT output
- **Analytics** — Total comments, avg score, max depth, unique authors, etc.
- **Filtering** — Min score, skip deleted, sort order
- **Export** — JSON, CSV, and TXT export from both CLI and web UI

## Quick Start

### 1. Get Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps/
2. Click **"create another app..."**
3. Select **"script"**, name it, set redirect URI to `http://localhost:8080`
4. Note the **client ID** (under app name) and **client secret**

### 2. Setup

```bash
# Clone the project
git clone <your-repo-url>
cd reddit-explorer

# Copy and edit credentials
cp .env.example .env
# Edit .env with your credentials

# Install dependencies
pip install -r requirements.txt
```

### 3. Run — Web UI

**Windows:**
```cmd
start.bat
```

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

**Manual:**
```bash
python server.py
# Open http://localhost:5000
```

### 4. Run — CLI

```bash
# Basic usage
python cli.py --url https://www.reddit.com/r/AskReddit/comments/abc123/title/

# With options
python cli.py -u <url> --depth 5 --sort top --min-score 10

# Export to JSON
python cli.py -u <url> --format json --output thread.json

# Export to CSV
python cli.py -u <url> --format csv

# Simple indented view
python cli.py -u <url> --format indent --no-body

# Show help
python cli.py --help

# Show about
python cli.py --about
```

## CLI Options

| Flag | Short | Description | Default |
|---|---|---|---|
| `--url` | `-u` | Reddit post URL | Required |
| `--depth` | `-d` | Max reply depth | 10 |
| `--sort` | `-s` | Sort order | best |
| `--format` | `-f` | Output format | tree |
| `--output` | `-o` | Output file path | auto |
| `--min-score` | | Minimum comment score | None |
| `--skip-deleted` | | Skip deleted comments | False |
| `--more-comments` | `-m` | Expand MoreComments | 0 |
| `--max-body-length` | | Truncate bodies | None |
| `--no-body` | | Hide comment bodies | False |
| `--no-analytics` | | Hide analytics | False |
| `--verbose` | `-v` | Debug logging | False |
| `--about` | | Show tool info | |

## Project Structure

```
reddit-explorer/
├── server.py           # Flask backend
├── scraper.py          # Core scraping & processing
├── config.py           # Configuration management
├── utils.py            # Utilities (formatting, validation, IDs)
├── cli.py              # Command-line interface
├── index.html          # Web frontend
├── start.bat           # Windows launcher
├── start.sh            # Unix launcher
├── requirements.txt    # Dependencies
├── .env.example        # Credential template
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌───────────┐
│  index.html  │────▶│  server.py   │────▶│  Reddit   │
│  (Frontend)  │◀────│  (Flask API) │◀────│   API     │
└──────────────┘     └──────┬───────┘     └───────────┘
                            │
                    ┌───────┴───────┐
                    │  scraper.py   │
                    │  config.py    │
                    │  utils.py     │
                    └───────────────┘

┌──────────────┐
│   cli.py     │ (Same scraper.py, direct to terminal)
└──────────────┘
```

## Security

- **Never commit `.env` files** — they're in `.gitignore`
- Credentials are loaded from environment variables only
- The server keeps credentials server-side; the frontend never sees them
- No authentication tokens are exposed to the browser

## License

MIT
