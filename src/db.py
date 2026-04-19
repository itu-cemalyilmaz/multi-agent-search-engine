"""
Database Module (Systems Architect Agent)
=========================================
Manages SQLite connection using WAL mode for concurrent read/write access.
Uses FTS5 virtual tables for full-text search capability.
Provides persistence for crash-recovery: unvisited URLs are stored in a
frontier table so that crawling can resume after interruption.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.db")


def get_db_connection():
    """
    Returns a new connection to the SQLite database.
    Configures WAL mode so readers (search) never block writers (crawler).
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes all required tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # ----------------------------------------------------------
        # 1. crawled_pages – stores fetched pages with metadata
        # ----------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawled_pages (
                url           TEXT PRIMARY KEY,
                origin_url    TEXT NOT NULL,
                depth         INTEGER NOT NULL,
                content       TEXT DEFAULT ''
            )
        """)

        # ----------------------------------------------------------
        # 2. frontier – URLs waiting to be crawled (for resume)
        # ----------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS frontier (
                url           TEXT PRIMARY KEY,
                origin_url    TEXT NOT NULL,
                depth         INTEGER NOT NULL,
                max_depth     INTEGER NOT NULL
            )
        """)

        # ----------------------------------------------------------
        # 3. FTS5 virtual table for full-text search
        # ----------------------------------------------------------
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
                url UNINDEXED,
                content
            )
        """)

        # ----------------------------------------------------------
        # 4. Triggers to keep FTS in sync with crawled_pages
        # ----------------------------------------------------------
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_pages_insert
            AFTER INSERT ON crawled_pages BEGIN
                INSERT INTO pages_fts(url, content) VALUES (new.url, new.content);
            END;
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_pages_delete
            AFTER DELETE ON crawled_pages BEGIN
                INSERT INTO pages_fts(pages_fts, url, content)
                    VALUES('delete', old.url, old.content);
            END;
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_pages_update
            AFTER UPDATE ON crawled_pages BEGIN
                INSERT INTO pages_fts(pages_fts, url, content)
                    VALUES('delete', old.url, old.content);
                INSERT INTO pages_fts(url, content) VALUES (new.url, new.content);
            END;
        """)

        # ----------------------------------------------------------
        # 5. Index jobs – track each index() invocation
        # ----------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS index_jobs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                origin_url    TEXT NOT NULL,
                max_depth     INTEGER NOT NULL,
                status        TEXT NOT NULL DEFAULT 'running',
                pages_crawled INTEGER NOT NULL DEFAULT 0,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
    finally:
        conn.close()


def reset_db():
    """Drops all data and reinitializes the schema."""
    conn = get_db_connection()
    try:
        conn.execute("DROP TABLE IF EXISTS crawled_pages")
        conn.execute("DROP TABLE IF EXISTS frontier")
        conn.execute("DROP TABLE IF EXISTS pages_fts")
        conn.execute("DROP TABLE IF EXISTS index_jobs")
        conn.commit()
    finally:
        conn.close()
    init_db()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
