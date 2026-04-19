# Production Deployment Recommendation

**Author:** DevOps Agent

## Current Limitations

The prototype uses Python's `asyncio.Queue` for the URL frontier (in-memory, single-process), `asyncio.Semaphore` for concurrency control, and SQLite with WAL mode for both storage and full-text search via FTS5. While this architecture elegantly demonstrates the core concepts on a single machine, it has clear scaling ceilings: the in-memory queue is lost on process crash (partially mitigated by the frontier table), SQLite's single-writer model becomes a bottleneck beyond millions of rows, and the entire system is bound to a single CPU and its local disk I/O.

## Production Architecture

For a production deployment handling billions of pages, I recommend replacing each component with its distributed equivalent. The in-memory `asyncio.Queue` should be replaced by **Apache Kafka** or **RabbitMQ**, which provide persistent, partitioned topic queues that can distribute URL work items across hundreds of consumer nodes, with built-in dead-letter queues for failed fetches and configurable backpressure via consumer group lag monitoring. URL deduplication, currently handled by a Python `set()`, should be offloaded to **Redis Bloom Filters** which provide probabilistic O(1) membership checks with less than 1% false positive rate, using a fraction of the memory that an exact set would require at billion-URL scale. Finally, SQLite with FTS5 should be replaced by **Elasticsearch** (or **Typesense** for a lighter alternative), which distributes the full-text index across shards on multiple nodes, supports sophisticated BM25+ ranking, faceted search, and handles concurrent writes from multiple crawler instances without the single-writer constraint. The crawler workers themselves should be deployed as containerized microservices (e.g., on **Kubernetes**) to enable horizontal scaling, with **Prometheus** and **Grafana** providing observability into queue depths, crawl rates, and error rates across the fleet.
