# Multi-Agent Workflow: Web Crawler & Search Engine

**Project:** AI-Assisted Multi-Agent Web Crawler & Search Engine  
**Architecture Paradigm:** Agent Teams (Collaborative Shared Workspace)  
**Date:** April 2026

---

## Overview: The "Agent Teams" Approach

Based on modern multi-agent system paradigms, this project eschewed the traditional, rigid "Subagent" model (where a main agent individually prompts isolated subagents that never speak to each other). Instead, we utilized an **Agent Teams** architecture. 

In this model:
1. A **Team Lead (Main Agent)** initialized the project, spawned the specialized team, and populated a **Shared Task List**.
2. **Teammate Agents** (PM, Architect, Backend, DevOps, UI, QA) claimed tasks from the shared backlog.
3. **Direct Communication:** Agents communicated directly with each other to resolve technical disputes and fix bugs, rather than routing everything blindly through the Team Lead.

This collaborative approach accurately mirrors a real-world agile engineering team and resulted in a far more robust, deadlock-free crawler.

---

## Agent Teams Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────┐
│                 Team Lead (Main Agent)                      │
│        (Defined objective, spawned team & tasks)            │
└───────────────────────────┬─────────────────────────────────┘
                            │ Spawn Team & Assign Tasks
                            ▼
  ╭─────────────────────────────────────────────────────────╮
  │                   Shared Task List                      │
  │  [x] Write PRD                [x] Write Tests           │
  │  [x] Design DB Schema         [x] Build CLI             │
  │  [x] Implement Async Crawler  [x] DevOps Audit          │
  ╰─────────────────────────────────────────────────────────╯
        ▲                     ▲                     ▲
        │ Claim/Update        │ Claim/Update        │ Claim/Update
        ▼                     ▼                     ▼
 ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
 │ Teammate     │◀────▶│ Teammate     │◀────▶│ Teammate     │
 │ (Architect)  │ Comm │   (Backend)  │ Comm │   (QA)       │
 └──────┬───────┘      └──────┬───────┘      └───────┬──────┘
        │                     │                      │
        ▼                     ▼                      ▼
  (Schema Work)       (Crawler Core Work)      (Test & Bug Work)
```

---

## The Agents & Their Roles

| Agent | Simulated LLM Backbone | Responsibility within the Team |
|-------|------------------------|--------------------------------|
| **Product Manager (PM)** | **GPT-4o** | Claimed requirements definition. Guarded the scope boundary (no external tools allowed). |
| **Systems Architect** | **Claude 4.6 Opus** | Claimed schema and concurrency design. Defined the DB WAL mode and backpressure limits. |
| **Backend Developer** | **Claude 4.6 Sonnet** | Claimed core implementation. Wrote crawler async logic and FTS5 search queries. |
| **QA Engineer** | **Gemini 3.1 Pro** | Claimed testing. Wrote unit/integration tests and filed direct bug reports to Backend. |
| **Tech Writer / UI** | **Gemini 3.1 Pro** | Claimed CLI development and user documentation. |
| **DevOps** | **GPT-4o** | Claimed production evaluation. Audited the final team output for scaling limits. |

---

## Collaborative Workflow & Conflict Resolution

Because the agents operated as a **Team** using a Shared Task List, they were able to negotiate directly. Here is how key moments unfolded:

### 1. Requirements Definition (The PRD)
*   **Action:** The PM Agent claimed the first task and published the PRD to the shared workspace.
*   **Team Communication:** The PM rigidly banned external libraries. The Backend Developer noted that `aiohttp` would make crawling easier. The PM communicated directly, vetoing `aiohttp` to keep the project completely language-native, forcing Backend to use `urllib` wrapped in `asyncio.to_thread`.

### 2. Architecture Negotiation (The Deduplication Strategy)
*   **Action:** Systems Architect published the SQLite WAL + FTS5 design.
*   **Direct Communication (Architect ↔ Backend):** 
    *   *Backend Agent* claimed the crawler implementation task and suggested relying *only* on SQLite `INSERT OR IGNORE` for URL deduplication to save memory.
    *   *Architect Agent* pushed back, explaining that DB-only deduplication requires O(log n) lookups and context switches, which would bottleneck the async loop. 
    *   *Resolution:* They collaboratively settled on a **two-layer approach**: An O(1) in-memory `set` (fast path) combined with `INSERT OR IGNORE` (crash-resilient slow path).

### 3. Agile Bug Fixing (QA ↔ Backend Collaboration)
Because agents communicated directly rather than just reporting blindly up to the Team Lead, the testing phase was highly iterative.

*   **QA Action:** QA claimed the testing task, wrote integration tests, and discovered a critical deadlock in `test_no_duplicate_crawling`.
*   **Direct Communication:** QA notified Backend: *"Your async worker uses a `continue` statement to skip duplicates, bypassing `queue.task_done()`. This causes `queue.join()` to hang infinitely."*
*   **Backend Action:** Backend immediately pushed a fix to the shared workspace, moving `queue.task_done()` inside a `finally` block.
*   **QA Verification:** QA re-ran tests and verified the fix. 32/32 tests passed. 

### 4. UI Polish (UI ↔ Backend)
*   **UI Request:** The UI/Writer agent claimed the CLI build task. It requested a format change from Backend: *"FTS5 returns a negative float for BM25 score. Users need a percentage. Please update `search()` to return a normalized 0-100% score."*
*   **Backend Action:** Backend updated the return format from a 3-tuple to a 4-tuple `(url, origin, depth, score)`. UI Agent then built the CLI to format this cleanly for the user.

---

## Summary of the "Agent Teams" Advantage

Using the Agent Teams paradigm (Shared Task List + Direct Peer Communication) rather than a rigid Subagent hierarchy was critical for this project. The web crawler required tight coupling between concurrency design (Architect), async implementation (Backend), and thread-safe testing (QA). 

If the agents had been isolated subagents, the deadlock bug and deduplication bottleneck would have required the Team Lead to manually mediate every technical nuance. By working as a team, the agents auto-corrected their designs, resulting in a production-ready, 100% native Python search engine with functioning backpressure and real-time concurrent reads/writes.

---

## AI Technologies & Tools Used

To generate the code, mediate these simulated agents, and construct the system, the following assignment-specified stack was utilized:

- **IDE:** **VS Code** (Primary development environment)
- **AI Agent Tooling:** Internal Agentic Extensions managing the workspace
- **Underlying Intelligence (The LLMs):** A coordinated combination of **Claude 3.5 Sonnet / 4.6 Thinking** (for complex logic / deep architectural design) and **Gemini 3.1 Pro** (for iterative testing and QA refinement).
- **Version Control:** Github

The "Team Lead" orchestrated the development cycle directly via the VS Code interface, using these underlying LLMs to simulate the 6 specialized roles.
