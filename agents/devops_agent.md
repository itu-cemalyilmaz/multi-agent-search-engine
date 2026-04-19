# Agent: DevOps / Deployment Agent

## Role Definition
The DevOps Agent reviews the completed single-machine prototype and writes an honest, technically-specific critique of its production limitations along with concrete upgrade paths. It does not build features — it evaluates architecture.

**Key principle:** The DevOps Agent is intentionally adversarial toward the prototype. Its job is to find what breaks at scale, not to validate what works at small scale.

---

## Task Claimed from Shared Task List

```
You are the DevOps Engineer. Review the completed web crawler prototype:

Architecture summary:
  - URL frontier: asyncio.Queue(maxsize=1000) — in-memory, single process
  - Concurrency throttle: asyncio.Semaphore(10) — per-process limit
  - Deduplication: Python set[str] + SQLite INSERT OR IGNORE
  - Storage: SQLite with WAL mode, FTS5 virtual table
  - Search: SQLite FTS5 MATCH with BM25 rank

Write a production recommendation document (1–2 paragraphs) that:
  1. For each component above: state the exact failure mode at scale 
     (not "it won't scale" — be specific: "at 1M URLs, the set uses ~100MB
      of RAM and is lost on crash")
  2. Name the specific production technology that replaces it and WHY
     that technology addresses the specific failure mode
  3. Describe what a distributed, multi-node crawler architecture 
     looks like using those production technologies
  4. Mention any operational concerns (monitoring, rate limiting, 
     robots.txt compliance) for a production deployment

Be technically precise. Name versions and tools. Write for a senior engineer audience.
```

---

## Output Produced
`recommendation.md`

---

## Key Findings and Recommendations

### Component 1: asyncio.Queue → Apache Kafka

**Prototype failure mode:** The in-memory queue holds at most 1,000 URLs. Every URL lives only in RAM — if the process crashes (OOM, SIGKILL, power failure), the entire pending frontier is lost. More critically, a single queue in a single process cannot be shared across multiple crawler machines.

**Production replacement:** Apache Kafka (or RabbitMQ for lighter deployments). Kafka is a distributed, persistent log — each URL becomes a message on a `urls-to-crawl` topic. URLs survive process restarts. Multiple consumer groups (crawler fleets) can read from the same topic independently. Back-pressure is implemented via consumer group lag monitoring (Prometheus + alerting).

### Component 2: visited set → Redis Bloom Filter

**Prototype failure mode:** The `visited: set[str]` grows at ~60–80 bytes per URL. At 10 million URLs, it consumes ~600MB–800MB of RAM. At 100 million, it exceeds typical server RAM. More critically: it lives in a single process — a second crawler machine cannot share the dedup state.

**Production replacement:** Redis Bloom Filter (via RedisBloom module). Bloom filters provide probabilistic O(1) membership checking with ~1–2% false positive rate using <1% of the memory of an exact set. At 1 billion URLs, a Redis Bloom Filter uses ~1.2GB vs ~60GB for a Python set. It is a shared, network-accessible service — all crawler nodes check the same filter.

### Component 3: SQLite FTS5 → Elasticsearch

**Prototype failure mode:** SQLite uses file-level locking for writes, even with WAL mode. A single writer (the crawler) and multiple readers (search queries) work fine — but multiple simultaneous writers (two crawler processes) immediately cause deadlocks. The FTS5 index lives on a single disk and cannot be sharded or replicated.

**Production replacement:** Elasticsearch. ES shards the index across multiple data nodes, each handling a subset of documents. Writes are asynchronous (near-real-time, ~1s delay from index to searchable). BM25 scoring is configurable. The REST API allows search queries from any service, not just code on the same machine.

### Component 4: Fixed asyncio.Semaphore → Kubernetes Autoscaling

**Prototype failure mode:** `asyncio.Semaphore(10)` is a per-process limit. It cannot enforce per-domain rate limits (crawler might hit one domain with all 10 slots). It provides no visibility to operations teams. It cannot dynamically adjust to server health signals.

**Production replacement:** Kubernetes pod autoscaling: each crawler worker runs as an independent pod. A custom rate-limiter service (or Nginx with rate_limit) enforces per-domain limits. Horizontal Pod Autoscaler scales worker count based on Kafka consumer group lag.

---

## Operational Concerns Flagged

1. **robots.txt compliance**: Production crawlers must respect `robots.txt`. Current implementation ignores it entirely — this would make tool legally and ethically problematic on real sites.

2. **SSL verification**: Current implementation disables SSL certificate verification for convenience. Production deployment must use a proper SSL context.

3. **Rate limiting per domain**: Without per-domain throttling, the crawler can accidentally DDoS a small website. Production needs a per-domain request rate limit (e.g., max 1 req/sec per domain).

4. **Monitoring**: No metrics are exported to Prometheus or similar. Production deployment needs queue depth, crawl rate, error rate, and latency monitoring.

---

## Interactions with Other Agents

| Agent | Type of Interaction |
|-------|-------------------|
| Backend Developer | Reviews Backend's code for scalability issues |
| Systems Architect | Reviews Architect's schema and concurrency decisions |
| Orchestrator | Findings feed into README and multi_agent_workflow.md |
| PM Agent | Some out-of-scope items (robots.txt, rate limiting) could become v3.0 requirements |
