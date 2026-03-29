# Streaming Chat with Thinking Mode — Design Spec

**Date**: 2026-03-28
**Status**: Approved
**Branch**: `feature/auth-security`

---

## Overview

Replace the silent 60-second wait in chat with progressive streaming: a "thinking" phase showing simplified status messages during query processing, followed by word-by-word response streaming from the narrator. Collapsible reasoning toggle after completion.

## Current vs New UX

**Current**: User sends query → 60s silence → full response appears at once.

**New**: User sends query → thinking messages stream in → narrator response streams word-by-word → done with collapsible reasoning.

## WebSocket Protocol

Extend the existing `/ws/chat` with new message types:

| Type | When | Content |
|------|------|---------|
| `session_created` | New session | `{session_id}` |
| `thinking` | During pipeline | `{text: "Found 30 matching records"}` |
| `stream_start` | Narrator begins | `{}` |
| `stream_chunk` | Each narrator token | `{text: "Found 2 books"}` |
| `complete` | Pipeline done | `{response: ChatResponse}` |
| `error` | Any failure | `{message: "..."}` |

### Thinking Messages (Simplified Narrative)

Generated at key pipeline milestones:

1. After interpreter starts: `"Interpreting your query..."`
2. After query compilation: `"Searching for books published in Amsterdam between 1500 and 1599..."`
3. After SQL execution: `"Found 30 matching records"`
4. After enrichment starts: `"Analyzing 12 related scholars..."`
5. After narrator starts: `"Writing response..."`

These are human-readable summaries, not raw technical output.

### Narrator Streaming

Switch narrator's OpenAI call to `stream=True`. Forward each text chunk through the WebSocket as `stream_chunk`. The complete response is still assembled server-side for the final `complete` message (needed for session storage, token counting, etc.).

## Backend Changes

### Pipeline Progress Callback

Add an optional `progress_callback` parameter to the scholar pipeline functions. When provided (WebSocket context), it sends thinking messages:

```python
async def _run_scholar_pipeline(message, session_context, progress_callback=None):
    if progress_callback:
        await progress_callback("thinking", "Interpreting your query...")

    # ... interpreter runs ...

    if progress_callback:
        filter_desc = describe_filters(plan)  # "books in Amsterdam, 16th century"
        await progress_callback("thinking", f"Searching for {filter_desc}...")

    # ... SQL executes ...

    if progress_callback:
        await progress_callback("thinking", f"Found {len(candidates)} matching records")

    # ... enrichment ...

    if progress_callback:
        await progress_callback("thinking", "Writing response...")

    # ... narrator streams ...
```

### Narrator Streaming

In `scripts/chat/narrator.py`, add a streaming mode:

```python
async def narrate_streaming(prompt, context, chunk_callback):
    """Stream narrator response, calling chunk_callback for each token."""
    response = client.chat.completions.create(
        model=model, messages=messages, stream=True
    )
    full_text = []
    for chunk in response:
        text = chunk.choices[0].delta.content
        if text:
            full_text.append(text)
            await chunk_callback(text)
    return "".join(full_text)
```

### WebSocket Endpoint Update

The existing `/ws/chat` handler sends progress/batch/complete messages. Update it to:
1. Pass a `progress_callback` to the pipeline
2. Send `thinking` messages from the callback
3. Send `stream_start` before narrator
4. Forward narrator chunks as `stream_chunk`
5. Send `complete` with full response after narrator finishes

### HTTP /chat Stays Synchronous

No changes to POST `/chat` — it returns the full response as before. Streaming is WebSocket-only.

## Frontend Changes

### Switch Chat to WebSocket

The Chat page currently uses HTTP POST (`fetch('/chat', ...)`). Switch to using the WebSocket for the primary chat flow to get streaming. Keep HTTP as fallback.

### Message Rendering States

**1. Thinking state** — shown during pipeline processing:
```
┌─ 💭 Thinking ────────────────────────┐
│ Found 30 matching records...          │
└───────────────────────────────────────┘
```
- Muted gray/blue background, subtle animated pulse
- Shows latest thinking text (replaces previous, not appended)
- Small text (text-sm), italic

**2. Streaming state** — narrator response appearing:
- Normal message bubble
- Text appears progressively (append each chunk)
- Blinking cursor/caret at the end (CSS animation)

**3. Complete state** — final response:
- Normal message bubble with full content
- Thinking content collapses to:
```
💭 Show reasoning (4 steps)     [▾]
```
- Click expands to show all thinking steps as a list
- Collapsed by default after completion

### Frontend State Machine

```
IDLE → THINKING → STREAMING → COMPLETE
                              ↓
                          (save thinking steps)
                          (collapse thinking box)
```

Per-message state tracked in the chat message store.

## Files

| File | Change |
|------|--------|
| `scripts/chat/narrator.py` | Add `narrate_streaming()` async generator |
| `scripts/chat/interpreter.py` | Add progress callback support |
| `app/api/main.py` | Update `/ws/chat` to use progress callbacks + narrator streaming |
| `frontend/src/pages/Chat.tsx` | Switch to WebSocket, add streaming state machine |
| `frontend/src/components/chat/MessageBubble.tsx` | Add thinking/streaming/complete render modes |
| `frontend/src/components/chat/ThinkingBlock.tsx` | New: collapsible thinking steps component |

## Implementation Notes

- The interpreter call is synchronous (not streaming) — it returns a query plan. Only the narrator streams.
- Token counting: accumulate tokens from the streaming response's final chunk (which includes usage stats) or count chunks.
- Security checks (moderation, quota, kill switch) run BEFORE any streaming starts — they're pre-pipeline checks.
- If WebSocket disconnects mid-stream, the server should clean up gracefully (cancel the OpenAI stream if possible).
- The HTTP POST `/chat` endpoint is unchanged — still returns full response synchronously.
