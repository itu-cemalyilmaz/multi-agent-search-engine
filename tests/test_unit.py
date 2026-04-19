"""
Unit Tests (QA Agent)
======================
Tests for URL normalization, HTML parsing, search query handling,
and database operations.
"""

import unittest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.crawler import normalize_url, LinkExtractor
from src.db import init_db, get_db_connection, DB_PATH


class TestUrlNormalization(unittest.TestCase):
    """Test the normalize_url function for deduplication accuracy."""

    def test_strip_fragment(self):
        self.assertEqual(
            normalize_url("https://example.com/page#section"),
            normalize_url("https://example.com/page"),
        )

    def test_strip_trailing_slash(self):
        self.assertEqual(
            normalize_url("https://example.com/page/"),
            normalize_url("https://example.com/page"),
        )

    def test_lowercase_scheme_and_host(self):
        self.assertEqual(
            normalize_url("HTTPS://EXAMPLE.COM/Page"),
            "https://example.com/Page",
        )

    def test_default_http_port(self):
        self.assertEqual(
            normalize_url("http://example.com:80/page"),
            normalize_url("http://example.com/page"),
        )

    def test_default_https_port(self):
        self.assertEqual(
            normalize_url("https://example.com:443/page"),
            normalize_url("https://example.com/page"),
        )

    def test_non_default_port_preserved(self):
        result = normalize_url("https://example.com:8080/page")
        self.assertIn("8080", result)

    def test_query_params_preserved(self):
        result = normalize_url("https://example.com/page?q=test&lang=en")
        self.assertIn("q=test", result)
        self.assertIn("lang=en", result)

    def test_root_path(self):
        result = normalize_url("https://example.com")
        self.assertEqual(result, "https://example.com/")


class TestLinkExtractor(unittest.TestCase):
    """Test the HTML parser for link and text extraction."""

    def test_extract_absolute_links(self):
        html = '<html><body><a href="https://example.com/about">About</a></body></html>'
        ext = LinkExtractor("https://example.com/")
        ext.feed(html)
        self.assertEqual(len(ext.links), 1)
        self.assertIn("example.com/about", ext.links[0])

    def test_extract_relative_links(self):
        html = '<html><body><a href="/contact">Contact</a></body></html>'
        ext = LinkExtractor("https://example.com/page")
        ext.feed(html)
        self.assertEqual(len(ext.links), 1)
        self.assertIn("example.com/contact", ext.links[0])

    def test_skip_non_http_links(self):
        html = '<html><body><a href="mailto:a@b.com">Email</a><a href="javascript:void(0)">JS</a></body></html>'
        ext = LinkExtractor("https://example.com/")
        ext.feed(html)
        self.assertEqual(len(ext.links), 0)

    def test_extract_text_content(self):
        html = '<html><body><p>Hello World</p></body></html>'
        ext = LinkExtractor("https://example.com/")
        ext.feed(html)
        self.assertIn("Hello World", ext.get_text())

    def test_skip_script_text(self):
        html = '<html><body><script>var x = 1;</script><p>Visible</p></body></html>'
        ext = LinkExtractor("https://example.com/")
        ext.feed(html)
        text = ext.get_text()
        self.assertIn("Visible", text)
        self.assertNotIn("var x", text)

    def test_skip_style_text(self):
        html = '<html><body><style>.red{color:red}</style><p>Styled</p></body></html>'
        ext = LinkExtractor("https://example.com/")
        ext.feed(html)
        text = ext.get_text()
        self.assertIn("Styled", text)
        self.assertNotIn("color:red", text)

    def test_empty_html(self):
        html = ""
        ext = LinkExtractor("https://example.com/")
        ext.feed(html)
        self.assertEqual(len(ext.links), 0)
        self.assertEqual(ext.get_text(), "")

    def test_multiple_links(self):
        html = """
        <html><body>
            <a href="/a">A</a>
            <a href="/b">B</a>
            <a href="https://other.com/c">C</a>
        </body></html>
        """
        ext = LinkExtractor("https://example.com/")
        ext.feed(html)
        self.assertEqual(len(ext.links), 3)


class TestDatabase(unittest.TestCase):
    """Test database initialization and operations."""

    TEST_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_data.db")

    def setUp(self):
        """Use a separate test database."""
        import src.db as db_module
        self._orig_path = db_module.DB_PATH
        db_module.DB_PATH = self.TEST_DB
        init_db()

    def tearDown(self):
        import src.db as db_module
        db_module.DB_PATH = self._orig_path
        if os.path.exists(self.TEST_DB):
            os.remove(self.TEST_DB)
        # Clean up WAL and SHM files
        for suffix in ("-wal", "-shm"):
            p = self.TEST_DB + suffix
            if os.path.exists(p):
                os.remove(p)

    def test_tables_created(self):
        conn = get_db_connection()
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t["name"] for t in tables]
            self.assertIn("crawled_pages", table_names)
            self.assertIn("frontier", table_names)
            self.assertIn("index_jobs", table_names)
        finally:
            conn.close()

    def test_insert_and_fts_sync(self):
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO crawled_pages (url, origin_url, depth, content) "
                "VALUES (?, ?, ?, ?)",
                ("https://test.com", "https://test.com", 0, "hello world test"),
            )
            conn.commit()

            # The FTS trigger should have populated pages_fts
            row = conn.execute(
                "SELECT url FROM pages_fts WHERE pages_fts MATCH 'hello'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["url"], "https://test.com")
        finally:
            conn.close()

    def test_no_duplicate_urls(self):
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO crawled_pages (url, origin_url, depth, content) "
                "VALUES (?, ?, ?, ?)",
                ("https://dup.com", "https://dup.com", 0, "first"),
            )
            conn.commit()
            conn.execute(
                "INSERT OR IGNORE INTO crawled_pages (url, origin_url, depth, content) "
                "VALUES (?, ?, ?, ?)",
                ("https://dup.com", "https://dup.com", 0, "second"),
            )
            conn.commit()
            cnt = conn.execute("SELECT COUNT(*) as c FROM crawled_pages WHERE url='https://dup.com'").fetchone()
            self.assertEqual(cnt["c"], 1)
        finally:
            conn.close()


class TestSearchQuery(unittest.TestCase):
    """Test search query sanitization and execution."""

    TEST_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_search.db")

    def setUp(self):
        import src.db as db_module
        self._orig_path = db_module.DB_PATH
        db_module.DB_PATH = self.TEST_DB
        init_db()
        # Seed some data
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO crawled_pages (url, origin_url, depth, content) VALUES (?, ?, ?, ?)",
                ("https://a.com", "https://a.com", 0, "python programming language tutorial"),
            )
            conn.execute(
                "INSERT INTO crawled_pages (url, origin_url, depth, content) VALUES (?, ?, ?, ?)",
                ("https://b.com", "https://a.com", 1, "javascript web development framework"),
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        import src.db as db_module
        db_module.DB_PATH = self._orig_path
        if os.path.exists(self.TEST_DB):
            os.remove(self.TEST_DB)
        for suffix in ("-wal", "-shm"):
            p = self.TEST_DB + suffix
            if os.path.exists(p):
                os.remove(p)

    def test_search_finds_match(self):
        from src.search import search
        results = search("python")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0][0], "https://a.com")

    def test_search_returns_triple_format(self):
        from src.search import search
        results = search("python")
        self.assertTrue(len(results) > 0)
        # Returns 4-tuple: (relevant_url, origin_url, depth, relevance_score)
        url, origin, depth, score = results[0]
        self.assertIsInstance(url, str)
        self.assertIsInstance(origin, str)
        self.assertIsInstance(depth, int)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)

    def test_search_empty_query(self):
        from src.search import search
        results = search("")
        self.assertEqual(results, [])

    def test_search_special_chars(self):
        from src.search import search
        # Should not crash on special characters
        results = search("!@#$%^&*()")
        self.assertEqual(results, [])

    def test_search_multi_word(self):
        from src.search import search
        results = search("python programming")
        self.assertTrue(len(results) > 0)
        # Verify results are sorted by relevance (highest score first)
        if len(results) > 1:
            scores = [r[3] for r in results]
            self.assertEqual(scores, sorted(scores, reverse=True))

    def test_search_no_match(self):
        from src.search import search
        results = search("xyznonexistent")
        self.assertEqual(results, [])

    def test_search_relevance_score_range(self):
        from src.search import search
        results = search("python")
        for _, _, _, score in results:
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 100.0)


if __name__ == "__main__":
    unittest.main()
