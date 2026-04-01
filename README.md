# Rare Books Bot

A conversational discovery system for rare book collections, built on MARC XML bibliographic records.

**Live:** [cenlib-rare-books.nurdillo.com](https://cenlib-rare-books.nurdillo.com)

## What It Does

Ask questions about a rare books collection in plain language — get precise, evidence-based answers grounded in the actual catalog data.

**Example queries:**
- "Books in philosophy published in Venice"
- "Hebrew books printed by the Bragadin press in the 16th century"
- "Works by Maimonides held in the collection"

The system interprets your question, searches the bibliographic database, and responds with a scholarly narrative citing specific records, MARC fields, and confidence scores. Every answer traces back to the source data — no hallucination, no guesswork.

## How It Works

The system processes MARC XML catalog records through a pipeline that preserves all original data while adding normalized, queryable fields:

```
MARC XML  →  Canonical Records  →  Normalized & Enriched  →  SQLite Index
                                    (dates, places, publishers,
                                     Wikidata, Wikipedia)

User Query  →  Interpret (LLM)  →  Execute (SQL)  →  Narrate (LLM)
                                                       ↓
                                              Streaming response with
                                              evidence and source citations
```

**Key design choices:**
- **MARC XML is the source of truth** — raw values are always preserved alongside any normalization
- **Evidence before narrative** — the system finds matching records first, then explains what it found
- **Confidence-scored** — every normalized value (dates, places, publishers) carries a method tag and confidence score so you know how reliable each interpretation is
- **Deterministic retrieval** — the same query always produces the same candidate set; LLMs are used for interpretation and narration, not for retrieval

## The Collection

Currently configured for the **Sourasky Central Library rare books collection** at Tel Aviv University — nearly 2,800 bibliographic records in 39 languages (Hebrew, Latin, German, Italian, French, Arabic, Yiddish, Ladino, and more) spanning the 13th century to the present, published across 350+ cities worldwide. The system is designed to work with any MARC XML export.

## Capabilities

**Conversational Chat** — Ask questions, get streaming responses with thinking steps and scholarly context. Multi-turn sessions remember your conversation. Ambiguous queries get clarification prompts.

**Metadata Workbench** — Dashboard for improving catalog quality: coverage statistics, specialist agents for place/date/publisher/name normalization, human-in-the-loop correction workflows.

**Network Map** — Interactive geographic visualization showing where books were published and the connections between printing centers.

**Publisher Authorities** — Internal authority system linking variant name forms (Latin, Hebrew, vernacular) to canonical publisher identities.

**QA Framework** — Gold-set regression testing to prevent quality regressions as the system evolves.

## Getting Started

### Prerequisites

- Python 3.11+ (tested on 3.12)
- Node.js 20+
- [Poetry](https://python-poetry.org/) for Python dependency management
- An OpenAI API key (for query interpretation and narration)

### Installation

```bash
git clone https://github.com/hagaybar/rare-books-bot.git
cd rare-books-bot

# Python dependencies
poetry install

# Frontend dependencies
cd frontend && npm install && cd ..

# Environment
export OPENAI_API_KEY="sk-..."
```

### Running Locally

```bash
# Start the API server
uvicorn app.api.main:app --reload        # http://localhost:8000

# Start the frontend (separate terminal)
cd frontend && npm run dev               # http://localhost:5173
```

The MARC XML source file is included in the repository (`data/marc_source/`). To rebuild the database from scratch, use the ingestion pipeline skill:

```bash
/marc-ingest              # Interactive 7-phase rebuild
```

Or run the stages manually:

```bash
python -m app.cli parse-marc data/marc_source/rare_books_with_lod.xml
python -m app.cli query "books printed in Venice"
```

### Running Tests

```bash
pytest                    # all tests
ruff check .              # linting
```

## Documentation

Technical documentation for developers working on the system lives in `docs/current/` — 9 topic files covering the normalization pipeline, query engine, chatbot API, streaming protocol, deployment, and more. See [CLAUDE.md](CLAUDE.md) for the full topic registry.

## Technology

- **Backend:** Python, FastAPI, SQLite, OpenAI API (gpt-4.1)
- **Frontend:** React, TypeScript, Vite, MapLibre GL
- **Deployment:** Docker, nginx reverse proxy
- **Orchestration:** Babysitter (multi-step workflow engine)
