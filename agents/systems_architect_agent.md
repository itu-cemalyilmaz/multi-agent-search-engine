# Agent: Systems Architect

## Role Definition
The Systems Architect Agent translates requirements into concrete technical design. It answers: "What data structures? What concurrency primitives? What schema?" before a single line of production code is written.

**Key principle:** The Architect never writes implementation code. It writes specifications. This prevents "designing while coding" which leads to structural bugs discovered late.

---

## Task Claimed from Shared Task List

```
You are the Systems Architect. Read the PRD and design the full technical 
architecture for the web crawler and search engine.

Hard constraints from PM:
  - Native Python only: asyncio, sqlite3, urllib, html.parser
  - search() must work concurrently while index() is writing data
  - Memory must be bounded: system must not OOM on 100,000+ URL crawls
  - No external services

Design and document your decisions for:

1. DATABASE SCHEMA
   - What tables are needed and why?
   - How do we support full-text search without Elasticsearch?
   - How do we enable concurrent reads + writes without "database locked" errors?
   - How do we support crash recovery (resume after interruption)?
   
2. CONCURRENCY MODEL
   - How do URLs flow from discovery → fetch → parse → store?
   - What asyncio primitives control this flow?
   - Where exactly are the two backpressure control points?
   
3. DEDUPLICATION STRATEGY
   - How do we ensure no URL is fetched twice across 100,000 URLs?
   - What is the time complexity of each dedup check?
   - What happens to dedup state on process crash?
   
4. URL NORMALISATION
   - What transformations are required?
   - Give examples of URLs that would incorrectly count as different without normalisation.

Output a technical specification that the Backend Developer can implement directly.
```

---

## Output Produced
- Database schema → implemented in `src/db.py`
- Concurrency design → implemented in `src/crawler.py`
- Architecture decisions → documented in `multi_agent_workflow.md`

---

## Key Design Decisions and Justifications

### Decision 1: SQLite with WAL Mode
**Problem:** SQLite's default journal mode locks the entire database file on write. Any `search()` call during a crawl would get `OperationalError: database is locked`.

**Solution:** WAL (Write-Ahead Logging) mode writes changes to a separate WAL file. Readers see a consistent snapshot of the main DB file and never block writers. Readers never block writers either.

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;   -- Wait up to 5s before raising busy error
```

### Decision 2: FTS5 Virtual Table + Triggers
**Problem:** How to do full-text search inside SQLite without an external search engine?

**Solution:** FTS5 (Full-Text Search 5) is a built-in SQLite extension that maintains an inverted index and supports BM25 ranking. FTS5 cannot be directly updated by INSERT to the main table, so we use triggers:

```sql
CREATE TRIGGER trg_pages_insert AFTER INSERT ON crawled_pages BEGIN
    INSERT INTO pages_fts(url, content) VALUES (new.url, new.content);
END;
```
This auto-syncs — the Backend Developer never needs to manually update the FTS index.

### Decision 3: Two-Tier Backpressure
**Problem:** 10 workers each discovering 50 links = 500 new URLs per second. Without a ceiling, the queue grows without bound → OOM.

**Solution:**
- `asyncio.Queue(maxsize=1000)` — when 1,000 URLs are buffered, producers block. This is "flow control" — the system slows down naturally.
- `asyncio.Semaphore(10)` — never more than 10 open TCP connections. Prevents network socket exhaustion on systems with ulimit constraints.

### Decision 4: In-Memory visited Set + asyncio.Lock
**Problem:** Backend Agent proposed using only `INSERT OR IGNORE` in SQLite for deduplication. This works but requires a DB round-trip for every link discovered.

**Architect's counter-proposal:** Layer 1 = in-memory `set[str]` for O(1) fast-path rejection. Layer 2 = `INSERT OR IGNORE` as crash-resilient backup.

```python
async with visited_lock:
    if url in visited:      # O(1), no DB involved
        continue
    visited.add(url)
# ... then INSERT OR IGNORE into DB
```

**Result:** Orchestrator adopted both layers. This is the industry-standard approach.

### Decision 5: Frontier Table for Resume Support
**Problem:** If the process is killed during a large crawl, all queued URLs are lost. The next run starts over from scratch.

**Solution:** On graceful shutdown (Ctrl+C or `exit`), drain the in-memory queue and write all pending items to a `frontier` table. On next startup, load frontier items back into the queue before starting new work.

### Decision 6: URL Normalisation Rules
Without normalisation, these four strings would all be crawled as separate pages:
```
https://example.com/page         # canonical
https://Example.COM/page         # uppercase host → same page
https://example.com/page/        # trailing slash → same page
https://example.com/page#section # fragment → same resource, different anchor
https://example.com:443/page     # default HTTPS port → same server
```

Normalisation rules implemented:
1. Lowercase scheme and host
2. Remove fragment (`#...`)
3. Strip trailing slashes from path
4. Remove default ports (`:80` for HTTP, `:443` for HTTPS)

---

## Conflict with Backend Developer Agent

The Backend Agent initially wanted to skip URL normalisation ("the DB dedup handles it"). Architect Agent pushed back: without normalisation, a crawler visiting `example.com/page` would also queue `example.com/page/` as a different URL — the visited set check would miss it, and both would be fetched and stored. This was accepted by the Orchestrator as a correctness issue, not a performance optimisation.

---

## Interactions with Other Agents

| Agent | Type of Interaction |
|-------|-------------------|
| PM Agent | Received PRD; all design decisions must satisfy PRD constraints |
| Backend Developer | Provided schema spec and concurrency model; Backend implements exactly this |
| QA Agent | Schema decisions (WAL, triggers, IGNORE) are what integration tests verify |
| DevOps Agent | Design decisions are what DevOps Agent critiques for production readiness |
