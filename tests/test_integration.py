"""
Integration Tests (QA Agent)
=============================
End-to-end tests verifying the crawl → index → search pipeline
and concurrent read/write behavior.
"""

import unittest
import asyncio
import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import init_db, get_db_connection
from src.crawler import index_manager, normalize_url, status as crawler_status
from src.search import search, get_stats


class TestCrawlPipeline(unittest.TestCase):
    """Integration test: crawl a real page and verify search works."""

    TEST_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_integration.db")

    def setUp(self):
        import src.db as db_module
        self._orig_path = db_module.DB_PATH
        db_module.DB_PATH = self.TEST_DB
        init_db()

    def tearDown(self):
        import src.db as db_module
        db_module.DB_PATH = self._orig_path
        for f in [self.TEST_DB, self.TEST_DB + "-wal", self.TEST_DB + "-shm"]:
            if os.path.exists(f):
                os.remove(f)

    def test_crawl_and_search_example_com(self):
        """Crawl example.com at depth 0 and search for 'example'."""
        asyncio.run(index_manager("https://example.com", 0))

        results = search("example")
        self.assertTrue(len(results) > 0, "Expected at least one result for 'example'")

        # Verify 4-tuple format: (relevant_url, origin_url, depth, relevance_score)
        url, origin, depth, score = results[0]
        self.assertIn("example.com", url)
        self.assertEqual(depth, 0)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)

    def test_crawl_records_in_db(self):
        """Verify crawled pages are persisted in the database."""
        asyncio.run(index_manager("https://example.com", 0))

        conn = get_db_connection()
        try:
            count = conn.execute("SELECT COUNT(*) as c FROM crawled_pages").fetchone()
            self.assertGreater(count["c"], 0)
        finally:
            conn.close()

    def test_job_tracking(self):
        """Verify index jobs are recorded and updated."""
        asyncio.run(index_manager("https://example.com", 0))

        conn = get_db_connection()
        try:
            job = conn.execute(
                "SELECT * FROM index_jobs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(job)
            self.assertEqual(job["status"], "completed")
            self.assertIn("example.com", job["origin_url"])
        finally:
            conn.close()

    def test_no_duplicate_crawling(self):
        """Crawl the same URL twice and verify no duplicates."""
        asyncio.run(index_manager("https://example.com", 0))
        asyncio.run(index_manager("https://example.com", 0))

        conn = get_db_connection()
        try:
            count = conn.execute(
                "SELECT COUNT(*) as c FROM crawled_pages WHERE url LIKE '%example.com%'"
            ).fetchone()
            # Should still be only 1 entry for example.com root
            self.assertEqual(count["c"], 1)
        finally:
            conn.close()

    def test_get_stats(self):
        """Verify get_stats returns correct data."""
        asyncio.run(index_manager("https://example.com", 0))
        stats = get_stats()
        self.assertGreater(stats["total_indexed_pages"], 0)
        self.assertTrue(len(stats["recent_jobs"]) > 0)


class TestConcurrentSearchDuringCrawl(unittest.TestCase):
    """Verify search can run while indexing is active (WAL mode test)."""

    TEST_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_concurrent.db")

    def setUp(self):
        import src.db as db_module
        self._orig_path = db_module.DB_PATH
        db_module.DB_PATH = self.TEST_DB
        init_db()

    def tearDown(self):
        import src.db as db_module
        db_module.DB_PATH = self._orig_path
        for f in [self.TEST_DB, self.TEST_DB + "-wal", self.TEST_DB + "-shm"]:
            if os.path.exists(f):
                os.remove(f)

    def test_search_during_indexing(self):
        """Start indexing in a thread and perform searches concurrently."""
        from src.crawler import start_indexing

        errors = []

        def run_indexer():
            try:
                start_indexing("https://example.com", 1)
            except Exception as e:
                errors.append(f"Indexer error: {e}")

        # Start indexer in background
        t = threading.Thread(target=run_indexer, daemon=True)
        t.start()

        # Give it a moment to start
        time.sleep(1)

        # Perform multiple searches while indexing runs
        for _ in range(5):
            try:
                results = search("example")
                # Results may or may not be found depending on timing
                # The key test is that no OperationalError (database locked) is raised
            except Exception as e:
                errors.append(f"Search error: {e}")
            time.sleep(0.5)

        t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Concurrent errors: {errors}")


if __name__ == "__main__":
    unittest.main()
