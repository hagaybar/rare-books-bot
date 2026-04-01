# Enrichment Record Panel — Design Spec

**Date**: 2026-03-27
**Status**: Approved

---

## Overview

Make the blue "N records" badge on Entity Enrichment cards clickable. Clicking opens a slide-in side panel showing the agent's bibliographic records with navigation to Chat and Primo.

## User Flow

1. User browses Entity Enrichment page, sees "14 records" on Isaac Abrabanel's card
2. Clicks the badge
3. Side panel slides in from the right showing:
   - **Header**: "Isaac Abrabanel" · 1437–1508 · 14 records
   - **Record list** (scrollable): each record shows title, date, place, publisher, agent's role
   - **Footer**: "Ask in Chat" button + "View all in Primo" button
4. Clicking a record title opens it in Primo (external link)
5. "Ask in Chat" navigates to `/chat?q=books by Isaac Abrabanel`
6. "View all in Primo" opens Primo search for this agent
7. Clicking X or outside the panel closes it

## API

### `GET /metadata/enrichment/agent-records`

Returns records where this agent appears, with imprint details.

**Parameters** (query params, exactly one required):
- `wikidata_id` — e.g., `Q319902`. Preferred for merged entities (finds all agent_norms sharing this Wikidata ID).
- `agent_norm` — e.g., `abravanel, isaac`. Fallback for agents without Wikidata ID.

Returns 400 if neither or both are provided.

**No pagination** — max observed record_count is ~50. All records returned in one response.

**Response**:
```json
{
  "agent_norm": "abravanel, isaac",
  "display_name": "Isaac Abrabanel",
  "record_count": 14,
  "records": [
    {
      "mms_id": "990001234560204146",
      "title": "Perush ha-Torah",
      "date_raw": "[1579]",
      "date_start": 1579,
      "place_norm": "venice",
      "publisher_norm": "bragadin press, venice",
      "role": "author"
    }
  ]
}
```

**Field notes**:
- `mms_id`: From `records.mms_id` (external identifier, used for Primo URL construction)
- `role`: From `agents.role_raw` for the specific agent row that matched. If an agent has multiple roles on the same record, the first non-null role is used.

The query joins `agents` → `records` → `titles` → `imprints`, filtered by all agent_norms sharing the given `wikidata_id` (or a single `agent_norm` if no wikidata_id).

**Loading/error/empty states**:
- Loading: spinner in panel body while API call is in flight
- Error: "Could not load records" message with retry
- 0 records: badge should not be clickable (but this shouldn't happen — record_count > 0 by definition)

## Frontend

### New Component: `EnrichmentRecordPanel.tsx`

- Location: `frontend/src/components/enrichment/EnrichmentRecordPanel.tsx`
- Props: `{ agent: EnrichedAgent, onClose: () => void }`
- Layout: 300px wide, slides from right, full height, scrollable body

**Header** (sticky):
```
Isaac Abrabanel
1437–1508 · 14 records
[X close]
```

**Record list** (scrollable):
Each record as a compact row:
```
Perush ha-Torah                    [Primo →]
1579 · Venice · Bragadin Press · author
```

Title is a clickable link to Primo. Below it: date + place + publisher + role in muted text.

**Footer** (sticky):
```
[Ask in Chat →]  [View all in Primo →]
```

- "Ask in Chat": `<a href="/chat?q=books by {displayName}">`
- "View all in Primo": opens Primo author search URL

### Modified: `Enrichment.tsx`

- Add state: `selectedAgent: EnrichedAgent | null`
- Make the record count badge clickable: `onClick={() => setSelectedAgent(agent)}`
- Render `<EnrichmentRecordPanel>` when selectedAgent is set

## Files

| File | Action |
|------|--------|
| `app/api/metadata.py` | Add `GET /metadata/enrichment/agent-records` endpoint |
| `frontend/src/components/enrichment/EnrichmentRecordPanel.tsx` | New component |
| `frontend/src/pages/admin/Enrichment.tsx` | Add click handler + panel rendering |
| `frontend/src/api/metadata.ts` | Add `fetchAgentRecords()` function |
