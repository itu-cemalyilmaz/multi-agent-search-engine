"""
CLI Interface (Technical Writer / UI Agent)
============================================
Interactive command-line interface that allows concurrent indexing and
searching.  Indexing runs in a background daemon thread so the prompt
remains fully responsive for search queries and status checks at all times.

Concurrency model:
  - OS Thread 1 (main):  CLI input loop + search queries
  - OS Thread 2 (daemon): asyncio event loop running the crawler workers
  - SQLite WAL mode:      Readers (Thread 1) and writers (Thread 2) never
                          block each other — queries always return immediately.
"""

import threading
import sys
import os
import time

# Ensure the project root is on sys.path regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import init_db, reset_db
from src.crawler import start_indexing, status as crawler_status, save_frontier_on_interrupt
from src.search import search, get_stats


BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║      Multi-Agent Web Crawler & Search Engine  v2.0      ║
║      ─────────────────────────────────────────────      ║
║  Built with native Python: asyncio · sqlite3 · urllib   ║
╚══════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
Commands:
  index <url> <depth>   Start crawling from <url> up to <depth> hops
  search <query>        Search indexed pages for <query>
  status                Show crawler status and backpressure info
  stats                 Show database statistics and job history
  reset                 Clear all indexed data
  help                  Show this message
  exit / quit           Exit (saves frontier for resume)
"""


def _format_status() -> str:
    """Format the crawler status dict into a readable string."""
    s = crawler_status
    lines = [
        "┌─ Crawler Status ──────────────────────────────┐",
        f"│  Running        : {'✅ Yes' if s['is_running'] else '❌ No (idle)'}",
        f"│  Pages Crawled  : {s['pages_crawled']}",
        f"│  Pages Failed   : {s['pages_failed']}",
        f"│  Active Workers : {s['active_workers']} / 10",
        f"│  Queue Depth    : {s['queue_depth']} / 1000  (backpressure limit)",
        f"│  BP Hits        : {s['backpressure_hits']}  (times queue was full)",
        "└───────────────────────────────────────────────┘",
    ]
    return "\n".join(lines)


def _graceful_exit():
    """Save frontier state then exit."""
    if crawler_status["is_running"]:
        print("⏳ Saving unfinished URLs to frontier for resume...")
        save_frontier_on_interrupt()
    print("Goodbye!")
    os._exit(0)


def cli_loop():
    print(BANNER)
    print(HELP_TEXT)

    while True:
        try:
            raw = input("\n🔍 > ").strip()
            if not raw:
                continue

            parts = raw.split(None, 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            # ---- EXIT ----
            if cmd in ("exit", "quit"):
                _graceful_exit()

            # ---- HELP ----
            elif cmd == "help":
                print(HELP_TEXT)

            # ---- INDEX ----
            elif cmd == "index":
                if crawler_status["is_running"]:
                    print("⚠️  An indexer is already running. Use 'status' to monitor it.")
                    continue

                idx_parts = args.split()
                if len(idx_parts) != 2:
                    print("Usage: index <url> <depth>")
                    continue

                url = idx_parts[0]
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url

                try:
                    depth = int(idx_parts[1])
                    if depth < 0:
                        raise ValueError
                except ValueError:
                    print("Depth must be a non-negative integer.")
                    continue

                t = threading.Thread(
                    target=start_indexing, args=(url, depth), daemon=True
                )
                t.start()
                print(f"🚀 Started indexing {url} (max depth={depth}) in background.")
                print("   ℹ️  Search runs concurrently via SQLite WAL mode.")
                print("   Use 'status' to monitor progress, 'search' to query anytime.")

            # ---- SEARCH ----
            elif cmd == "search":
                if not args:
                    print("Usage: search <query>")
                    continue

                t0 = time.time()
                results = search(args)
                elapsed = time.time() - t0

                if not results:
                    print(f"No results found for '{args}'. ({elapsed:.3f}s)")
                    if crawler_status["is_running"]:
                        print("   (Indexing still running — try again in a moment)")
                else:
                    print(f"\n📄 {len(results)} result(s) for '{args}' "
                          f"({elapsed:.3f}s, ranked by BM25):\n")
                    for i, (url, origin, depth, score) in enumerate(results, 1):
                        print(f"  {i:3d}. [{score:5.1f}%] {url}")
                        print(f"         origin={origin}  depth={depth}")

            # ---- STATUS ----
            elif cmd == "status":
                print(_format_status())

            # ---- STATS ----
            elif cmd == "stats":
                info = get_stats()
                print(f"\n📊 Total indexed pages: {info['total_indexed_pages']}")
                print(f"   (Unique pages only — duplicates prevented by "
                      f"in-memory visited set + DB INSERT OR IGNORE)")
                if info["recent_jobs"]:
                    print("   Recent jobs:")
                    for j in info["recent_jobs"]:
                        live = " ← live counter" if j.get("note") == "live" else ""
                        print(f"     #{j['id']} {j['origin_url']} "
                              f"depth={j['max_depth']} status={j['status']} "
                              f"pages={j['pages_crawled']}{live} "
                              f"at={j['created_at']}")
                else:
                    print("   No jobs recorded yet.")

            # ---- RESET ----
            elif cmd == "reset":
                if crawler_status["is_running"]:
                    print("⚠️  Cannot reset while indexer is running.")
                    continue
                reset_db()
                print("🗑️  All indexed data has been cleared.")

            else:
                print(f"Unknown command: '{cmd}'. Type 'help' for commands.")

        except KeyboardInterrupt:
            print("\n")
            _graceful_exit()
        except EOFError:
            _graceful_exit()
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    init_db()
    cli_loop()
