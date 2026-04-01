# 🔍 Reddit Discussion Explorer v2

A tool for fetching, analyzing, and visualizing Reddit comment threads with hierarchical tree rendering, **sentiment analysis**, **per-user analytics**, engagement duration tracking, and multiple export formats including human-readable TXT.

## What's New in v2

- **Sentiment Analysis** — Keyword lexicon with 500+ positive/negative words, negation handling, and intensity modifiers
- **Per-User Analytics Sidebar** — Click any username to see their stats: total score, word count, vocabulary richness, top words (stopwords removed), sentiment profile
- **Engagement Duration** — Shows total discussion timespan (Years, Months, Days, Hours, Minutes — zeros omitted)
- **TXT Export** — Human-readable plain text format optimized for LLM consumption (not token-heavy like JSON)
- **Table View** — Sortable tabular view alongside the tree view
- **Quick Jump Bar** — One-click navigation to top-scoring comments
- **Sentiment Tooltips** — Click sentiment indicators to see positive/negative word breakdowns
- **Interactive User Sidebar** — Dedicated panel showing per-user word frequencies, vocabulary richness, comment locations

## Quick Start

### 1. Get Reddit API Credentials
1. Go to https://www.reddit.com/prefs/apps/
2. Click **"create another app..."**, select **"script"**
3. Note the **client ID** and **client secret**

### 2. Setup
```bash
cp .env.example .env
# Edit .env with your credentials
pip install -r requirements.txt
```

### 3. Run — Web UI
```bash
python server.py
# Open http://localhost:5000
```

### 4. Run — CLI
```bash
python cli.py -u <reddit_url>
python cli.py -u <url> --format txt --output thread.txt
python cli.py -u <url> --depth 5 --sort top --min-score 10
```

## Export Formats

| Format | Command | Best For |
|--------|---------|----------|
| Tree | `--format tree` (default) | Terminal reading |
| JSON | `--format json` | Programmatic use |
| CSV | `--format csv` | Spreadsheets |
| TXT | `--format txt` | LLM input, archival |

## TXT Export Format
```
Title of Post
CMV: Cultures should not be immune from criticism.

Body of Post
As the title of my post asserts...

NOTE: This post has 221 upvotes and has 33 replies.

Total Length of Engagement: 2 Days, 14 Hours, 23 Minutes

Comment replies to post:

-------------------------------
Comment ID: LJ661Z-1 (Comment 1 by user123 (9 upvotes)):
Comment text here...
[Sentiment: positive (0.2341)]

Reply 1.1 by user456 (-1 upvotes)):
Reply text...
[Sentiment: negative (-0.1523)]

=================================================================
THREAD ANALYTICS
=================================================================
  Total Comments: 33
  ...

-----------------------------------------------------------------
SENTIMENT ANALYSIS
-----------------------------------------------------------------
  Overall Sentiment: neutral
  ...

-----------------------------------------------------------------
USER ANALYTICS
-----------------------------------------------------------------
  User: user123 [OP]
    Comments: 5
    Total Score: 42
    ...
    Top Words: culture(8), criticism(5), practice(4)
```

## Architecture
```
┌──────────────┐     ┌──────────────┐     ┌───────────┐
│  index.html  │────▶│  server.py   │────▶│  Reddit   │
│  (Frontend)  │◀────│  (Flask API) │◀────│   API     │
└──────────────┘     └──────┬───────┘     └───────────┘
                            │
                    ┌───────┴───────┐
                    │  scraper.py   │ ← sentiment, user analytics
                    │  utils.py     │ ← lexicon, stopwords, duration
                    │  config.py    │
                    └───────────────┘
```

## License
MIT