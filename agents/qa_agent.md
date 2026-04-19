# Agent: QA / Testing Agent

## Role Definition
The QA Agent is intentionally adversarial toward the implementation. Its job is to break things, not to confirm that things work. It writes tests that attempt to expose real failure modes: deadlocks, format mismatches, race conditions, and constraint violations.

**Key principle:** The QA Agent never modifies production code. When it finds a bug, it writes a formal bug report with: symptom, root cause, reproduction steps, and suggested fix. The fix is applied by the Backend Agent.

---

## Task Claimed from Shared Task List

```
You are the QA Engineer. Your job is to break the web crawler and search engine.
Write a comprehensive test suite using Python's built-in unittest framework only.
No pytest, no mock libraries.

UNIT TESTS (tests/test_unit.py) — test individual components in isolation:

1. URL Normalisation (src/crawler.normalize_url):
   - Trailing slash stripped: "/page/" → "/page"
   - Fragment stripped: "/page#section" → "/page"
   - Default HTTP port stripped: "http://host:80/page" → "http://host/page"
   - Default HTTPS port stripped: "https://host:443/page" → "https://host/page"
   - Non-default port preserved: "http://host:8080/page" unchanged
   - Uppercase host lowercased: "HTTP://EXAMPLE.COM/" → "http://example.com/"
   - Root path preserved: "https://example.com" → "https://example.com/"
   - Query string preserved: "/page?q=1" unchanged

2. HTML Link Extraction (src/crawler.LinkExtractor):
   - Absolute HTTP link extracted correctly
   - Relative link resolved against base URL
   - mailto: and javascript: links ignored
   - Malformed/empty href ignored
   - Multiple links in one page all extracted
   - Text inside <script> and <style> NOT included in get_text()
   - Text inside <p>, <h1> etc. IS included in get_text()
   - Empty HTML returns zero links and empty text

3. Database (src/db.init_db):
   - All 4 tables created: crawled_pages, pages_fts, frontier, index_jobs
   - FTS5 trigger syncs: INSERT to crawled_pages → searchable via pages_fts
   - Duplicate URL rejected: second INSERT with same URL → still 1 row

4. Search (src/search.search):
   - Single word query returns matching results
   - Multi-word query returns results (must not crash with FTS5 syntax error)
   - Empty string query returns []
   - Query with special chars (e.g., "@#$") returns []
   - Return format is 4-tuple: (str, str, int, float)
   - Relevance score is in range [0.0, 100.0]
   - Multi-word results sorted by score descending (highest score first)

ISOLATION RULE: Each test class creates a temp DB with a unique name 
(e.g., f"test_{uuid4().hex}.db") and deletes it in tearDown().
Never use the production data.db. Never share state between tests.

INTEGRATION TESTS (tests/test_integration.py) — test the full pipeline:

1. Full pipeline: index("https://example.com", 0) → search("example") returns results
   Verify: result format is 4-tuple, depth=0, URL contains "example.com"
   
2. DB persistence: after index(), crawled_pages has row with correct url/origin/depth
   
3. Job tracking: index_jobs has a row after indexing; status becomes "completed"
   
4. Duplicate prevention: index same origin twice → SELECT COUNT(*) = 1 row still
   
5. Stats: get_stats() returns correct total_indexed_pages count
   
6. MOST IMPORTANT — Concurrent search during active indexing:
   Start index() in a background thread. While it runs, call search() in main 
   thread 10 times in a loop. NONE of these calls may raise an OperationalError 
   or any SQLite error. This verifies WAL mode is working.

Use real network calls (no mocking). Tests that require internet: example.com is 
reliable and appropriate for this use.
```

---

## Output Produced
- `tests/test_unit.py` — 26 unit tests
- `tests/test_integration.py` — 6 integration tests

---

## Bug Reports Issued

### Bug Report #1 (Critical): Deadlock on skip

**Test that caught it:** `test_no_duplicate_crawling`  
**Symptom:** Test hangs indefinitely — never completes  
**Root cause analysis:**
```python
# In _worker():
item = await queue.get()
url, origin, depth, max_depth = item
async with visited_lock:
    if url in visited:
        continue   # ← EXIT HERE: task_done() never called
    visited.add(url)
# ... rest of worker ...
queue.task_done()   # ← Never reached on the skip path
```
`queue.join()` in `index_manager` waits for `task_done()` to be called for every item that was `get()`'d. If we skip a URL via `continue` without calling `task_done()`, the counter never reaches zero and `queue.join()` blocks indefinitely.

**Fix requested:** Move `queue.task_done()` into a `finally` block that runs regardless of how the `try` block exits:
```python
try:
    ...all processing...
finally:
    queue.task_done()   # ← Always called
```
**Status:** Fixed by Backend Agent. Verified by re-running `test_no_duplicate_crawling` ✅

---

### Bug Report #2 (High): FTS5 syntax error on multi-word search

**Test that caught it:** `test_search_multi_word`  
**Symptom:** `sqlite3.OperationalError: fts5: syntax error near "web"`  
**Root cause analysis:**
```python
# Broken:
query = "python web"
conn.execute("SELECT * FROM pages_fts WHERE pages_fts MATCH ?", (query,))
# SQLite receives: MATCH 'python web'
# FTS5 parser sees "web" as keyword NEAR/AND/OR/NOT → syntax error
```
FTS5 MATCH treats unquoted multi-word strings as boolean expressions. "python web" is parsed as two tokens where "web" is expected to be an operator.

**Fix requested:**
```python
tokens = [f'"{w}"' for w in query.split() if w.isalnum()]
fts_query = " OR ".join(tokens)
# SQLite receives: MATCH '"python" OR "web"' → correct
```
**Status:** Fixed by Backend Agent ✅

---

### Bug Report #3 (Medium): Return format mismatch

**Test that caught it:** `test_search_returns_triple_format`  
**Symptom:** `ValueError: too many values to unpack (expected 3)`  
**Root cause:** `search()` was updated to return 4-tuples `(url, origin, depth, score)` but the test still unpacked 3: `url, origin, depth = results[0]`  
**Note:** This is a test-code bug, not a production bug. search() returning a score is **correct** — the tests needed to be updated.  
**Fix applied by QA Agent:** Updated test to unpack 4-tuple and added `assertIsInstance(score, float)` and `assertGreaterEqual/LessEqual` bounds checks  
**Status:** Fixed ✅

---

## Final Test Results

```
Ran 32 tests in 22.4s
OK

26 unit tests:
  - 8 URL normalization tests  ✅
  - 7 HTML extraction tests    ✅  
  - 3 database tests           ✅
  - 7 search tests             ✅
  (includes new test_search_relevance_score_range)

6 integration tests:
  - test_crawl_and_search_example_com   ✅
  - test_crawl_records_in_db            ✅
  - test_job_tracking                   ✅
  - test_no_duplicate_crawling          ✅ (was the deadlock test)
  - test_get_stats                      ✅
  - test_search_during_indexing         ✅ (WAL concurrency verified)
```

---

## Interactions with Other Agents

| Agent | Type of Interaction |
|-------|-------------------|
| Backend Developer | Primary consumer: tested all Backend output; sent 3 bug reports |
| Systems Architect | Verified schema decisions (WAL mode, triggers, IGNORE) via integration tests |
| Writer/UI Agent | CLI tested indirectly via integration tests |
| Orchestrator | Bug reports reviewed and approved before routing to Backend |
