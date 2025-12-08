#!/usr/bin/env python3
"""Claude Chat Search - A simple webapp to search Claude Code conversation history."""

import json
import os
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DB_PATH = Path(__file__).parent / "search.db"

# Indexing state
indexing_status = {"running": False, "progress": 0, "total": 0, "error": None}


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database with FTS5 table."""
    conn = get_db()
    conn.executescript("""
        DROP TABLE IF EXISTS messages;
        DROP TABLE IF EXISTS metadata;

        CREATE VIRTUAL TABLE messages USING fts5(
            session_id,
            timestamp,
            role,
            content,
            project,
            file_path,
            tokenize='porter'
        );

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()


def extract_project_name(folder_name: str) -> str:
    """Extract readable project name from folder path.

    Claude stores projects in folders like: -Users-USERNAME-code-PROJECTNAME
    (absolute path with '-' replacing '/'). Extracts portion after 'code'.
    """
    parts = folder_name.split("-")
    # Find 'code' and take everything after it
    if "code" in parts:
        idx = parts.index("code")
        return "-".join(parts[idx + 1:]) if idx + 1 < len(parts) else folder_name
    # Otherwise take the last part
    return parts[-1] if parts else folder_name


def extract_text_content(content) -> str:
    """Extract text from message content (can be string or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "document":
                    source = block.get("source", {})
                    if source.get("type") == "text":
                        texts.append(source.get("data", ""))
            elif isinstance(block, str):
                texts.append(block)
        return "\n".join(texts)
    return ""


def index_jsonl_file(file_path: Path, conn: sqlite3.Connection) -> int:
    """Index a single JSONL file, returning number of messages indexed."""
    count = 0
    project = extract_project_name(file_path.parent.name)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line.strip())
                    msg_type = obj.get("type")

                    # Only index user and assistant messages
                    if msg_type not in ("user", "assistant"):
                        continue

                    message = obj.get("message", {})
                    role = message.get("role", msg_type)
                    content = extract_text_content(message.get("content", ""))

                    if not content.strip():
                        continue

                    session_id = obj.get("sessionId", file_path.stem)
                    timestamp = obj.get("timestamp", "")

                    conn.execute(
                        "INSERT INTO messages (session_id, timestamp, role, content, project, file_path) VALUES (?, ?, ?, ?, ?, ?)",
                        (session_id, timestamp, role, content, project, str(file_path))
                    )
                    count += 1
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading {file_path}: {e}")

    return count


def run_indexer():
    """Run the full indexer."""
    global indexing_status

    indexing_status = {"running": True, "progress": 0, "total": 0, "error": None}

    try:
        # Find all JSONL files
        jsonl_files = list(CLAUDE_PROJECTS_DIR.glob("**/*.jsonl"))
        indexing_status["total"] = len(jsonl_files)

        # Initialize fresh database
        init_db()
        conn = get_db()

        total_messages = 0
        for i, file_path in enumerate(jsonl_files):
            total_messages += index_jsonl_file(file_path, conn)
            indexing_status["progress"] = i + 1

            # Commit every 50 files
            if (i + 1) % 50 == 0:
                conn.commit()

        # Save metadata
        conn.commit()
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("last_indexed", datetime.now().isoformat())
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("message_count", str(total_messages))
        )
        conn.commit()
        conn.close()

        indexing_status["running"] = False
        print(f"Indexed {total_messages} messages from {len(jsonl_files)} files")

    except Exception as e:
        indexing_status["error"] = str(e)
        indexing_status["running"] = False
        print(f"Indexing error: {e}")


@app.route("/")
def index():
    """Serve the search UI."""
    return render_template("index.html")


@app.route("/search")
def search():
    """Search messages."""
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 50)), 200)

    if not query:
        return jsonify({"results": [], "query": query})

    conn = get_db()

    # Use FTS5 match syntax
    # Escape special characters and add wildcards for partial matching
    safe_query = re.sub(r'[^\w\s]', ' ', query)
    fts_query = " ".join(f"{word}*" for word in safe_query.split() if word)

    try:
        results = conn.execute("""
            SELECT
                session_id,
                timestamp,
                role,
                snippet(messages, 3, '<mark>', '</mark>', '...', 64) as snippet,
                project,
                file_path
            FROM messages
            WHERE messages MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, limit)).fetchall()

        return jsonify({
            "results": [dict(r) for r in results],
            "query": query,
            "count": len(results)
        })
    except sqlite3.OperationalError as e:
        return jsonify({"results": [], "query": query, "error": str(e)})
    finally:
        conn.close()


@app.route("/conversation/<session_id>")
def conversation(session_id):
    """Get full conversation by session ID."""
    conn = get_db()

    results = conn.execute("""
        SELECT session_id, timestamp, role, content, project, file_path
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp
    """, (session_id,)).fetchall()

    conn.close()

    return jsonify({
        "session_id": session_id,
        "messages": [dict(r) for r in results]
    })


@app.route("/status")
def status():
    """Get index status."""
    if not DB_PATH.exists():
        return jsonify({
            "indexed": False,
            "last_indexed": None,
            "message_count": 0,
            "indexing": indexing_status
        })

    conn = get_db()
    try:
        last_indexed = conn.execute(
            "SELECT value FROM metadata WHERE key = 'last_indexed'"
        ).fetchone()
        message_count = conn.execute(
            "SELECT value FROM metadata WHERE key = 'message_count'"
        ).fetchone()

        return jsonify({
            "indexed": True,
            "last_indexed": last_indexed[0] if last_indexed else None,
            "message_count": int(message_count[0]) if message_count else 0,
            "indexing": indexing_status
        })
    except sqlite3.OperationalError:
        return jsonify({
            "indexed": False,
            "last_indexed": None,
            "message_count": 0,
            "indexing": indexing_status
        })
    finally:
        conn.close()


@app.route("/reindex", methods=["POST"])
def reindex():
    """Trigger reindexing."""
    if indexing_status["running"]:
        return jsonify({"status": "already_running"})

    thread = threading.Thread(target=run_indexer)
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started"})


if __name__ == "__main__":
    # Auto-index on first run if no database exists
    if not DB_PATH.exists():
        print("No index found. Building index...")
        run_indexer()

    print(f"Starting server on http://localhost:9000")
    app.run(host="127.0.0.1", port=9000, debug=False)
