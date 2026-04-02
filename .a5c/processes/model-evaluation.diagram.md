# Model Evaluation — Process Diagram

```
Phase 1: Infrastructure
  Task 1: Config Module + litellm pin
  Task 2: LLM Client Wrapper
  Shell: Run tests
  Shell: Commit
    |
    v
Phase 2: Migration
  Task 3: Migrate interpreter.py
  Task 4: Migrate narrator.py
  Task 5: Migrate cost tracking
  Task 6: Migrate legacy compiler + agent harness
  Shell: Regression tests
  Shell: Commit
    |
    v
Phase 3: Evaluation Framework
  Tasks 7-9: Query set + Judge + Report + CLI
  Shell: Eval tests
  Shell: Commit
    |
    v
Phase 4: UI Comparison
  Task 10: /chat/compare endpoint
  Task 11: Frontend CompareMode + ModelSelector
  Shell: Frontend build
  Shell: Commit
    |
    v
Phase 5: Integration
  [BREAKPOINT] Approve API calls
  Task 12: E2E verification
  Docs update
  Shell: Final commit
    |
    v
  DONE
```
