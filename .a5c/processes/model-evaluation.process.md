# Model Evaluation — Process Overview

## Overview
Implement model evaluation & cost optimization infrastructure on branch `feature/model-evaluation`. LiteLLM migration + config-driven model selection + batch evaluation CLI + frontend compare mode.

## Phases

### Phase 1: Infrastructure
- Task 1: Config module (`scripts/models/config.py`) + update litellm dependency
- Task 2: LLM client wrapper (`scripts/models/llm_client.py`)
- Shell: Run Phase 1 tests
- Shell: Commit

### Phase 2: Migration
- Task 3: Migrate `interpreter.py` from OpenAI Responses API to litellm
- Task 4: Migrate `narrator.py` (sync, stream, meta extraction)
- Task 5: Migrate cost tracking in `llm_logger.py`
- Task 6: Migrate legacy compiler + agent harness
- Shell: Run regression tests
- Shell: Commit

### Phase 3: Evaluation Framework
- Tasks 7-9: Build query set module, LLM-as-judge, report generator, CLI
- Curate 20-30 benchmark queries from actual database
- Shell: Run eval tests
- Shell: Commit

### Phase 4: UI Comparison Mode
- Task 10: `/chat/compare` API endpoint
- Task 11: Frontend components (ModelSelector, CompareMode)
- Shell: Frontend build check
- Shell: Commit

### Phase 5: Integration & Verification
- [BREAKPOINT] Approve API calls for integration test
- Task 12: End-to-end verification
- Documentation updates
- Shell: Final commit

## Breakpoints
- Phase 5: Before integration test that makes LLM API calls (costs tokens)

Minimal breakpoints per user profile (breakpointTolerance: minimal).
