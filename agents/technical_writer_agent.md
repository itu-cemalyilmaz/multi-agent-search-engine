# Agent: Technical Writer / UI Agent

## Role Definition
The Technical Writer / UI Agent creates everything the user interacts with: the CLI and all documentation. It is responsible for bridging the gap between the engineering work (done by Backend and Architect agents) and the user/grader's understanding of that work.

**Key principle:** The Writer Agent never modifies core logic. If it identifies a UX improvement that requires a backend change (e.g., "the search results need a relevance score"), it raises a change request to the Orchestrator, who routes it to the Backend Agent.

---

## Task Claimed from Shared Task List

```
You are the Technical Writer and UI Agent. Your inputs are the completed modules:
  - src/crawler.py  (exports: start_indexing, status, save_frontier_on_interrupt)
  - src/search.py   (exports: search(query) → [(url, origin, depth, score), ...])
  - src/db.py       (exports: init_db, reset_db)

Create two deliverables:

DELIVERABLE 1: src/cli.py
An interactive CLI with these requirements:
  - Main thread: input loop — never blocks user input
  - Background daemon thread: asyncio event loop running the crawler
    (threading.Thread(target=start_indexing, args=(...), daemon=True))
  - Commands:
      index <url> <depth>   — validate input, auto-prepend https://, start thread
      search <query>        — call search(), show count, timing, and BM25 % scores
      status                — show is_running, pages_crawled, active_workers,
                              queue_depth/1000, backpressure_hits
      stats                 — total indexed pages + recent job history
                              (show "← live counter" note for running jobs)
      reset                 — clear DB (only allowed when not running)
      help                  — print command list
      exit / quit           — call save_frontier_on_interrupt() then os._exit(0)
  - Ctrl+C: same as exit (save frontier and exit gracefully)
  - Use Unicode box-drawing and emoji throughout
  - Print "ℹ️ Search runs concurrently via SQLite WAL mode" on index start

DELIVERABLE 2: README.md
  - ASCII architecture diagram showing 2-thread model and SQLite WAL
  - Backpressure explanation: where the two control points are
  - BM25 explanation: what the relevance scores mean
  - Deduplication explanation: two-layer approach
  - Setup: Python 3.11+ required, no pip install needed
  - Run instructions for CLI and for tests
  - Example CLI session with annotated output
  - Multi-agent development approach summary

Use Unicode box-drawing characters. Write for a technically literate reader.
```

---

## Output Produced
- `src/cli.py` — 175-line interactive CLI
- `README.md` — Full project documentation

---

## Key Design Decisions

### Decision 1: daemon=True on Background Thread
```python
t = threading.Thread(target=start_indexing, args=(url, depth), daemon=True)
t.start()
```
`daemon=True` means the background crawler thread is automatically killed when the main CLI thread exits. Without this, pressing `exit` in the CLI would leave the crawler running in the background indefinitely (the Python process would not exit).

### Decision 2: os._exit(0) Instead of sys.exit()
`sys.exit()` raises `SystemExit` which can be caught. In a multithreaded program with a daemon background thread, `SystemExit` can produce race conditions. `os._exit(0)` forces immediate process termination without cleanup, which is safe here because we've already called `save_frontier_on_interrupt()` first.

### Decision 3: Live Counter in Stats
When a job is actively running, the `pages_crawled` column in `index_jobs` is `0` because we only write the final count to the DB when the job completes. To avoid confusing the user with `pages=0` while 20+ pages are clearly indexed:

```python
if i == 0 and d["status"] == "running":
    d["pages_crawled"] = crawler_status["pages_crawled"]  # live memory value
    d["note"] = "live"
```

### Decision 4: BM25 % Notation Instead of Raw Rank
FTS5 returns a negative float like `-2.847`. This is meaningless to a user. We map the result set's range to `[0%, 100%]`:
- The best-matching result always shows as `100.0%`
- The worst-matching result in the set shows as `0.0%`
- All others interpolate proportionally

### Decision 5: Change Request Raised to Orchestrator
The Writer Agent identified that search results had no relevance score (Backend Agent originally returned 3-tuples). It raised a change request:

> "graders will immediately ask about ranking. We should show a relevance percentage. 
> This requires Backend Agent to normalise the BM25 rank. Requesting change."

Orchestrator approved. Backend Agent updated `search()` to return 4-tuples. Tests updated by QA Agent.

---

## Interactions with Other Agents

| Agent | Type of Interaction |
|-------|-------------------|
| Backend Developer | Consumed its exports (start_indexing, status, save_frontier_on_interrupt, search) |
| Systems Architect | Documented its design decisions in README and workflow docs |
| QA Agent | CLI is tested indirectly via integration tests |
| Orchestrator | Raised change request for relevance score display; approved and routed |
