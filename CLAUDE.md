# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Claude Chat Search - A Flask webapp that indexes and searches Claude Code conversation history stored in `~/.claude/projects/`.

## Commands

```bash
# Run the server (auto-indexes on first run)
python3 app.py

# Server runs on http://localhost:9000
```

## Architecture

**Single-file Flask app** with SQLite FTS5 for full-text search.

- `app.py` - Server, indexer, and all API endpoints
- `templates/index.html` - Single-page search UI with vanilla JS
- `search.db` - SQLite database with FTS5 virtual table (generated)
- `Claude Search.app` - macOS app bundle for Dock launch

**Data Flow:**
1. Indexer scans `~/.claude/projects/**/*.jsonl`
2. Extracts user/assistant messages from JSONL format
3. Stores in FTS5 table with porter stemming
4. Web UI queries via `/search?q=` endpoint

**Key Functions:**
- `extract_project_name(folder_name)` - Generates readable project name from Claude's folder path format. Claude stores projects in folders named like `-Users-USERNAME-code-PROJECTNAME` (absolute path with `-` replacing `/`). This function extracts the portion after `code` to get `PROJECTNAME`.
- `extract_text_content(content)` - Handles Claude's message content format which can be either a plain string or an array of content blocks (text, document, etc.)
- `run_indexer()` - Background thread that scans all JSONL files and rebuilds the FTS5 index

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Search UI |
| `/search?q=<query>` | GET | JSON search results with snippets |
| `/conversation/<session_id>` | GET | Full conversation messages |
| `/status` | GET | Index age and message count |
| `/reindex` | POST | Trigger background reindex |
