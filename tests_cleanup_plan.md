# Tests Directory Cleanup Plan

## Overview

Remove test files that correspond to deleted scripts modules, preserving only tests for infrastructure we kept.

---

## 🗑️ REMOVE (Tests for deleted RAG modules)

### 1. **`tests/agents/`** - Remove entirely
- **Tests for**: scripts/agents/ (deleted in Phase 1)
- **Contents**: 8 test files for email orchestrators, image insight agents
- **Reason**: No corresponding code exists

### 2. **`tests/chunking/`** - Remove entirely
- **Tests for**: scripts/chunking/ (deleted in Phase 2)
- **Contents**: 10 test files for text chunking strategies
- **Reason**: MARC doesn't use chunking

### 3. **`tests/connectors/`** - Remove entirely
- **Tests for**: scripts/connectors/ (deleted in Phase 1)
- **Contents**: 2 test files for Outlook connector
- **Reason**: No email/Outlook integration

### 4. **`tests/embeddings/`** - Remove entirely
- **Tests for**: scripts/embeddings/ (deleted in Phase 2)
- **Contents**: Vector counting/embedding tests
- **Reason**: Using SQLite, not embeddings

### 5. **`tests/ingestion/`** - Remove entirely
- **Tests for**: scripts/ingestion/ (deleted in Phase 3)
- **Contents**: 5 test files for PDF/DOCX/XLSX loaders
- **Reason**: Not ingesting documents, only MARC XML

### 6. **`tests/retrieval/`** - Remove entirely
- **Tests for**: scripts/retrieval/ (deleted in Phase 2)
- **Contents**: 6 test files for FAISS retrieval, email retrievers
- **Reason**: Using SQLite queries, not vector retrieval

### 7. **`tests/pipline/`** - Remove (typo directory)
- **Tests for**: scripts/pipeline/ (being repurposed)
- **Contents**: test_pipeline.py (RAG pipeline test)
- **Reason**: Pipeline will be repurposed for MARC workflow, old tests not relevant
- **Note**: Directory name has typo "pipline" instead of "pipeline"

### 8. **`tests/integration/`** - Remove most, keep one
- **Remove**:
  - `email_tests/` - Email integration tests
  - `outlook_tests/` - Outlook integration tests
  - `test_email_full_pipeline.py` - RAG email pipeline
  - `test_phase1_phase2_integration.py` - RAG phase integration
  - `test_new_project.py` - May be RAG-specific
- **Keep**:
  - `test_project_manager.py` - Tests core/project_manager.py (we kept this)

### 9. **`tests/images_completion/`** - Remove entirely
- **Tests for**: Image processing with LLM
- **Contents**: 6 files for image descriptions, cost tracking
- **Reason**: No image processing in MARC system

### 10. **`tests/lite_llm/`** - Remove entirely
- **Tests for**: LiteLLM embeddings (deleted)
- **Contents**: test_light_llm.py
- **Reason**: No longer using LiteLLM for embeddings
- **Note**: May want to add new tests for completer.py later

### 11. **`tests/fixtures/`** - Remove most, keep structure
- **Remove all document fixtures**:
  - `docx/` - DOCX test files
  - `pdf/` - PDF test files
  - `pptx/` - PPTX test files
  - `xlsx/` - XLSX test files
  - `emails/` - Email test files
  - `e2e_ingest/` - End-to-end ingestion fixtures
  - `ingestion_test_data/` - Ingestion test data
  - `demo.pptx` - Demo presentation
- **Keep directory structure**: Empty `fixtures/` for future MARC XML test files

---

## ✅ KEEP (Tests for preserved infrastructure)

### 1. **`tests/loggers/`** - Keep, review files
- **Tests for**: scripts/utils/logger.py, run_logger.py, logger_context.py
- **Contents**: 5 test files for logging infrastructure
- **Keep**:
  - `test_logger.py` - Core logger tests
  - `run_logger_test.py` - Run logger tests
  - `test_context.py` - Context logger tests
- **Remove or update**:
  - `pipe_logger_test.py` - May be RAG pipeline specific
  - `prerun_logger_test.py` - May be RAG specific
  - `test_full_pipeline_logger_redo.py` - RAG pipeline specific
- **Action**: Keep directory, review individual files

### 2. **`tests/utils/`** - Keep partially
- **Tests for**: scripts/utils/
- **Contents**: 3 test files
- **Review each**:
  - `test_logger.py` - Keep (logger still exists)
  - `test_infer_folder.py` - Check if relevant
- **Action**: Keep directory, remove RAG-specific utility tests

### 3. **`tests/integration/test_project_manager.py`** - Keep
- **Tests for**: scripts/core/project_manager.py
- **Reason**: ProjectManager is core infrastructure we kept

---

## ➕ CREATE NEW (MARC-specific test structure)

After cleanup, create new test directories for MARC modules:

```bash
mkdir -p tests/scripts/marc/
mkdir -p tests/scripts/normalization/
mkdir -p tests/scripts/query/
mkdir -p tests/scripts/schemas/
```

Mirror the new scripts structure for clean organization.

---

## 📋 Execution Plan

### Step 1: Remove RAG module tests (safe bulk delete)
```bash
rm -rf tests/agents/
rm -rf tests/chunking/
rm -rf tests/connectors/
rm -rf tests/embeddings/
rm -rf tests/ingestion/
rm -rf tests/retrieval/
rm -rf tests/pipline/  # Note typo
rm -rf tests/images_completion/
rm -rf tests/lite_llm/
```

### Step 2: Clean integration tests (keep project_manager test)
```bash
cd tests/integration/
rm -rf email_tests/ outlook_tests/
rm -f test_email_full_pipeline.py test_phase1_phase2_integration.py test_new_project.py
# Keep: test_project_manager.py and __init__.py
```

### Step 3: Remove RAG fixture files
```bash
cd tests/fixtures/
rm -rf docx/ pdf/ pptx/ xlsx/ emails/ e2e_ingest/ ingestion_test_data/
rm -f demo.pptx
# Keep: directory structure for future MARC XML fixtures
```

### Step 4: Review and clean loggers tests
```bash
cd tests/loggers/
# Remove RAG-specific pipeline logger tests
rm -f pipe_logger_test.py prerun_logger_test.py test_full_pipeline_logger_redo.py
# Keep: run_logger_test.py, test_context.py, test_logger.py
```

### Step 5: Review utils tests
```bash
cd tests/utils/
# Check each file, remove if tests deleted utils
# Keep: test_logger.py if it tests scripts/utils/logger.py
```

### Step 6: Create new MARC test structure
```bash
mkdir -p tests/scripts/marc/
mkdir -p tests/scripts/normalization/
mkdir -p tests/scripts/query/
mkdir -p tests/scripts/core/
mkdir -p tests/scripts/utils/

# Move surviving tests to new structure
mv tests/integration/test_project_manager.py tests/scripts/core/
mv tests/utils/test_logger.py tests/scripts/utils/ 2>/dev/null || true
mv tests/loggers/run_logger_test.py tests/scripts/utils/ 2>/dev/null || true
```

### Step 7: Update test configuration
```bash
# Update pytest.ini if needed
# Remove legacy_chunker marker (no longer relevant)
```

---

## Final Structure (after cleanup)

```
tests/
├── __init__.py
├── fixtures/                          # Empty, for future MARC XML fixtures
├── scripts/                           # NEW organized structure
│   ├── core/
│   │   └── test_project_manager.py   # Kept from integration/
│   ├── utils/
│   │   ├── test_logger.py            # Kept/moved
│   │   └── test_run_logger.py        # Kept/moved
│   ├── marc/                          # NEW - for M1 tests
│   ├── normalization/                 # NEW - for M3 tests
│   ├── query/                         # NEW - for M4 tests
│   └── schemas/                       # NEW - for validation tests
```

---

## Summary

**Remove**: 11 test directories, ~50+ test files, all RAG document fixtures
**Keep**: 2-3 infrastructure test files (project_manager, logger, run_logger)
**Restructure**: Move kept tests to tests/scripts/ organized structure
**Create**: New test directories for MARC modules

**Before**: ~15 test directories testing RAG functionality
**After**: Clean structure ready for MARC XML implementation

---

## Notes

- **pytest.ini**: Remove `legacy_chunker` marker (line 3) - no longer relevant
- **Test coverage**: Start fresh with MARC-specific tests as we implement M1-M5
- **Fixtures**: Keep empty fixtures/ directory for future MARC XML test files
