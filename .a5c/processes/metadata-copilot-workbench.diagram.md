# Metadata Co-pilot Workbench - Architecture Diagram

```
                          METADATA CO-PILOT WORKBENCH
                          ===========================

  ┌──────────────────────────────────────────────────────────────────┐
  │                    React Frontend (frontend/)                    │
  │                                                                  │
  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
  │  │  Dashboard   │  │  Workbench   │  │    Agent Chat         │  │
  │  │              │  │              │  │                       │  │
  │  │ Coverage     │  │ Data Tables  │  │ [PlaceAgent]  ───┐   │  │
  │  │ Charts       │  │ Inline Edit  │  │ [DateAgent]   ───┤   │  │
  │  │ Gap Cards    │  │ Batch Ops    │  │ [PublAgent]   ───┤   │  │
  │  │ Trends       │  │ Primo Links  │  │ [AgentAgent]  ───┘   │  │
  │  └──────┬───────┘  └──────┬───────┘  └──────────┬────────── │  │
  │         │                 │                      │           │  │
  │  ┌──────┴─────────────────┴──────────────────────┴────────┐  │  │
  │  │              Corrections Review Page                    │  │  │
  │  │   Timeline │ Filters │ Impact │ Undo │ Export           │  │  │
  │  └────────────────────────────────────────────────────────┘  │  │
  └────────────────────────────┬─────────────────────────────────┘
                               │ REST API / WebSocket
  ┌────────────────────────────┴─────────────────────────────────┐
  │                   FastAPI Backend (app/api/)                   │
  │                                                               │
  │  Existing:                    New (metadata.py router):       │
  │  ├─ POST /chat               ├─ GET  /metadata/coverage      │
  │  ├─ GET  /health              ├─ GET  /metadata/issues        │
  │  ├─ GET  /sessions/{id}       ├─ GET  /metadata/unmapped      │
  │  └─ WS   /ws/chat             ├─ GET  /metadata/clusters      │
  │                                ├─ GET  /metadata/methods       │
  │                                ├─ POST /metadata/corrections   │
  │                                ├─ POST /metadata/corrections/batch │
  │                                ├─ GET  /metadata/corrections/history │
  │                                ├─ POST /metadata/primo-urls    │
  │                                ├─ POST /metadata/agent/chat    │
  │                                └─ WS   /ws/metadata/agent      │
  └────────────────────────────┬─────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
  ┌───────┴───────┐   ┌───────┴───────┐   ┌───────┴───────┐
  │  Grounding    │   │  Specialist   │   │   Action      │
  │   Layer       │   │   Agents      │   │   Layer       │
  │               │   │               │   │               │
  │ ┌───────────┐ │   │ ┌───────────┐ │   │ ┌───────────┐ │
  │ │ M3 SQLite │ │   │ │PlaceAgent │ │   │ │Alias Maps │ │
  │ │ Database  │ │   │ │           │ │   │ │  (JSON)   │ │
  │ └───────────┘ │   │ │ Grounding │ │   │ └───────────┘ │
  │ ┌───────────┐ │   │ │ + LLM     │ │   │ ┌───────────┐ │
  │ │Alias Maps │ │   │ └───────────┘ │   │ │Review Log │ │
  │ │  (read)   │ │   │ ┌───────────┐ │   │ │ (JSONL)   │ │
  │ └───────────┘ │   │ │DateAgent  │ │   │ └───────────┘ │
  │ ┌───────────┐ │   │ │           │ │   │ ┌───────────┐ │
  │ │Country    │ │   │ │ Hebrew    │ │   │ │Re-index   │ │
  │ │Codes      │ │   │ │ Calendar  │ │   │ │ Trigger   │ │
  │ └───────────┘ │   │ │ + LLM     │ │   │ └───────────┘ │
  │ ┌───────────┐ │   │ └───────────┘ │   │ ┌───────────┐ │
  │ │Authority  │ │   │ ┌───────────┐ │   │ │Coverage   │ │
  │ │URIs/VIAF  │ │   │ │PublAgent  │ │   │ │ Refresh   │ │
  │ └───────────┘ │   │ └───────────┘ │   │ └───────────┘ │
  │               │   │ ┌───────────┐ │   │               │
  │               │   │ │AgentAgent │ │   │               │
  │               │   │ │(Names/    │ │   │               │
  │               │   │ │ Authority)│ │   │               │
  │               │   │ └───────────┘ │   │               │
  └───────────────┘   └───────────────┘   └───────────────┘
```

## Data Flow

```
  Audit Module          Clustering          Agent Chat
  ┌─────────┐          ┌─────────┐         ┌─────────┐
  │ Query DB │ ──────> │ Group   │ ──────> │ LLM     │
  │ for gaps │         │ by type │         │ proposes │
  └─────────┘         └─────────┘         │ fixes   │
                                          └────┬────┘
                                               │
                                          ┌────▼────┐
                                          │Librarian│
                                          │ Reviews │
                                          └────┬────┘
                                               │
                             ┌─────────────────┼──────────────────┐
                             │                 │                  │
                        ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
                        │ Approve │       │ Reject  │       │  Edit   │
                        └────┬────┘       └────┬────┘       └────┬────┘
                             │                 │                  │
                        ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
                        │ Update  │       │ Log to  │       │ Update  │
                        │ Alias   │       │ Review  │       │ + Log   │
                        │ Map     │       │ Log     │       │         │
                        └────┬────┘       └─────────┘       └────┬────┘
                             │                                    │
                        ┌────▼────────────────────────────────────▼────┐
                        │           Re-normalize affected records      │
                        │           Update M3 database                 │
                        │           Refresh coverage stats             │
                        └─────────────────────────────────────────────┘
```

## Agent Architecture (per specialist)

```
  ┌──────────────────────────────────────────────┐
  │              Specialist Agent                 │
  │                                              │
  │  ┌──────────────────────────────────────┐    │
  │  │  GROUNDING LAYER (Deterministic)     │    │
  │  │                                      │    │
  │  │  - Query M3 DB for gaps              │    │
  │  │  - Load alias maps                   │    │
  │  │  - Cross-reference country codes     │    │
  │  │  - Check authority URIs              │    │
  │  │  - Cluster by frequency/pattern      │    │
  │  │  - Count affected records            │    │
  │  └──────────────┬───────────────────────┘    │
  │                 │ Evidence                    │
  │  ┌──────────────▼───────────────────────┐    │
  │  │  REASONING LAYER (LLM-Assisted)     │    │
  │  │                                      │    │
  │  │  STRICT System Prompt:               │    │
  │  │  - "You are a bibliographic          │    │
  │  │    metadata specialist"              │    │
  │  │  - Existing alias map as vocabulary  │    │
  │  │  - Country code as evidence          │    │
  │  │  - Structured JSON response only     │    │
  │  │  - confidence < 0.7 = "uncertain"    │    │
  │  │                                      │    │
  │  │  Outputs: ProposedMapping            │    │
  │  │  {canonical, confidence, reasoning}  │    │
  │  └──────────────┬───────────────────────┘    │
  │                 │ Proposals                   │
  │  ┌──────────────▼───────────────────────┐    │
  │  │  CACHE LAYER                         │    │
  │  │                                      │    │
  │  │  - LLM responses cached (JSONL)      │    │
  │  │  - Rejected proposals logged         │    │
  │  │  - Never re-propose rejected items   │    │
  │  └─────────────────────────────────────┘    │
  └──────────────────────────────────────────────┘
```
