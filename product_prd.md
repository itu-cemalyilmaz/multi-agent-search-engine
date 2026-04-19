# Product Requirements Document (PRD)

**Project:** AI Multi-Agent Web Crawler & Search Engine  
**Author:** Product Manager Agent  
**Date:** April 2026  
**Version:** 2.0

---

## 1. Overview

Build a high-performance web crawler and search engine on a single machine using exclusively native Python libraries. The system must handle large-scale crawls with controlled resource usage (backpressure) while allowing concurrent search queries during active indexing.

## 2. Technical Constraints

| Constraint | Detail |
|-----------|--------|
| Language | Python 3.11+ |
| Libraries | Standard library only (`asyncio`, `sqlite3`, `urllib`, `html.parser`) |
| Forbidden | Scrapy, Elasticsearch, aiohttp, BeautifulSoup, or any library that performs core crawling/indexing/search out of the box |
| Deployment | Single machine, localhost |
| Database | SQLite (included in Python stdlib) |

## 3. Core Features

### 3.1. `index(origin, k)` — Web Crawling & Indexing

**Input:**
- `origin` (string): The starting URL
- `k` (integer): Maximum depth — the number of hops between the origin and a newly discovered link

**Behavior:**
1. Fetch the HTML at `origin`
2. Extract all `<a href>` links from the page
3. For each discovered link, if `current_depth < k`, schedule it for crawling
4. Never crawl the same URL twice (URL normalization + deduplication)
5. Extract visible text content and store it in a searchable index

**Backpressure Requirements:**
- **Memory Backpressure**: Queue of pending URLs must be bounded (max 1,000 items). When full, producers must block until space is available.
- **Network Backpressure**: No more than 10 concurrent outgoing HTTP requests at any time.
- **Monitoring**: Current queue depth, active worker count, and backpressure hit count must be queryable.

### 3.2. `search(query)` — Full-Text Search

**Input:**
- `query` (string): A text search query

**Output:**
- List of triples: `(relevant_url, origin_url, depth)`
  - `relevant_url`: A page whose content matches the query
  - `origin_url`: The URL passed to `index()` that initiated the crawl
  - `depth`: The depth at which `relevant_url` was discovered

**Behavior:**
- Uses full-text search with relevance ranking (BM25 via SQLite FTS5)
- Must work concurrently while an active indexing job is running
- New results appear as they are indexed — no need to wait for crawl completion

### 3.3. CLI Interface

| Command | Description |
|---------|-------------|
| `index <url> <depth>` | Start background crawling |
| `search <query>` | Search indexed content |
| `status` | Show queue depth, active workers, backpressure hits |
| `stats` | Show total pages indexed and job history |
| `reset` | Clear all indexed data |
| `help` | List commands |
| `exit` | Quit |

## 4. Non-Functional Requirements

- **Scalability**: Must handle 10,000+ pages without OOM or significant slowdown
- **Concurrency**: Search queries must not block or be blocked by active crawling
- **Resilience**: Already-crawled pages persist across restarts. The frontier table enables future resume support.
- **Correctness**: No duplicate pages in the index. URL normalization prevents `example.com/page` and `example.com/page/` from being treated as different URLs.

## 5. Success Criteria

- [ ] `index("https://example.com", 2)` completes without errors
- [ ] `search("example")` returns results with correct triple format
- [ ] `search` works while `index` is actively running (no "database locked" errors)
- [ ] Queue depth never exceeds 1,000; active workers never exceed 10
- [ ] 25 unit tests pass
- [ ] 6 integration tests pass (including concurrent search test)
- [ ] System handles malformed HTML, SSL errors, and timeouts gracefully

## 6. Out of Scope (for v2.0)

- robots.txt compliance (deferred to production deployment)
- Rate limiting per domain (deferred)
- Web UI (CLI is sufficient for the exercise)
- Distributed crawling across multiple machines
