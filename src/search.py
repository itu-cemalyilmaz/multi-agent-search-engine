"""
Search Module (Backend Developer Agent)
========================================
Implements the search(query) function using SQLite FTS5.

Relevancy: Uses SQLite FTS5's built-in BM25 (Best Match 25) algorithm.
  - BM25 is the industry-standard term-frequency × inverse-document-frequency
    ranking function (same algorithm used by Elasticsearch by default).
  - `rank` is a negative float: more negative = more relevant.
  - We convert it to a 0–100 relevance score for display.

Safe to call while the crawler is actively writing (WAL mode allows
concurrent readers and writers without blocking each other).
"""

from src.db import get_db_connection
from src.crawler import status as crawler_status


def search(query: str) -> list[tuple[str, str, int, float]]:
    """
    Given a text query, returns relevant indexed URLs ranked by BM25.

    Returns:
        List of (relevant_url, origin_url, depth, relevance_score) tuples.
        relevance_score is a 0.0–100.0 float (higher = more relevant).
    """
    if not query or not query.strip():
        return []

    # Sanitise query for FTS5 – keep only alphanumeric and spaces,
    # then wrap each token in double quotes to avoid FTS5 syntax errors.
    tokens = []
    for word in query.strip().split():
        cleaned = "".join(ch for ch in word if ch.isalnum())
        if cleaned:
            tokens.append(f'"{cleaned}"')

    if not tokens:
        return []

    fts_query = " OR ".join(tokens)

    conn = get_db_connection()
    try:
        # BM25 rank is a negative float (most negative = best match).
        # We ORDER BY rank ASC so the best results come first.
        sql = """
            SELECT f.url, c.origin_url, c.depth, rank
            FROM pages_fts f
            JOIN crawled_pages c ON f.url = c.url
            WHERE pages_fts MATCH ?
            ORDER BY rank
            LIMIT 100
        """
        cursor = conn.execute(sql, (fts_query,))
        rows = cursor.fetchall()

        if not rows:
            return []

        # Normalise BM25 scores to a 0–100 human-readable scale.
        # rank values are ≤ 0; the most-negative is the best match.
        raw_scores = [row["rank"] for row in rows]
        min_score = min(raw_scores)   # most relevant (most negative)
        max_score = max(raw_scores)   # least relevant (least negative / 0)
        score_range = (max_score - min_score) or 1.0   # avoid div-by-zero

        results = []
        for row in rows:
            # Map: min_score → 100, max_score → 0
            relevance = ((max_score - row["rank"]) / score_range) * 100.0
            results.append((row["url"], row["origin_url"], row["depth"], round(relevance, 1)))

        return results

    except Exception as e:
        print(f"[Search Error] {e}")
        return []
    finally:
        conn.close()


def get_stats() -> dict:
    """
    Return stats about the indexed data.
    Merges the live in-memory counter with the DB job record so
    'pages' is accurate even while a job is still running.
    """
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM crawled_pages").fetchone()
        total_pages = row["cnt"] if row else 0

        jobs_raw = conn.execute(
            "SELECT id, origin_url, max_depth, status, pages_crawled, created_at "
            "FROM index_jobs ORDER BY created_at DESC LIMIT 10"
        ).fetchall()

        jobs = []
        for i, j in enumerate(jobs_raw):
            d = dict(j)
            # For the most-recent running job, show the live in-memory counter
            # instead of the DB value (which is only written on completion).
            if i == 0 and d["status"] == "running":
                d["pages_crawled"] = crawler_status["pages_crawled"]
                d["note"] = "live"
            jobs.append(d)

        return {
            "total_indexed_pages": total_pages,
            "recent_jobs": jobs,
        }
    finally:
        conn.close()
