# Scripts Directory Cleanup Plan

## Overview

Transform scripts/ from RAG platform to rare books bot MARC XML system.

**Strategy**: Remove RAG-specific directories, keep infrastructure, create new MARC-specific directories.

---

## 🗑️ REMOVE (RAG-specific, not needed for MARC XML)

### 1. **`agents/`** - Remove entirely
- **Contents**: Email orchestrators, image insight, action item extractors
- **Reason**: MARC XML doesn't need agentic email processing or image analysis
- **Files**: 10 files (~3-5KB total)

### 2. **`categorization/`** - Remove entirely
- **Contents**: Document category discovery
- **Reason**: MARC records have explicit classifications (subjects, genres)
- **Files**: 2 files

### 3. **`chunking/`** - Remove entirely
- **Contents**: Text chunking for RAG (chunker_v3, rules)
- **Reason**: MARC has structured fields, not free text needing chunking
- **Files**: 5 files (~10KB total)

### 4. **`connectors/`** - Remove entirely
- **Contents**: Outlook connector, WSL helper
- **Reason**: Not ingesting emails, only MARC XML
- **Files**: 4 files (~15KB total)

### 5. **`embeddings/`** - Remove entirely
- **Contents**: BGE embedder, LiteLLM embedder, FAISS indexing, unified embedder
- **Reason**: Using SQLite fielded queries, not vector embeddings
- **Files**: 9 files (~25KB total)

### 6. **`interface/`** - Remove entirely
- **Contents**: ask_interface.py (RAG Q&A interface)
- **Reason**: Will build new query interface for QueryPlan → SQL → CandidateSet
- **Files**: 2 files

### 7. **`pipeline/`** - Remove entirely
- **Contents**: runner.py, legacy runners (RAG pipeline orchestration)
- **Reason**: Different pipeline: MARC parse → normalize → index → query
- **Files**: 4 files (~20KB total)

### 8. **`prompting/`** - Remove entirely
- **Contents**: prompt_builder.py (RAG context assembly)
- **Reason**: Will build new prompt system for evidence-based Q&A over CandidateSet
- **Files**: 2 files

### 9. **`retrieval/`** - Remove entirely
- **Contents**: FAISS retrievers, email multi-aspect retrieval, image retrieval
- **Reason**: Using SQLite queries, not vector similarity search
- **Files**: 11 files (~30KB total)

### 10. **`ui/`** - Remove entirely
- **Contents**: Streamlit UI for RAG (project manager, Outlook setup, custom pipeline)
- **Reason**: CLI-first for POC, may build MARC-specific UI later
- **Files**: 9 files (~40KB total)

### 11. **`tools/`** - Remove entirely
- **Contents**: Outlook helper deployment tools
- **Reason**: Not using Outlook connector
- **Files**: 2+ files/dirs

### 12. **`ingestion/`** - Remove entirely (will recreate)
- **Contents**: PDF, DOCX, PPTX, email loaders, ingestion manager
- **Reason**: Not ingesting documents, only MARC XML
- **Action**: Delete directory, create new `scripts/marc/` for MARC parsing
- **Files**: 11 files (~30KB total)

**Total to remove: ~12 directories, ~70 files, ~200KB**

---

## ✅ KEEP (useful infrastructure)

### 1. **`core/`** - Keep entirely ✓
- **Contents**: project_manager.py, README
- **Reason**: ProjectManager handles config, paths, logging - useful for any project
- **Files**: 3 files
- **Action**: May need minor adaptations for MARC data paths

### 2. **`utils/`** - Keep partially ✓
- **Keep**:
  - `logger.py` - Structured JSON logging (essential)
  - `logger_context.py` - Logger context manager
  - `task_paths.py` - Per-run artifact paths (essential)
  - `config_loader.py` - YAML config loading (useful)
  - `run_logger.py` - Run-level logging
- **Remove**:
  - `chunk_utils.py` - Chunking utilities (not needed)
  - `email_utils.py` - Email cleaning (not needed)
  - `image_utils.py` - Image extraction (not needed)
  - `msg2email.py` - Email conversion (not needed)
  - `translation_utils.py` - Translation (not needed)
  - `ui_utils.py` - UI helpers (not needed)
  - `create_demo_pptx.py` - Demo file generator (not needed)
- **Action**: Remove 7 files, keep 5 core utilities

---

## 🔄 ADAPT (partial keep, need changes)

### 1. **`api_clients/`** - Adapt
- **Current**: openai/batch_embedder.py, openai/completer.py
- **Keep**: `openai/completer.py` (for LLM calls in M4/M5)
- **Remove**: `openai/batch_embedder.py` (no embeddings)
- **Action**: Keep directory structure, remove embedder, keep completer

### 2. **`index/`** - Adapt (rebuild from scratch)
- **Current**: inspect_faiss.py (FAISS inspection)
- **Remove**: All current files
- **Create new**:
  - `build_index.py` - Build SQLite bibliographic index (M2)
  - `schema.sql` - SQLite schema definition (M2)
- **Action**: Delete current files, will populate with new M2 code

---

## ➕ CREATE NEW (MARC-specific directories)

### 1. **`scripts/marc/`** - NEW
- **Purpose**: MARC XML parsing and canonical record extraction (M1)
- **Files to create**:
  - `parse.py` - Main MARC XML parser
  - `models.py` - CanonicalRecord, Provenance data models
  - `field_extractors.py` - Extract specific MARC fields
  - `__init__.py`

### 2. **`scripts/normalization/`** - NEW
- **Purpose**: Normalize dates, places, agents (M3)
- **Files to create**:
  - `date_normalizer.py` - Date parsing → date_start/date_end + confidence
  - `place_normalizer.py` - Place name normalization
  - `agent_normalizer.py` - Author/contributor normalization
  - `models.py` - NormalizedDate, NormalizedPlace, etc.
  - `__init__.py`

### 3. **`scripts/query/`** - NEW
- **Purpose**: QueryPlan compilation and execution (M4)
- **Files to create**:
  - `compile.py` - NL query → QueryPlan (JSON)
  - `execute.py` - QueryPlan → SQL → CandidateSet + Evidence
  - `models.py` - QueryPlan, CandidateSet, Evidence schemas
  - `__init__.py`

---

## 📋 Execution Plan

### Phase 1: Remove RAG-specific directories (safe, no dependencies)
```bash
rm -rf scripts/agents/
rm -rf scripts/categorization/
rm -rf scripts/chunking/
rm -rf scripts/connectors/
rm -rf scripts/embeddings/
rm -rf scripts/interface/
rm -rf scripts/pipeline/
rm -rf scripts/prompting/
rm -rf scripts/retrieval/
rm -rf scripts/tools/
rm -rf scripts/ui/
rm -rf scripts/ingestion/
```

### Phase 2: Clean up utils/ directory
```bash
cd scripts/utils/
rm -f chunk_utils.py email_utils.py image_utils.py msg2email.py \
      translation_utils.py ui_utils.py create_demo_pptx.py
# Keep: logger.py, logger_context.py, task_paths.py, config_loader.py, run_logger.py
```

### Phase 3: Clean up api_clients/
```bash
rm -f scripts/api_clients/openai/batch_embedder.py
# Keep: scripts/api_clients/openai/completer.py
```

### Phase 4: Clean up index/ (prepare for rebuild)
```bash
rm -f scripts/index/inpect_faiss.py
# Will create: build_index.py, schema.sql in M2
```

### Phase 5: Create new MARC-specific directories
```bash
mkdir -p scripts/marc/
mkdir -p scripts/normalization/
mkdir -p scripts/query/
# Will populate in M1, M3, M4 respectively
```

### Phase 6: Update scripts/README.md
- Remove RAG pipeline documentation
- Add rare books bot mission and structure
- Document new directories (marc, normalization, query)

---

## Final Structure (after cleanup)

```
scripts/
├── __init__.py
├── README.md (updated)
├── api_clients/
│   ├── __init__.py
│   └── openai/
│       ├── __init__.py
│       └── completer.py          # LLM completion (keep)
├── core/
│   ├── __init__.py
│   ├── README.md
│   └── project_manager.py        # Config/paths (keep)
├── index/
│   └── __init__.py               # Empty, will populate in M2
├── marc/                          # NEW - M1
│   └── __init__.py               # To be created
├── normalization/                 # NEW - M3
│   └── __init__.py               # To be created
├── query/                         # NEW - M4
│   └── __init__.py               # To be created
└── utils/
    ├── __init__.py
    ├── README.md
    ├── config_loader.py          # YAML config (keep)
    ├── logger.py                 # Logging (keep)
    ├── logger_context.py         # Logger context (keep)
    ├── run_logger.py             # Run logging (keep)
    └── task_paths.py             # Artifact paths (keep)
```

**Summary**:
- Remove: 12 directories, ~70 files, ~200KB
- Keep: 3 directories, ~10 files (core infrastructure)
- Create: 3 new directories (marc, normalization, query)

---

## Commit Strategy

**Commit 1**: Remove RAG-specific directories
- Message: "Remove RAG-specific directories from scripts/"
- Include: agents, categorization, chunking, connectors, embeddings, interface, pipeline, prompting, retrieval, tools, ui, ingestion

**Commit 2**: Clean up utils and api_clients
- Message: "Remove RAG-specific utilities and embedder"
- Include: utils cleanup (7 files), api_clients/openai/batch_embedder.py

**Commit 3**: Prepare index directory and create new structure
- Message: "Prepare scripts for MARC XML implementation"
- Include: Clear index/, create marc/, normalization/, query/ dirs, update README.md

---

## Dependencies Check

Before removing, verify no critical dependencies in:
- `app/cli.py` - May reference removed modules
- `tests/` - May have tests for removed modules
- `configs/chunk_rules.yaml` - Used by chunking (can remove)

**Action**: After cleanup, will need to update app/cli.py and remove obsolete tests.
