# Token-Saving Mode Evaluation — 2026-04-01

## Test Setup

**Query**: "Books in philosophy published in Venice"
**Model**: gpt-4.1
**Test method**: Two identical queries in separate new chat sessions on production (cenlib-rare-books.nurdillo.com)

| Session | Time (UTC) | token_saving | Mode |
|---------|-----------|:---:|------|
| f0db1289 | 12:07:40 | `true` | Lean (default) |
| aa330478 | 12:26:44 | `false` | Full |

## 1. Cost Comparison

### Per-stage breakdown (from LLM logger)

| Stage | Lean (token saving ON) | Full (token saving OFF) | Ratio |
|-------|:--:|:--:|:--:|
| **scholar_interpreter** | 3,835 tok (in=3,564, out=271) / $0.0093 | 3,870 tok (in=3,564, out=306) / $0.0096 | ~1.0x |
| **narrator_streaming** | 3,318 tok (in=1,854, out=1,464) / $0.0154 | 9,064 tok (in=7,199, out=1,865) / $0.0293 | **2.7x tokens, 1.9x cost** |
| **Total** | **7,153 tok / $0.0247** | **12,934 tok / $0.0389** | **1.8x tokens, 1.6x cost** |
| **Response time** | ~24 sec | ~34 sec | +10 sec |

### Key observations

- The interpreter stage is identical (same grounding data, same input prompt).
- The difference is entirely in the narrator: the lean prompt sends **1,854 input tokens** vs the full prompt's **7,199** (3.9x reduction in narrator input context).
- Output lengths are similar (1,464 vs 1,865 tokens) — both produce comprehensive responses.

## 2. Quality Comparison

### 2a. Accuracy

**Both responses are equally accurate.** Both identify the same **10 works** with correct bibliographic details (title, printer, year, Primo catalog links). No factual errors detected in either response.

**Verdict: Tie**

### 2b. Coverage

| Aspect | Lean (default) | Full |
|--------|:--:|:--:|
| All 10 works listed | Yes | Yes |
| Publisher names | Yes | Yes |
| Dates | Yes | Yes |
| Primo links | Yes (all 10) | Yes (all 10) |
| Subject headings | No | Partial |
| Wikipedia links for key figures | No | Yes (Halevi, Abravanel, Manutius) |
| Contextual grouping | 4 groups | 4 groups |
| Historical context section | Yes (general narrative) | Yes (with inline catalog links) |

Full mode adds **Wikipedia enrichment links** for key figures and **inline catalog references** in the contextual section, giving the reader more scholarly entry points.

**Verdict: Full mode slightly better** — Wikipedia enrichment and inline references add depth.

### 2c. Logical Narrative

| Aspect | Lean (default) | Full |
|--------|:--:|:--:|
| Opening | Broad contextual intro about Venice | Concise holdings-first intro |
| Structure | Context -> Holdings -> Context -> Conclusion | Holdings -> Context -> Conclusion |
| Flow | Top-down (city first, then works) | Bottom-up (works first, then city) |
| Redundancy | Some overlap between intro and conclusion | Minimal overlap |
| Style | More essayistic, historian's voice | More reference-oriented, scannable |

For a **bibliographic discovery tool**, the full mode's structure is arguably better — it answers "what do you have?" first, then contextualizes.

**Verdict: Full mode marginally better** for this use case.

## 3. Summary

| Dimension | Winner | Margin |
|-----------|--------|--------|
| **Cost** | Lean (default) | **1.6x cheaper, 10 sec faster** |
| **Accuracy** | Tie | Identical grounding data |
| **Coverage** | Full | Small — Wikipedia links, inline refs |
| **Narrative** | Full | Marginal — more scannable structure |

## 4. Conclusion

The token-saving mode delivers **~95% of the quality at ~60% of the cost**. The full mode adds Wikipedia enrichment and slightly more structured presentation, but the core content (10 books + evidence + Primo links) is identical.

**Recommendation**: Token saving ON (default) is the right tradeoff for most users. Full mode is worth enabling when a polished, link-rich scholarly response is desired.

## 5. Technical Note: Streaming Bug Fixed During This Test

During testing, a race condition was discovered where the **first query in a new session** showed no response. Root cause: the `session_created` WebSocket handler in `Chat.tsx` called `setSessionId()` without also calling `setRestoredSessionId()`, causing a `useEffect` to trigger `restoreSession()` which overwrote the messages array mid-stream. Fix: added `setRestoredSessionId(newSessionId)` before `setSessionId(newSessionId)` (1-line fix). Deployed and verified via Playwright on production.
