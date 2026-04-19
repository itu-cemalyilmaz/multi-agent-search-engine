# AI Multi-Agent Web Crawler and Search Engine

A production-quality web crawler and search engine built entirely with **native Python** (`asyncio`, `sqlite3`, `urllib`, `html.parser`). Designed and developed using an **Agent Teams architecture** where specialized Artificial Intelligence teammates collaborated via a Shared Task List to build the system.

## Architecture Overview

```
┌──────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   CLI / UI   │────▶│   Crawler Engine     │────▶│  SQLite (WAL)   │
│  (cli.py)    │     │  asyncio workers     │     │  + FTS5 Index   │
│              │◀────│  backpressure queue   │     │                 │
│              │     └──────────────────────┘     │  crawled_pages  │
│              │────────────────────────────────▶│  pages_fts      │
│  search cmd  │     Search Module               │  frontier       │
│              │◀────────────────────────────────│  index_jobs     │
└──────────────┘                                  └─────────────────┘
```

### Backpressure Design

## Architecture Overview

**Core Engine:**
- **URL Frontier:** `asyncio.Queue` (backpressure: memory bounded to 1000 items)
- **Concurrency:** `asyncio.Semaphore` (backpressure: max 10 active connections)
- **Database:** `sqlite3` using **WAL mode** (enables concurrent reads/writes)
- **Search:** `sqlite3` **FTS5** virtual table with custom BM25 ranking

**AI Tooling & Setup:**
- **IDE / Environment:** VS Code
- **Agent Environment (Orchestrator):** Antigravity / Agentic Workspace powered by LLMs (Claude 3.5 Sonnet & Gemini Pro)
- **Multi-Agent Runtime:** Demonstrated via specialized prompting logic and shared task coordination, designed iteratively via the IDE extension.

Two layers of backpressure prevent resource exhaustion during large-scale crawls:

1. **`asyncio.Queue(maxsize=1000)`** — Limits the in-memory URL frontier. When the queue is full, producers block, preventing memory explosions.
2. **`asyncio.Semaphore(10)`** — Limits concurrent outbound HTTP requests to 10.

### Concurrent Search During Indexing

SQLite is configured in **WAL (Write-Ahead Logging) mode**, which allows readers (search queries) and writers (crawler inserts) to operate concurrently without blocking each other.

### Resume After Interruption

- Already-crawled URLs are persisted in `crawled_pages` — on restart, they are loaded into the visited set
- The `frontier` table can store unprocessed URLs for future resume support
- Each crawl job is tracked in the `index_jobs` table with status updates

## Project Structure

```
ai2/
├── src/
│   ├── __init__.py
│   ├── db.py              # SQLite schema, WAL mode, FTS5 triggers
│   ├── crawler.py          # Async crawling engine with backpressure
│   ├── search.py           # FTS5-powered search with BM25 ranking
│   └── cli.py              # Interactive command-line interface
├── tests/
│   ├── __init__.py
│   ├── test_unit.py        # 25 unit tests (parsing, normalization, search)
│   └── test_integration.py # 6 integration tests (full pipeline, concurrency)
├── agents/
│   ├── product_manager_agent.md
│   ├── systems_architect_agent.md
│   ├── backend_developer_agent.md
│   ├── devops_agent.md
│   ├── technical_writer_agent.md
│   └── qa_agent.md
├── product_prd.md          # Product Requirements Document
├── multi_agent_workflow.md # Multi-agent collaboration details
├── recommendation.md       # Production deployment advice
└── README.md               # This file
```

## Prerequisites

- **Python 3.11+** (uses `asyncio.to_thread`, type hints with `|`)
- No external packages required — 100% standard library

## How to Run

### Start the Interactive CLI

```bash
cd ai2
python src/cli.py
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `index <url> <depth>` | Start crawling from URL up to depth hops |
| `search <query>` | Search indexed pages (works during crawling!) |
| `status` | Show crawler status, queue depth, backpressure |
| `stats` | Show database statistics and job history |
| `reset` | Clear all indexed data |
| `help` | Show available commands |
| `exit` | Quit the application |

### Example Session

```
🔍 > index https://example.com 2
🚀 Started indexing https://example.com (max depth=2) in background.

🔍 > status
┌─ Crawler Status ──────────────────────┐
│  Running        : ✅ Yes
│  Pages Crawled  : 3
│  Pages Failed   : 0
│  Active Workers : 2 / 10
│  Queue Depth    : 15 / 1000
│  BP Hits        : 0
└───────────────────────────────────────┘

🔍 > search example domain
📄 2 result(s) for 'example domain' (0.004s):
    1. https://example.com/
       origin=https://example.com/  depth=0
```

### Run Tests

```bash
# Unit tests (25 tests)
python -m unittest tests.test_unit -v

# Integration tests (6 tests, requires internet for example.com)
python -m unittest tests.test_integration -v
```

## Agent Teams Development Workflow

This project was developed using a modern **Agent Teams workflow** (bypassing the rigid subagent model) with 6 specialized AI teammates collaborating via a Shared Task List:

| Teammate Agent | LLM Backbone | Responsibility (Claimed Task) | Output |
|----------------|--------------|-------------------------------|--------|
| Product Manager | **GPT-4o** | Requirements & scope definition | `product_prd.md` |
| Systems Architect | **Claude 4.6 Opus** | Schema & async design | `src/db.py`, architecture |
| Backend Developer | **Claude 4.6 Sonnet** | Core crawler implementation | `src/crawler.py`, `src/search.py` |
| DevOps | **GPT-4o** | Scaling audit & production recommendations | `recommendation.md` |
| Technical Writer/UI | **Gemini 3.1 Pro** | CLI & documentation | `src/cli.py`, `README.md` |
| QA Engineer | **Gemini 3.1 Pro** | Thread-safe testing & bug reporting | `tests/` |

See `multi_agent_workflow.md` for the detailed Shared Task List, direct peer-to-peer agent collaborations, and design negotiations.
See `agents/` directory for individual teammate descriptions and prompt origins.

## Design Decisions

1. **Native Python Only**: No Scrapy, no Elasticsearch, no aiohttp — demonstrates understanding of the underlying mechanics
2. **SQLite FTS5**: Built-in full-text search with BM25 ranking, synced via triggers
3. **asyncio + threading**: Crawler runs in asyncio event loop inside a daemon thread, CLI stays responsive
4. **URL Normalization**: Strips fragments, default ports, trailing slashes to prevent duplicate crawling
5. **Bounded Queue + Semaphore**: Two-tier backpressure prevents both memory and network exhaustion
