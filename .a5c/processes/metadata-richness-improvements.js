/**
 * @process metadata-richness-improvements
 * @description Surface hidden metadata in chat pipeline, improve chat UX, and enhance network display.
 *   Phase 1: Extend RecordSummary/AgentSummary/GroundingData with confidence, publisher details,
 *            Hebrew subjects, agent images, auto-connections, and update narrator prompts.
 *   Phase 2: Chat UX — truncation feedback, granular progress, entity-aware follow-ups,
 *            re-narrate endpoint, session exploration.
 *   Phase 3: Network improvements + data enrichment.
 *
 * @inputs { projectRoot: string, planPath: string, dbPath: string }
 * @outputs { success: boolean, phasesCompleted: number, testsPassing: boolean }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill git-expert .claude/skills/git-expert/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    planPath = '/home/hagaybar/.claude/plans/squishy-percolating-biscuit.md',
    dbPath = 'data/index/bibliographic.db',
  } = inputs;

  ctx.log('info', 'Starting metadata richness improvements (3 phases)');

  // ============================================================================
  // PHASE 1: Surface Hidden Metadata in Chat Pipeline
  // ============================================================================

  ctx.log('info', '=== PHASE 1: Surface Hidden Metadata ===');

  // Task 1.1: Extend RecordSummary with confidence, title variants, expanded notes, Hebrew subjects
  const task1_1 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '1.1',
    taskName: 'Extend RecordSummary with confidence, titles, notes, Hebrew subjects',
    description: `Modify scripts/chat/plan_models.py and scripts/chat/executor.py to surface hidden record metadata.

MODEL CHANGES in scripts/chat/plan_models.py — add to RecordSummary class (after line 333):
  date_confidence: float | None = None
  place_confidence: float | None = None
  publisher_confidence: float | None = None
  title_variants: list[str] = Field(default_factory=list)
  notes_structured: dict[str, list[str]] = Field(default_factory=dict)
  subjects_he: list[str] = Field(default_factory=list)

EXECUTOR CHANGES in scripts/chat/executor.py _collect_grounding() method:
1. Imprints query: Add i.date_confidence, i.place_confidence, i.publisher_confidence to the existing SELECT. Populate on each RecordSummary.
2. Titles query: Add a second batch query for title_type IN ('uniform', 'variant'). Build title_variants list.
3. Notes query: Expand from tags (500, 520) to include (504, 505, 590). Group by tag into notes_structured dict. Keep existing notes list for backward compat.
4. Subjects query: Also fetch s.value_he. Populate subjects_he list on each RecordSummary.

TOKEN BUDGET GUARD: When len(all_mms) > 15, skip title_variants and notes_structured queries (set to empty defaults). This prevents token explosion on large result sets.

IMPORTANT: All new fields have defaults so existing code is not broken. Read the current _collect_grounding() implementation carefully before making changes.`,
    testCommand: `cd ${projectRoot} && python -m pytest tests/ -k "plan_models or executor" --tb=short -q 2>&1 | tail -30`,
  });

  // Task 1.2: Extend AgentSummary with image, authority URI, Hebrew aliases
  const task1_2 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '1.2',
    taskName: 'Extend AgentSummary with image URL, authority URI, Hebrew aliases',
    description: `Modify scripts/chat/plan_models.py and scripts/chat/executor.py to add agent enrichment data.

MODEL CHANGES in scripts/chat/plan_models.py — add to AgentSummary class (after line 213):
  image_url: str | None = None
  authority_uri: str | None = None
  hebrew_aliases: list[str] = Field(default_factory=list)

EXECUTOR CHANGES:
1. In _handle_enrich() (around line 934-1024): The query already joins authority_enrichment. Add ae.image_url to the existing query. Set image_url and authority_uri on AgentSummary.
2. For Hebrew aliases: After fetching alias_rows, query agent_aliases for script='hebrew' entries. Set hebrew_aliases.
3. In _collect_grounding() auto-enrichment section: Apply the same pattern when building AgentSummary objects outside explicit enrich steps.

Read the existing _handle_enrich() and _collect_grounding() agent-building code carefully before modifying.`,
    testCommand: `cd ${projectRoot} && python -m pytest tests/ -k "executor" --tb=short -q 2>&1 | tail -20`,
  });

  // Task 1.3: Add PublisherDetail to GroundingData
  const task1_3 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '1.3',
    taskName: 'Add PublisherDetail to GroundingData',
    description: `Add publisher authority data to the grounding so the narrator can describe publishers scholarly.

NEW MODEL in scripts/chat/plan_models.py (add before GroundingData class):
class PublisherDetail(BaseModel):
    """Publisher authority data for narrator consumption."""
    canonical_name: str
    type: str | None = None
    dates_active: str | None = None
    location: str | None = None
    wikidata_id: str | None = None
    cerl_id: str | None = None

Add to GroundingData class: publishers: list[PublisherDetail] = Field(default_factory=list)

EXECUTOR CHANGES in _collect_grounding():
After building records, collect distinct publisher_norm values from all grounded RecordSummary objects.
Batch-lookup against publisher_authorities via publisher_variants:
  SELECT pa.canonical_name, pa.type, pa.dates_active, pa.date_start, pa.date_end,
         pa.location, pa.wikidata_id, pa.cerl_id
  FROM publisher_authorities pa
  JOIN publisher_variants pv ON pv.authority_id = pa.id
  WHERE lower(pv.variant_form) IN (?)
Only include publishers where type IS NOT NULL AND type != 'unresearched'.
Build PublisherDetail objects and set grounding.publishers.`,
    testCommand: `cd ${projectRoot} && python -m pytest tests/ -k "plan_models or executor" --tb=short -q 2>&1 | tail -20`,
  });

  // Verify Phase 1 data layer
  const phase1DataVerify = await ctx.task(verifyTask, {
    projectRoot,
    phase: 'phase1-data',
    description: 'Verify all new fields are populated in grounding data',
    testCommand: `cd ${projectRoot} && python -m pytest tests/ -k "plan_models or executor" --tb=short -q 2>&1 | tail -30`,
  });

  // Task 1.4: Auto-trigger connection discovery
  const task1_4 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '1.4',
    taskName: 'Auto-trigger connection discovery for top agents',
    description: `Add automatic agent connection discovery to the executor so the narrator can weave relationships into responses.

MODEL CHANGE in scripts/chat/plan_models.py:
Add to GroundingData: connections: list[dict] = Field(default_factory=list)

EXECUTOR CHANGE in execute_plan() (scripts/chat/executor.py):
After _collect_grounding() returns, check if:
  - grounding has 2-10 agent summaries
  - no find_connections step was already in the plan
If both conditions are true, call cross_reference.find_connections() for the top agents (by record_count).
Serialize the resulting ConnectionGraph.connections as list[dict] and set grounding.connections.

Performance guard: skip if >10 agents or if find_connections was already in the plan.

Read scripts/chat/cross_reference.py find_connections() to understand the function signature and return type.
Read scripts/chat/executor.py _handle_find_connections() to see how it's called in the explicit step case.`,
    testCommand: `cd ${projectRoot} && python -m pytest tests/ -k "executor" --tb=short -q 2>&1 | tail -20`,
  });

  // Task 1.5: Update narrator prompts
  const task1_5 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '1.5',
    taskName: 'Update narrator prompts to use new grounding data',
    description: `Modify scripts/chat/narrator.py to weave new metadata into the narrator's prompt.

CHANGES to build_lean_narrator_prompt() AND _build_narrator_prompt():

1. CONFIDENCE ANNOTATIONS: When rendering a record, if any confidence score (date_confidence, place_confidence, publisher_confidence) is below 0.7, append "(date uncertain)" or "(place uncertain)" or "(publisher uncertain)" next to the respective field.

2. PUBLISHER CONTEXT SECTION: After the AGENT PROFILES section, add PUBLISHER CONTEXT if result.grounding.publishers is non-empty:
   PUBLISHER CONTEXT:
     - Bragadin (Venice, printing_house, active 1550-1610)

3. HEBREW SUBJECTS: In subject rendering, when rec.subjects_he is non-empty, show bilingual: "Jewish law / mishpat ivri" (use the actual Hebrew text from subjects_he)

4. CONNECTION HINTS SECTION: If result.grounding.connections is non-empty, add:
   RELATIONSHIP HINTS (discovered automatically):
     - AgentA teacher_of AgentB (source: Wikidata)

5. TITLE VARIANTS: When rec.title_variants is non-empty, show "Also known as: [titles]"

6. AGENT IMAGES: In agent profile rendering, include "Image: [url]" when image_url is present.

ADD TO NARRATOR_SYSTEM_PROMPT (the evidence rules section):
  8. When confidence scores indicate uncertainty (below 0.7) for dates, places, or publishers, qualify your statements (e.g., "attributed to", "possibly printed in", "circa").
  9. When Hebrew subject equivalents are provided, include them alongside English terms.
  10. When publisher context is provided, weave type/dates/location into publication descriptions.
  11. When agent relationships are discovered, mention them to enrich the scholarly narrative.

IMPORTANT: Read the existing build_lean_narrator_prompt() carefully — it has token-saving logic. New sections should be compact (2-5 lines each). Do NOT add verbose sections.`,
    testCommand: `cd ${projectRoot} && python -m pytest tests/ -k "narrator" --tb=short -q 2>&1 | tail -20`,
  });

  // Task 1.6: Update frontend types
  const task1_6 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '1.6',
    taskName: 'Update frontend TypeScript types for new grounding data',
    description: `Update frontend/src/types/chat.ts to add the new fields from the backend models.

Read the current frontend/src/types/chat.ts to understand the existing interface shapes.

Add to the record/grounding record interface (matching RecordSummary backend):
  date_confidence?: number | null;
  place_confidence?: number | null;
  publisher_confidence?: number | null;
  title_variants?: string[];
  subjects_he?: string[];
  notes_structured?: Record<string, string[]>;

Add to the agent/grounding agent interface (matching AgentSummary backend):
  image_url?: string | null;
  authority_uri?: string | null;
  hebrew_aliases?: string[];

Add new PublisherDetail interface:
  interface PublisherDetail {
    canonical_name: string;
    type?: string | null;
    dates_active?: string | null;
    location?: string | null;
    wikidata_id?: string | null;
    cerl_id?: string | null;
  }

Add to GroundingData interface:
  publishers?: PublisherDetail[];
  connections?: Record<string, unknown>[];

All fields are optional — backward compatible. Also check frontend/src/components/chat/ for any GroundingSources or similar component that displays grounding data and could show the new fields.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -20`,
  });

  // Phase 1 quality gate
  const phase1Gate = await ctx.task(verifyTask, {
    projectRoot,
    phase: 'phase1-complete',
    description: 'Run all tests and verify Phase 1 changes are complete',
    testCommand: `cd ${projectRoot} && python -m pytest tests/ --tb=short -q 2>&1 | tail -30 && cd frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  // Phase 1 commit
  const phase1Commit = await ctx.task(commitTask, {
    projectRoot,
    message: 'feat: surface hidden metadata in chat pipeline (Phase 1)',
    description: 'Commit Phase 1 — extended RecordSummary, AgentSummary, GroundingData with confidence, publisher details, Hebrew subjects, agent images, auto-connections, and narrator prompt updates',
  });

  ctx.log('info', `Phase 1 complete: ${JSON.stringify(phase1Commit)}`);

  // ============================================================================
  // PHASE 2: Chat Pipeline UX Improvements
  // ============================================================================

  ctx.log('info', '=== PHASE 2: Chat Pipeline UX ===');

  // Task 2.1: Transparent truncation feedback
  const task2_1 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '2.1',
    taskName: 'Add transparent truncation feedback',
    description: `Make result truncation visible to users.

1. In scripts/chat/narrator.py build_lean_narrator_prompt(): Change the truncation NOTE to include counts:
   "NOTE: Showing {len(records)} of {result.total_record_count} total matching records. The response should acknowledge this truncation to the user."
   Apply same change in _build_narrator_prompt().

2. In app/api/main.py WebSocket handler: After execution, if execution_result.truncated is True, send thinking message:
   "Found {records_found} matching records (showing top {grounding_records_count} of {execution_result.total_record_count} total)"

3. Add total_record_count to ChatResponse.metadata dict in the response mapping.

Read the existing truncation handling in narrator.py and the WebSocket handler in main.py before making changes.`,
    testCommand: `cd ${projectRoot} && python -m pytest tests/ -k "narrator" --tb=short -q 2>&1 | tail -20`,
  });

  // Task 2.2: Granular pipeline progress
  const task2_2 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '2.2',
    taskName: 'Add granular pipeline progress with stage field',
    description: `Improve progress messages in the WebSocket handler (app/api/main.py).

1. Add "stage" field to thinking messages: "interpret", "execute", "narrate".
   Change existing thinking sends to include stage:
     {"type": "thinking", "text": "Interpreting your query...", "stage": "interpret"}
     {"type": "thinking", "text": "Searching for...", "stage": "execute"}
     {"type": "thinking", "text": "Found N matching records", "stage": "execute"}

2. Before narration starts (before stream_start), send:
     {"type": "thinking", "text": "Composing scholarly response...", "stage": "narrate"}

3. Update frontend ThinkingBlock component (find it in frontend/src/components/chat/) to recognize the stage field. When present, show a compact 3-step indicator: interpret > execute > narrate with the current stage highlighted (e.g., bold or different color).

Read the existing WebSocket handler in main.py (around lines 1010-1070) and the ThinkingBlock component before making changes.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  // Task 2.3: Entity-aware follow-up suggestions
  const task2_3 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '2.3',
    taskName: 'Add entity-aware follow-up suggestions to narrator',
    description: `Help the narrator generate better follow-up suggestions by providing deterministic hint data.

In scripts/chat/narrator.py build_lean_narrator_prompt() and _build_narrator_prompt():

Add a FOLLOW-UP HINTS section before the final instruction, containing:
  - Top agents in results: names + record counts (top 3)
  - Agents with connections: names where grounding.connections mentions them
  - Subjects found: top 5 distinct subjects from grounded records

Example:
  FOLLOW-UP HINT DATA:
  - Top agents: Karo (5 records), Bragadin (3 records), Luria (2 records)
  - Agents with connections available: Karo, Luria
  - Top subjects: Jewish law, Halakha, Liturgy, Kabbalah, Talmud

Modify the system prompt instruction about follow-ups to say:
"Suggest follow-ups that leverage available data — e.g., exploring an agent's connections, comparing publication places, or diving deeper into a subject."

Keep the hints section compact (5 lines max).`,
    testCommand: `cd ${projectRoot} && python -m pytest tests/ -k "narrator" --tb=short -q 2>&1 | tail -20`,
  });

  // Phase 2 quality gate
  const phase2Gate = await ctx.task(verifyTask, {
    projectRoot,
    phase: 'phase2-complete',
    description: 'Run all tests and verify Phase 2 changes',
    testCommand: `cd ${projectRoot} && python -m pytest tests/ --tb=short -q 2>&1 | tail -30 && cd frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  // Phase 2 commit
  const phase2Commit = await ctx.task(commitTask, {
    projectRoot,
    message: 'feat: chat UX improvements — truncation feedback, progress stages, entity follow-ups',
    description: 'Commit Phase 2 — transparent truncation, granular pipeline progress with stage indicator, entity-aware follow-up hints',
  });

  ctx.log('info', `Phase 2 complete: ${JSON.stringify(phase2Commit)}`);

  // ============================================================================
  // PHASE 3: Network Improvements + Data Enrichment
  // ============================================================================

  ctx.log('info', '=== PHASE 3: Network + Enrichment ===');

  // Task 3.1: Network agent search
  const task3_1 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '3.1',
    taskName: 'Add agent search to network map',
    description: `Add a search endpoint and search UI to the network map page.

BACKEND — app/api/network.py:
Add a new GET /network/search endpoint with query parameter q (string) and limit (int, default 10):
  SELECT agent_norm, display_name, lat, lon, connection_count FROM network_agents
  WHERE display_name LIKE '%' || ? || '%' OR agent_norm LIKE '%' || ? || '%'
  ORDER BY connection_count DESC LIMIT ?
Return list of matching agents with their coordinates.

Register the endpoint in the network router.

FRONTEND — frontend/src/components/network/ControlBar.tsx:
Add a search input at the top of the control bar. On input change (debounced 300ms), call the search endpoint.
Show results in a dropdown below the input. When a result is clicked:
1. Set it as the selected agent
2. Zoom the map to its lat/lon coordinates
3. Open the AgentPanel for that agent

Also add the API call function to frontend/src/api/network.ts.

Read the existing ControlBar.tsx and network API patterns before implementing.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  // Task 3.2: Network edge type legend
  const task3_2 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '3.2',
    taskName: 'Add edge type legend to network map',
    description: `Extend the network Legend component to show edge (connection) type colors alongside node colors.

In frontend/src/components/network/Legend.tsx:
The CONNECTION_TYPE_CONFIG in frontend/src/types/network.ts defines label, color, and tier for each connection type.
Add an "Edge Types" section below the existing node color legend. For each active connection type, show a small colored line/bar + the label.

Read Legend.tsx and types/network.ts to understand the existing structure.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  // Task 3.3: Agent panel "See all connections"
  const task3_3 = await ctx.task(implementTask, {
    projectRoot, planPath,
    taskId: '3.3',
    taskName: 'Add "See all connections" to AgentPanel',
    description: `In frontend/src/components/network/AgentPanel.tsx, the connections list is truncated to 20.

Add a "Show all N connections" button/toggle when the connection count exceeds 20. When clicked, expand the list to show all connections in a scrollable container (max-height with overflow-y: auto).

Read the existing AgentPanel.tsx to understand how connections are currently rendered and truncated.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  // Phase 3 quality gate
  const phase3Gate = await ctx.task(verifyTask, {
    projectRoot,
    phase: 'phase3-complete',
    description: 'Run all tests and type checks for Phase 3',
    testCommand: `cd ${projectRoot} && python -m pytest tests/ --tb=short -q 2>&1 | tail -30 && cd frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  // Phase 3 commit
  const phase3Commit = await ctx.task(commitTask, {
    projectRoot,
    message: 'feat: network map improvements — agent search, edge legend, expanded connections',
    description: 'Commit Phase 3 — network agent search, edge type legend, expanded agent panel connections',
  });

  ctx.log('info', `Phase 3 complete: ${JSON.stringify(phase3Commit)}`);

  // ============================================================================
  // FINAL VERIFICATION
  // ============================================================================

  ctx.log('info', '=== Final Verification ===');

  const finalVerify = await ctx.task(verifyTask, {
    projectRoot,
    phase: 'final',
    description: 'Final verification — all tests pass, type checks clean, no regressions',
    testCommand: `cd ${projectRoot} && python -m pytest tests/ --tb=short -q 2>&1 | tail -40 && echo "---" && cd frontend && npx tsc --noEmit 2>&1 | tail -10 && echo "---" && cd ${projectRoot} && ruff check . 2>&1 | tail -20`,
  });

  return {
    success: true,
    phasesCompleted: 3,
    phase1: phase1Commit,
    phase2: phase2Commit,
    phase3: phase3Commit,
    finalVerification: finalVerify,
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

const implementTask = defineTask('implement', (args, taskCtx) => ({
  kind: 'agent',
  title: `Implement ${args.taskId}: ${args.taskName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python/TypeScript developer implementing feature improvements for a rare books bibliographic discovery system',
      task: args.description,
      context: {
        projectRoot: args.projectRoot,
        planPath: args.planPath,
        taskId: args.taskId,
      },
      instructions: [
        `Read the plan at ${args.planPath} for full context`,
        'Read the target files BEFORE making changes to understand the existing code',
        'Make minimal, focused changes — do not refactor surrounding code',
        'All new model fields MUST have defaults for backward compatibility',
        'After making changes, run the test command to verify',
        'If tests fail, fix the issues and re-run until passing',
        `Test command: ${args.testCommand}`,
        'Return a summary of changes made (files modified, lines added/removed)',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      properties: {
        success: { type: 'boolean' },
        filesModified: { type: 'array', items: { type: 'string' } },
        summary: { type: 'string' },
        testOutput: { type: 'string' },
      },
      required: ['success', 'summary'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const verifyTask = defineTask('verify', (args, taskCtx) => ({
  kind: 'shell',
  title: `Verify ${args.phase}`,
  shell: {
    command: args.testCommand,
    cwd: args.projectRoot,
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const commitTask = defineTask('commit', (args, taskCtx) => ({
  kind: 'agent',
  title: `Commit: ${args.message}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Git workflow assistant',
      task: `Create a git commit for the recent changes. Message: "${args.message}". Description: ${args.description}`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Run git status to see changed files',
        'Stage only the relevant modified files (not .a5c/ or unrelated files)',
        'Create the commit with the provided message using HEREDOC format',
        'Include Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>',
        'Do NOT push to remote — just commit locally',
        'Return the commit hash and list of files committed',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      properties: {
        success: { type: 'boolean' },
        commitHash: { type: 'string' },
        filesCommitted: { type: 'array', items: { type: 'string' } },
      },
      required: ['success'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
