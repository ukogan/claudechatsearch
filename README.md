# Claude Chat Search

A lightweight webapp to search through your Claude Code conversation history.

## Features

- Full-text search across all Claude Code conversations
- Instant results with highlighted snippets
- Click to expand full conversation
- Index status with one-click reindex
- macOS Dock app for quick access

## Installation

### Prerequisites

- Python 3.8+
- Flask (`pip3 install flask`)

### Quick Start

```bash
# Clone or download this repository
git clone <repo-url>
cd claude_search

# Install dependencies
pip3 install -r requirements.txt

# Run the server (auto-indexes on first run)
python3 app.py
```

Open http://localhost:9000 in your browser.

### macOS Dock App

To launch from the Dock:

1. In Finder, navigate to the `claude_search` folder
2. Drag `Claude Search.app` directly to your Dock
3. Click to launch (starts server if needed, opens browser)

**Note:** Keep `Claude Search.app` in the same folder as `app.py` — it locates the server code relative to itself.

## Usage

1. Type in the search box to find conversations
2. Results show project name, date, and matching snippet
3. Click a result to view the full conversation
4. Use "Reindex" button to update the index after new conversations

## Data Location

The app indexes Claude Code conversations stored in:
```
~/.claude/projects/**/*.jsonl
```

The search index is stored locally in `search.db` (SQLite).
