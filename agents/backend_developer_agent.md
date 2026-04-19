# Agent: Backend Developer

## Role Definition
The Backend Developer Agent takes the Architect's specification and produces working Python code. It is the only agent that writes production source files. It does not design architecture — it implements what the Architect specified.

**Key constraint:** When the Backend Agent disagrees with the spec, it raises the disagreement formally to the Orchestrator. It does not silently deviate from the spec.

---

## Task Claimed from Shared Task List

```
You are the Backend Engineer. Implement the web crawler and search engine 
exactly as specified by the Systems Architect.

CRAWLER (src/crawler.py):
  - index(origin, k) implemented as index_manager() async coroutine
  - asyncio.Queue(maxsize=1000) as bounded URL frontier
  - asyncio.Semaphore(10) controls max concurrent HTTP connections
  - asyncio.to_thread(fetch_page, url) offloads blocking urllib call
    to a threadpool without blocking the event loop
  - In-memory `visited: set[str]` protected by asyncio.Lock
    (asyncio.Lock, NOT threading.Lock — all workers share one event loop)
  - URL normalisation: strip fragment, trailing slash, default ports,
    lowercase scheme and host
  - Global `status: dict` readable from Python threads (CLI thread reads it)
    Protect with threading.Lock (not asyncio.Lock) because CLI is a different OS thread
  - On interrupt: expose _current_queue so CLI can call save_frontier_on_interrupt()

CRITICAL BUGS TO AVOID (these were common in previous implementations):

Bug 1 — Deadlock:
  WRONG:
    item = await queue.get()
    if url in visited:
        continue   ← task_done() never called → queue.join() hangs forever
  CORRECT:
    item = await queue.get()
    try:
        ...all processing...
    finally:
        queue.task_done()  ← always reached

Bug 2 — FTS5 parse error on multi-word queries:
  WRONG: conn.execute("... WHERE pages_fts MATCH ?", ("python web",))
    → sqlite3.OperationalError: fts5: syntax error near 'web'
  CORRECT: tokenise + quote each word:
    tokens = [f'"{w}"' for w in query.split() if w.isalnum()]
    fts_query = " OR ".join(tokens)  # → '"python" OR "web"'

Bug 3 — NameError in finally:
  WRONG:
    try:
        conn = get_db_connection()
    finally:
        conn.close()   ← NameError if get_db_connection() raised
  CORRECT:
    conn = None
    try:
        conn = get_db_connection()
    finally:
        if conn: conn.close()

SEARCH (src/search.py):
  - Use FTS5 MATCH with quoted tokens (see Bug 2 above)
  - Return 4-tuples: (relevant_url, origin_url, depth, relevance_score)
  - relevance_score: normalise BM25 rank (negative float) to 0.0–100.0
    Most relevant result = 100.0, least relevant = 0.0
  - Handle empty query, all-special-char query gracefully (return [])
  - Thread-safe: this function is called from CLI thread during crawling
    (WAL mode handles the SQLite concurrency, no Python locking needed)
```

---

## Output Produced
- `src/crawler.py` — 423-line async crawler
- `src/search.py` — 95-line BM25 search engine

---

## Key Implementation Decisions

### Decision 1: asyncio.to_thread for urllib
`urllib.request.urlopen()` is a blocking call — it suspends the calling thread until the HTTP response arrives. In an asyncio event loop, blocking the thread means blocking ALL coroutines in that loop.

**Solution:** `asyncio.to_thread(fetch_page, url)` runs the blocking function in Python's default `ThreadPoolExecutor`, returning an awaitable. The event loop continues scheduling other coroutines while the HTTP call blocks its thread.

```python
html = await asyncio.to_thread(fetch_page, url)
```

### Decision 2: asyncio.Lock vs threading.Lock
There are two kinds of locks in this codebase with different purposes:

| Lock Type | Used For | Why |
|-----------|----------|-----|
| `asyncio.Lock` | `visited` set access | All worker coroutines share one OS thread (the event loop thread). asyncio.Lock yields control without a thread context-switch |
| `threading.Lock` | `status` dict access | CLI reads `status` from a different OS thread. asyncio.Lock doesn't work across OS threads |

### Decision 3: QueueFull — timed wait, then drop
When the queue is full and a worker discovers a new link:
1. Try `put_nowait()` first (free if space available)
2. If queue is full, try `put()` with 5-second timeout (waits for slot)
3. If still full after 5 seconds, log a backpressure hit and **drop the URL**

Dropping URLs is acceptable because: (a) this URL is likely reachable via another path in the crawl graph, and (b) OOM is worse than missing one URL.

### Decision 4: 2MB Page Size Limit
`resp.read(2 * 1024 * 1024)` limits each page to 2MB. This prevents a crawler trap where a single enormous page (e.g., a 50MB HTML dump) consumes all available memory.

### Decision 5: BM25 Score Normalisation
SQLite FTS5 returns `rank` as a negative float where:
- `-0.1` = very relevant
- `-10.0` = less relevant

This is counterintuitive. The Backend Agent normalises to 0–100%:

```python
min_score = min(raw_scores)  # most relevant (most negative)
max_score = max(raw_scores)  # least relevant (closest to 0)
relevance = ((max_score - row["rank"]) / (max_score - min_score)) * 100
```

---

## Bugs Found During QA and Fixes Applied

### Bug 1: Deadlock (Critical)
**Reported by:** QA Agent  
**Symptom:** `test_no_duplicate_crawling` hung indefinitely  
**Root cause:** `continue` inside worker skipped `task_done()` call  
**Fix:** Moved `queue.task_done()` to `finally` block — guaranteed to execute

### Bug 2: FTS5 syntax error (High)
**Reported by:** QA Agent  
**Symptom:** `test_search_multi_word` raised `OperationalError: fts5: syntax error`  
**Root cause:** Raw multi-word string passed to MATCH without quoting  
**Fix:** Tokenize + wrap each token in double quotes before building fts_query

### Bug 3: Format mismatch (Medium)  
**Reported by:** QA Agent  
**Symptom:** `test_search_returns_triple_format` raised `ValueError: too many values to unpack`  
**Root cause:** search() was updated to return 4-tuple but tests expected 3-tuple  
**Fix:** Updated tests and test documentation to match 4-tuple format

---

## Interactions with Other Agents

| Agent | Type of Interaction |
|-------|-------------------|
| Systems Architect | Received technical spec; implemented it faithfully |
| Writer/UI Agent | Exported `start_indexing()`, `status`, `save_frontier_on_interrupt()` for CLI |
| QA Agent | Received bug reports; applied fixes to crawler.py and search.py |
| Orchestrator | Raised disagreement about dedup strategy; Orchestrator mediated |
