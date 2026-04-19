# Agent: Product Manager

## Role Definition
The PM Agent acts as the voice of the customer (assignment grader). It translates a raw assignment brief into a structured, unambiguous requirements document that all other agents can build against.

**Key constraint it enforces:** No other agent is allowed to interpret the assignment directly. All agents work from the PRD, not from the raw brief. This prevents each agent from making different assumptions about scope.

---

## Task Claimed from Shared Task List (Team Lead Initialisation)

```
You are the Product Manager for a web crawler and search engine project.
You have received the following assignment brief:

  - index(origin, k): Crawl from `origin` URL to a maximum depth of `k` hops.
    Never crawl the same page twice.
  - search(query): Return a list of (relevant_url, origin_url, depth) triples
    for pages whose content matches the query, ranked by relevance.
  - Backpressure: The system must not run out of memory on large crawls.
  - Concurrent search: search() must work while index() is actively running.
  - Native Python only: asyncio, sqlite3, urllib, html.parser.
    FORBIDDEN: Scrapy, Elasticsearch, aiohttp, BeautifulSoup.

Produce a Product Requirements Document (PRD) that:
  1. States the exact input/output contract for index() and search() with 
     data types and return value examples
  2. Defines measurable backpressure acceptance criteria 
     (e.g., "queue must never exceed N URLs", "max M concurrent connections")
  3. Lists all required CLI commands and their behavior
  4. Lists explicit success criteria that can be verified by tests
  5. Declares what is explicitly OUT OF SCOPE

Keep scope tight. The grader cares about core correctness and clean design, 
not volume of features. Reject any scope creep.
```

---

## Output Produced
`product_prd.md`

---

## Key Decisions and Rationale

### Decision 1: Exact output format for search()
The assignment says "return relevant URLs" but doesn't specify format. PM Agent decided on `(relevant_url, origin_url, depth)` triples because:
- `origin_url` explains *why* a page was found (which crawl job discovered it)
- `depth` gives the user structural context (how far from origin)
- This matches the style of academic information retrieval systems

### Decision 2: Forbid all third-party libraries
PM Agent noticed the assignment says "language-native functionality." It explicitly listed forbidden libraries in the PRD so Backend Agent could not rationalise using aiohttp (which would have been faster to code with, but would have violated the assignment constraint).

### Decision 3: No web UI
The assignment does not mention a web interface. PM Agent kept scope at CLI only, preventing the Writer/UI Agent from building a Flask server (which would have introduced scope creep and potential bugs).

### Decision 4: Search must work during indexing
The assignment says "we are interested in your thoughts on how the system could be designed such that search can be invoked while the indexer is still active." PM Agent promoted this from a "nice-to-have thought" to a **hard requirement**: search() must actually work concurrently, not just theoretically described.

---

## Interactions with Other Agents

| Agent | Type of Interaction |
|-------|-------------------|
| Systems Architect | Provided PRD as input; Architect could not deviate from its constraints |
| Backend Developer | Provided output format spec; Backend could not change return types |
| QA Agent | PRD success criteria became the test checklist |
| Orchestrator | PM was overruled once: Orchestrator decided to add BM25 score to output (PM had specified 3-tuple; final is 4-tuple with score) |
