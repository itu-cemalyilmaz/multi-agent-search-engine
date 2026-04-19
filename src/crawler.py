"""
Crawler / Indexer Module (Backend Developer Agent)
===================================================
Implements the index(origin, k) function using asyncio for high-concurrency
crawling with two layers of backpressure:

  1. asyncio.Queue(maxsize)  – bounds memory usage of the URL frontier
  2. asyncio.Semaphore(N)    – limits concurrent outbound HTTP requests

Uses an in-memory set for O(1) deduplication and persists the frontier
to SQLite for crash-recovery.  URLs are normalized to avoid duplicates
caused by trailing slashes, fragments, etc.

Duplicate prevention (two layers):
  1. In-memory visited set (asyncio.Lock protected) – O(1) fast check
  2. INSERT OR IGNORE in SQLite – DB-level guarantee even across restarts
"""

import asyncio
import ssl
import urllib.request
import urllib.error
import threading
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse
from src.db import get_db_connection

# ---------------------------------------------------------------------------
#  Configuration constants
# ---------------------------------------------------------------------------
MAX_QUEUE_SIZE = 1000       # Backpressure: max URLs buffered in memory
MAX_CONCURRENCY = 10        # Backpressure: max parallel HTTP fetches
NUM_WORKERS = 10            # Number of async worker coroutines
FETCH_TIMEOUT = 10          # Seconds before a single fetch times out

# ---------------------------------------------------------------------------
#  Global mutable status dict – read by CLI / UI from the main thread
# ---------------------------------------------------------------------------
status = {
    "is_running": False,
    "queue_depth": 0,
    "pages_crawled": 0,
    "pages_failed": 0,
    "active_workers": 0,
    "backpressure_hits": 0,   # times queue.put had to wait (queue full)
}

_status_lock = threading.Lock()

# ---------------------------------------------------------------------------
#  Module-level references for frontier saving on interrupt
# ---------------------------------------------------------------------------
# These are set by index_manager so the CLI can call save_frontier() on Ctrl+C
_current_queue: asyncio.Queue | None = None
_current_visited: set | None = None


def _update_status(**kwargs):
    with _status_lock:
        status.update(kwargs)


def _inc_status(key, delta=1):
    with _status_lock:
        status[key] = status.get(key, 0) + delta


# ---------------------------------------------------------------------------
#  URL normalisation – strip fragments, default ports, trailing slashes
# ---------------------------------------------------------------------------
def normalize_url(url: str) -> str:
    """
    Return a canonical form of *url* to avoid crawling the same page twice.

    Normalisation rules:
      - Lowercase scheme and host
      - Strip URL fragment (#section)
      - Strip trailing slashes from path
      - Remove default ports (:80 for http, :443 for https)
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


# ---------------------------------------------------------------------------
#  HTML link extraction + text extraction (language-native HTMLParser)
# ---------------------------------------------------------------------------
class LinkExtractor(HTMLParser):
    """Extract <a href> links and visible text from an HTML document."""

    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[str] = []
        self.text_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    resolved = urljoin(self.base_url, value)
                    if resolved.startswith(("http://", "https://")):
                        self.links.append(normalize_url(resolved))

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self.text_parts)

    def error(self, message):
        pass  # Suppress HTMLParser errors for malformed HTML


# ---------------------------------------------------------------------------
#  Synchronous page fetch – runs in a thread via asyncio.to_thread
# ---------------------------------------------------------------------------
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def fetch_page(url: str) -> str | None:
    """Fetch a URL synchronously. Returns HTML string or None on failure."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MultiAgentCrawler/2.0 (+educational-project)",
            "Accept": "text/html",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT, context=_ssl_ctx) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return None
            raw = resp.read(2 * 1024 * 1024)  # Read at most 2 MB
            return raw.decode("utf-8", errors="ignore")
    except Exception:
        return None


# ---------------------------------------------------------------------------
#  Async worker coroutine
# ---------------------------------------------------------------------------
async def _worker(
    worker_id: int,
    queue: asyncio.Queue,
    semaphore: asyncio.Semaphore,
    visited: set,
    visited_lock: asyncio.Lock,
    stop_event: asyncio.Event,
    job_id: int | None,
):
    """
    Consumer coroutine.  Pulls (url, origin, depth, max_depth) from the queue,
    fetches the page, indexes it, and enqueues discovered links.

    Thread-safety note:
      - visited set is protected by asyncio.Lock (not threading.Lock) because
        all workers run in the same event loop thread.
      - status dict is protected by threading.Lock because the CLI reads it
        from a different OS thread.
      - SQLite WAL mode allows this coroutine to INSERT while the CLI thread
        runs SELECT queries simultaneously without any locking errors.
    """
    while not stop_event.is_set():
        # ---- Get next item from queue (with timeout so we can check stop) ----
        try:
            item = await asyncio.wait_for(queue.get(), timeout=2.0)
        except asyncio.TimeoutError:
            continue

        url, origin, depth, max_depth = item
        try:
            # ---- Dedup check (fast, in-memory O(1)) ----
            async with visited_lock:
                if url in visited:
                    continue
                visited.add(url)

            # ---- Acquire semaphore slot (backpressure on concurrency) ----
            async with semaphore:
                _inc_status("active_workers")
                _update_status(queue_depth=queue.qsize())

                html = await asyncio.to_thread(fetch_page, url)

                if html is None:
                    _inc_status("pages_failed")
                    _inc_status("active_workers", -1)
                    continue

                # ---- Parse HTML ----
                extractor = LinkExtractor(url)
                try:
                    extractor.feed(html)
                except Exception:
                    pass
                text = extractor.get_text()

                # ---- Persist to DB (INSERT OR IGNORE = DB-level dedup) ----
                conn = get_db_connection()
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO crawled_pages "
                        "(url, origin_url, depth, content) VALUES (?, ?, ?, ?)",
                        (url, origin, depth, text),
                    )
                    conn.commit()
                finally:
                    conn.close()

                _inc_status("pages_crawled")

                # ---- Discover new links ----
                if depth < max_depth:
                    for link in extractor.links:
                        async with visited_lock:
                            if link in visited:
                                continue
                        # put_nowait first (non-blocking); fall back to
                        # blocking put (backpressure) if queue is full.
                        try:
                            queue.put_nowait((link, origin, depth + 1, max_depth))
                        except asyncio.QueueFull:
                            _inc_status("backpressure_hits")
                            try:
                                await asyncio.wait_for(
                                    queue.put((link, origin, depth + 1, max_depth)),
                                    timeout=5.0,
                                )
                            except asyncio.TimeoutError:
                                pass  # Drop URL if queue stays full for 5 s

                _inc_status("active_workers", -1)
                _update_status(queue_depth=queue.qsize())

        except Exception:
            pass
        finally:
            # CRITICAL: task_done() MUST be in finally so queue.join() never
            # hangs even when we skip a URL via the dedup check above.
            queue.task_done()


# ---------------------------------------------------------------------------
#  Top-level index manager
# ---------------------------------------------------------------------------
async def index_manager(origin_url: str, max_depth: int):
    """
    Entry point: creates the queue, workers, and drives the crawl.
    Stores job metadata in the index_jobs table.
    """
    global _current_queue, _current_visited

    origin_url = normalize_url(origin_url)

    _update_status(
        is_running=True,
        queue_depth=0,
        pages_crawled=0,
        pages_failed=0,
        active_workers=0,
        backpressure_hits=0,
    )

    # Record job in DB
    conn = get_db_connection()
    try:
        cur = conn.execute(
            "INSERT INTO index_jobs (origin_url, max_depth, status) VALUES (?, ?, 'running')",
            (origin_url, max_depth),
        )
        conn.commit()
        job_id = cur.lastrowid
    finally:
        conn.close()

    # Backpressure primitives
    queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    stop_event = asyncio.Event()

    # Expose for CLI interrupt handler
    _current_queue = queue

    # In-memory visited set (O(1) dedup, asyncio.Lock for coroutine safety)
    visited: set[str] = set()
    visited_lock = asyncio.Lock()
    _current_visited = visited

    # Pre-load already-crawled URLs from DB (resume support on restart)
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT url FROM crawled_pages").fetchall()
        for row in rows:
            visited.add(row["url"])
    finally:
        conn.close()

    # Load frontier (URLs that were saved on a previous interrupted run)
    conn = get_db_connection()
    frontier_items = []
    try:
        rows = conn.execute(
            "SELECT url, origin_url, depth, max_depth FROM frontier"
        ).fetchall()
        for row in rows:
            frontier_items.append(
                (row["url"], row["origin_url"], row["depth"], row["max_depth"])
            )
        conn.execute("DELETE FROM frontier")
        conn.commit()
    finally:
        conn.close()

    # Seed the queue: frontier first (resume), then origin
    if frontier_items:
        print(f"   ↩️  Resuming from {len(frontier_items)} saved URLs...")
        for item in frontier_items:
            if item[0] not in visited:
                await queue.put(item)
    if origin_url not in visited:
        await queue.put((origin_url, origin_url, 0, max_depth))

    _update_status(queue_depth=queue.qsize())

    # Spawn fixed-size worker pool
    workers = []
    for i in range(NUM_WORKERS):
        task = asyncio.create_task(
            _worker(i, queue, semaphore, visited, visited_lock, stop_event, job_id)
        )
        workers.append(task)

    # Wait for queue to drain completely
    await queue.join()

    # Signal workers to stop and await cleanup
    stop_event.set()
    await asyncio.gather(*workers, return_exceptions=True)

    # Update final count in DB
    final_count = status["pages_crawled"]
    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE index_jobs SET status='completed', pages_crawled=? WHERE id=?",
            (final_count, job_id),
        )
        conn.commit()
    finally:
        conn.close()

    _current_queue = None
    _current_visited = None
    _update_status(is_running=False, active_workers=0, queue_depth=0)


# ---------------------------------------------------------------------------
#  Synchronous entry point (called from CLI thread via threading.Thread)
# ---------------------------------------------------------------------------
def start_indexing(origin_url: str, max_depth: int):
    """Blocking wrapper that runs the async index_manager in a new event loop."""
    asyncio.run(index_manager(origin_url, max_depth))


# ---------------------------------------------------------------------------
#  Save frontier on interrupt (resume support)
# ---------------------------------------------------------------------------
def save_frontier_on_interrupt():
    """
    Drain the in-memory queue into the `frontier` DB table so
    that the next run can resume from where it left off.
    Called by the CLI's KeyboardInterrupt / exit handler.
    """
    global _current_queue, _current_visited
    q = _current_queue
    if q is None or q.empty():
        return

    items = []
    while not q.empty():
        try:
            items.append(q.get_nowait())
        except Exception:
            break

    if not items:
        return

    conn = get_db_connection()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO frontier (url, origin_url, depth, max_depth) "
            "VALUES (?, ?, ?, ?)",
            items,
        )
        conn.commit()
        print(f"💾 Saved {len(items)} URLs to frontier for resume.")
    finally:
        conn.close()
