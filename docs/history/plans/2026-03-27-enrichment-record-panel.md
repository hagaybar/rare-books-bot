# Enrichment Record Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the "N records" badge on Entity Enrichment cards clickable, opening a slide-in panel with the agent's bibliographic records and links to Chat/Primo.

**Architecture:** New API endpoint returns records for an agent (by wikidata_id or agent_norm). New React component renders a slide-in panel. Enrichment page gets click handler + panel state.

**Tech Stack:** Python/FastAPI, React 19, TypeScript, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-27-enrichment-record-panel-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app/api/metadata.py` | Modify | Add `GET /metadata/enrichment/agent-records` endpoint |
| `frontend/src/api/metadata.ts` | Modify | Add `fetchAgentRecords()` function |
| `frontend/src/components/enrichment/EnrichmentRecordPanel.tsx` | Create | Side panel component |
| `frontend/src/pages/admin/Enrichment.tsx` | Modify | Click handler + panel rendering |

---

### Task 1: API Endpoint

**Files:**
- Modify: `app/api/metadata.py`

- [ ] **Step 1: Add the endpoint**

Add after the existing `get_enriched_agents` endpoint (~line 2003) in `app/api/metadata.py`:

```python
@router.get("/enrichment/agent-records", summary="Records for an enriched agent")
async def get_agent_records(
    wikidata_id: str = Query("", description="Wikidata ID (e.g., Q319902)"),
    agent_norm: str = Query("", description="Agent norm (fallback if no wikidata_id)"),
):
    """Get bibliographic records where this agent appears."""
    if not wikidata_id and not agent_norm:
        raise HTTPException(400, "Provide either wikidata_id or agent_norm")
    if wikidata_id and agent_norm:
        raise HTTPException(400, "Provide only one of wikidata_id or agent_norm")

    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Find all agent_norms for this entity
        if wikidata_id:
            norms = [r[0] for r in conn.execute(
                """SELECT DISTINCT a.agent_norm FROM agents a
                   JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
                   WHERE ae.wikidata_id = ?""",
                (wikidata_id,),
            ).fetchall()]
            # Get display name from enrichment
            label_row = conn.execute(
                "SELECT label FROM authority_enrichment WHERE wikidata_id = ? LIMIT 1",
                (wikidata_id,),
            ).fetchone()
            display_name = label_row["label"] if label_row else (norms[0] if norms else "Unknown")
        else:
            norms = [agent_norm]
            label_row = conn.execute(
                """SELECT ae.label FROM authority_enrichment ae
                   JOIN agents a ON a.authority_uri = ae.authority_uri
                   WHERE a.agent_norm = ? LIMIT 1""",
                (agent_norm,),
            ).fetchone()
            display_name = label_row["label"] if label_row else agent_norm

        if not norms:
            raise HTTPException(404, f"Agent not found: {wikidata_id or agent_norm}")

        placeholders = ",".join("?" for _ in norms)
        rows = conn.execute(
            f"""SELECT DISTINCT
                    r.mms_id,
                    t.value as title,
                    i.date_raw,
                    i.date_start,
                    i.place_norm,
                    i.publisher_norm,
                    a.role_raw as role
                FROM agents a
                JOIN records r ON a.record_id = r.id
                LEFT JOIN titles t ON t.record_id = r.id AND t.title_type = 'main'
                LEFT JOIN imprints i ON i.record_id = r.id
                WHERE a.agent_norm IN ({placeholders})
                ORDER BY i.date_start ASC NULLS LAST""",
            norms,
        ).fetchall()

        from scripts.utils.primo import generate_primo_url

        records = []
        seen_mms = set()
        for row in rows:
            mms = row["mms_id"]
            if mms in seen_mms:
                continue
            seen_mms.add(mms)
            records.append({
                "mms_id": mms,
                "title": row["title"],
                "date_raw": row["date_raw"],
                "date_start": row["date_start"],
                "place_norm": row["place_norm"],
                "publisher_norm": row["publisher_norm"],
                "role": row["role"],
                "primo_url": generate_primo_url(mms) if mms else None,
            })

        return {
            "display_name": display_name,
            "record_count": len(records),
            "records": records,
        }
    finally:
        conn.close()
```

- [ ] **Step 2: Test the endpoint**

```bash
curl -s 'http://localhost:8000/metadata/enrichment/agent-records?wikidata_id=Q319902' | python3 -m json.tool | head -30
```

Expected: JSON with `display_name: "Isaac Abrabanel"`, `record_count: 14`, and `records` array with mms_id, title, date, place, publisher, role, primo_url.

- [ ] **Step 3: Commit**

```bash
git add app/api/metadata.py
git commit -m "feat: add agent-records endpoint for enrichment record panel"
```

---

### Task 2: Frontend API Client + Panel Component

**Files:**
- Modify: `frontend/src/api/metadata.ts`
- Create: `frontend/src/components/enrichment/EnrichmentRecordPanel.tsx`

- [ ] **Step 1: Add API client function**

In `frontend/src/api/metadata.ts`, add:

```typescript
export interface AgentRecord {
  mms_id: string;
  title: string | null;
  date_raw: string | null;
  date_start: number | null;
  place_norm: string | null;
  publisher_norm: string | null;
  role: string | null;
  primo_url: string | null;
}

export interface AgentRecordsResponse {
  display_name: string;
  record_count: number;
  records: AgentRecord[];
}

export async function fetchAgentRecords(
  wikidataId?: string,
  agentNorm?: string
): Promise<AgentRecordsResponse> {
  const params = new URLSearchParams();
  if (wikidataId) params.set('wikidata_id', wikidataId);
  else if (agentNorm) params.set('agent_norm', agentNorm);
  const res = await fetch(`${BASE}/enrichment/agent-records?${params}`);
  return handleResponse<AgentRecordsResponse>(res);
}
```

- [ ] **Step 2: Create the panel component**

Create `frontend/src/components/enrichment/EnrichmentRecordPanel.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { fetchAgentRecords } from '../../api/metadata';

interface Props {
  wikidataId: string | null;
  agentNorm: string;
  displayName: string;
  lifespan: string;
  onClose: () => void;
}

export default function EnrichmentRecordPanel({
  wikidataId,
  agentNorm,
  displayName,
  lifespan,
  onClose,
}: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['agent-records', wikidataId || agentNorm],
    queryFn: () => fetchAgentRecords(wikidataId || undefined, wikidataId ? undefined : agentNorm),
  });

  return (
    <div className="w-96 bg-white border-l shadow-lg flex flex-col h-full flex-shrink-0">
      {/* Header */}
      <div className="p-4 border-b flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">{displayName}</h2>
          <p className="text-sm text-gray-500">
            {lifespan && <span>{lifespan} &middot; </span>}
            {data ? `${data.record_count} records` : '...'}
          </p>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">
          &times;
        </button>
      </div>

      {/* Records list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {isLoading && <p className="text-sm text-gray-400">Loading records...</p>}
        {error && <p className="text-sm text-red-500">Could not load records.</p>}
        {data?.records.map((rec) => (
          <div key={rec.mms_id} className="border-b pb-2">
            {rec.primo_url ? (
              <a
                href={rec.primo_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-blue-600 hover:text-blue-800 leading-tight block"
              >
                {rec.title || 'Untitled'} &rarr;
              </a>
            ) : (
              <p className="text-sm font-medium text-gray-900 leading-tight">
                {rec.title || 'Untitled'}
              </p>
            )}
            <p className="text-xs text-gray-400 mt-0.5">
              {[rec.date_raw, rec.place_norm, rec.publisher_norm, rec.role]
                .filter(Boolean)
                .join(' \u00B7 ')}
            </p>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-4 border-t flex gap-2">
        <a
          href={`/chat?q=${encodeURIComponent(`books by ${displayName}`)}`}
          className="flex-1 text-center text-sm bg-blue-50 text-blue-700 px-3 py-2 rounded hover:bg-blue-100"
        >
          Ask in Chat &rarr;
        </a>
        <a
          href={data?.records[0]?.primo_url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 text-center text-sm bg-gray-50 text-gray-700 px-3 py-2 rounded hover:bg-gray-100"
        >
          View in Primo &rarr;
        </a>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify compilation**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/metadata.ts frontend/src/components/enrichment/EnrichmentRecordPanel.tsx
git commit -m "feat: add EnrichmentRecordPanel component and API client"
```

---

### Task 3: Wire Panel into Enrichment Page

**Files:**
- Modify: `frontend/src/pages/admin/Enrichment.tsx`

- [ ] **Step 1: Add state and imports**

At the top of the component, add:
```typescript
import EnrichmentRecordPanel from '../../components/enrichment/EnrichmentRecordPanel';
```

Add state inside the component:
```typescript
const [selectedAgent, setSelectedAgent] = useState<EnrichedAgent | null>(null);
```

- [ ] **Step 2: Make the badge clickable**

Change the record count badge (around line 175) from:
```tsx
<span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full shrink-0">
  {agent.record_count} records
</span>
```

To:
```tsx
<button
  onClick={(e) => { e.stopPropagation(); setSelectedAgent(agent); }}
  className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full shrink-0 hover:bg-blue-100 cursor-pointer transition-colors"
>
  {agent.record_count} records
</button>
```

- [ ] **Step 3: Render the panel**

In the component's JSX, wrap the main content in a flex container and add the panel. Change the outermost layout div to include the panel:

```tsx
{selectedAgent && (
  <EnrichmentRecordPanel
    wikidataId={selectedAgent.wikidata_id}
    agentNorm={selectedAgent.agent_norm}
    displayName={selectedAgent.label || selectedAgent.agent_norm}
    lifespan={/* compute from person_info birth_year/death_year */}
    onClose={() => setSelectedAgent(null)}
  />
)}
```

The lifespan computation already exists in the component — extract it into a helper or compute inline from `selectedAgent.person_info.birth_year` and `death_year`.

- [ ] **Step 4: Verify compilation and build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/Enrichment.tsx
git commit -m "feat: wire record panel into Enrichment page with clickable badge"
```

---

### Task 4: Manual Test and Push

- [ ] **Step 1: Test in browser**

1. Navigate to Enrichment page
2. Click "14 records" on Isaac Abrabanel's card
3. Verify panel slides in with header, 14 records, Primo links, Chat/Primo buttons
4. Click a record title — opens in Primo
5. Click "Ask in Chat" — navigates to chat with pre-filled query
6. Click X — panel closes

- [ ] **Step 2: Push**

```bash
git push origin main
```
