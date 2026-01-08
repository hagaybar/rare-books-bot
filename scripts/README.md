# Scripts

This directory contains the core Python modules for the rare books bot bibliographic discovery system.

## Mission

Build a structured, deterministic bibliographic engine: **MARC XML → canonical → SQLite → CandidateSet**, with optional LLM planning for query compilation.

## Architecture

The system follows a clear pipeline:

1. **Parse** MARC XML to canonical JSONL (preserving raw values)
2. **Normalize** dates, places, agents with confidence tracking
3. **Index** into SQLite for fielded queries (not embeddings)
4. **Query** via QueryPlan → SQL → CandidateSet with evidence
5. **Answer** complex questions over CandidateSet only

## Directory Structure

### MARC-Specific Modules (New)

- **`marc/`** - MARC XML parsing and canonical record extraction (Milestone M1)
  - Parse MARC XML to canonical JSONL format
  - Extract record_id, title, imprint, subjects, agents, notes
  - Track provenance (MARC fields → values mapping)

- **`normalization/`** - Normalize bibliographic data with confidence (Milestone M3)
  - Date normalization (→ date_start/date_end + confidence)
  - Place/publisher/agent normalization (rule-based)
  - Preserve raw values with explicit reasoning for unparsed data

- **`query/`** - Query compilation and execution (Milestone M4)
  - Compile natural language → QueryPlan (JSON schema validated)
  - Execute QueryPlan → SQL → CandidateSet with evidence
  - Track which MARC fields caused record inclusion

- **`schemas/`** - JSON schemas for validation
  - QueryPlan schema
  - CanonicalRecord schema
  - CandidateSet schema

- **`fixtures/`** - Test data and sample MARC XML
  - Small MARC XML snippets for unit tests
  - Sample canonical records

### Infrastructure (Preserved from RAG Template)

- **`core/`** - Project management and configuration
  - `project_manager.py` - Central class for config, paths, logging
  - Handles project-level setup and directory structure

- **`utils/`** - Core utilities
  - `logger.py` - Structured JSON logging
  - `task_paths.py` - Per-run artifact paths management
  - `config_loader.py` - YAML configuration loading
  - `run_logger.py` - Run-level logging
  - `logger_context.py` - Logger context management

- **`api_clients/`** - External API clients
  - `openai/completer.py` - LLM completion for query planning (M4/M5)

- **`index/`** - Storage and indexing (Milestone M2)
  - SQLite schema definition
  - Index builders for bibliographic data
  - *To be populated in M2*

- **`pipeline/`** - Workflow orchestration
  - Step execution framework
  - Per-run artifact management
  - *To be repurposed for MARC workflow*

## Data Flow

```
MARC XML
   ↓ (M1: parse)
Canonical JSONL (raw values preserved)
   ↓ (M3: normalize)
Normalized data (+ confidence, method)
   ↓ (M2: index)
SQLite database (fielded queries)
   ↓ (M4: query)
QueryPlan → SQL → CandidateSet + Evidence
   ↓ (M5: answer)
LLM-generated answer (grounded in evidence)
```

## Key Principles

1. **Raw values always preserved** - Normalization is never destructive
2. **Deterministic operations** - Parsing/normalization testable without LLM
3. **Evidence-based answers** - Every result must show which MARC fields matched
4. **Confidence tracking** - All normalization includes method + confidence score
5. **Per-run artifacts** - Logs, plans, SQL, and results saved for debugging

## Development Workflow

See `plan.mf` in project root for milestone roadmap (M0-M5).

### Milestones

- **M0**: Repo setup (done)
- **M1**: MARC XML → canonical JSONL (`scripts/marc/`)
- **M2**: SQLite bibliographic index (`scripts/index/`)
- **M3**: Normalization v1 (`scripts/normalization/`)
- **M4**: QueryPlan → CandidateSet (`scripts/query/`)
- **M5**: Complex Q&A over CandidateSet

## Testing

Unit tests should mirror this structure in `tests/scripts/`:
- `tests/scripts/marc/` - MARC parsing tests
- `tests/scripts/normalization/` - Normalization tests
- `tests/scripts/query/` - Query compilation/execution tests

## What Was Removed

This codebase started as a RAG (Retrieval-Augmented Generation) platform. The following were removed as they're not needed for MARC bibliographic discovery:

- **Removed**: Vector embeddings, FAISS retrieval, document chunking
- **Removed**: PDF/DOCX/email loaders, image processing, Streamlit UI
- **Removed**: Email orchestration agents, categorization, connectors

**Preserved**: Core infrastructure (logging, config, paths, project management) that provides value regardless of domain.
