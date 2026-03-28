/**
 * @process network-data-fix
 * @description Fix 4 network data quality issues + write methodology report.
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;

  ctx.log('info', 'Fix 4 network data issues + methodology report');

  // Task 1: Fix build_network_tables.py
  const fix = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Fix all 4 data quality issues in build_network_tables.py',
    description: `You are fixing 4 critical data quality issues in the network build script.

Working directory: ${projectRoot}

Read scripts/network/build_network_tables.py and fix these 4 issues:

## Issue 1: Orphan edges (3,816 edges referencing non-existent agents)
Root cause: Edges are created for agents that get excluded from network_agents (no geocode).
Fix: After building network_edges AND network_agents, DELETE edges where either endpoint is not in network_agents:
\`\`\`sql
DELETE FROM network_edges WHERE source_agent_norm NOT IN (SELECT agent_norm FROM network_agents)
   OR target_agent_norm NOT IN (SELECT agent_norm FROM network_agents);
\`\`\`
Add this cleanup step at the end of the main() function, after both tables are built.

## Issue 2: Duplicate persons (Hebrew/Latin name variants treated as separate nodes)
Root cause: build_network_agents creates one row per agent_norm, but the same person can have multiple agent_norms (e.g., "maimonides, moses" and "משה בן מימון").
Fix: In build_network_agents, GROUP agents by wikidata_id (from authority_enrichment) when available. For each wikidata_id, merge all agent_norms into one network_agents row:
- display_name: use the enrichment label (best quality)
- place_norm: use the most frequent across all norms
- birth_year/death_year: from person_info (same for all norms)
- connection_count: sum of edges for ALL norms sharing this wikidata_id
- record_count: sum across all norms
- Also update network_edges: normalize all agent_norms sharing a wikidata_id to a single canonical agent_norm (the one with the most records)
- Delete self-referencing edges that result from merging (source == target after normalization)

## Issue 3: Teacher/student edge directionality (~50% inverted)
Root cause: In _build_teacher_student_edges, when processing person_info["teachers"], the edge is created as (source=agent, target=teacher, relationship="student of") but the source/target semantics should be (source=teacher, target=student, relationship="teacher of").
Fix: When processing teachers list, create edge as (source=teacher_norm, target=source_norm, relationship="teacher of"). When processing students list, create edge as (source=source_norm, target=student_norm, relationship="teacher of"). This way source is always the teacher.

## Issue 4: connection_count should reflect actual edges after cleanup
Fix: Recompute connection_count AFTER all edge cleanup (orphan removal, deduplication, self-reference removal). Currently it's computed during build_network_agents which runs before cleanup.
Move the connection_count computation to a final UPDATE after all cleanup:
\`\`\`sql
UPDATE network_agents SET connection_count = (
    SELECT count(*) FROM network_edges
    WHERE source_agent_norm = network_agents.agent_norm
       OR target_agent_norm = network_agents.agent_norm
);
\`\`\`

After ALL fixes, rebuild:
poetry run python -m scripts.network.build_network_tables data/index/bibliographic.db data/normalization/place_geocodes.json

Verify:
python3 -c "
import sqlite3
c = sqlite3.connect('data/index/bibliographic.db')
edges = c.execute('SELECT count(*) FROM network_edges').fetchone()[0]
agents = c.execute('SELECT count(*) FROM network_agents').fetchone()[0]
orphans_src = c.execute('SELECT count(*) FROM network_edges WHERE source_agent_norm NOT IN (SELECT agent_norm FROM network_agents)').fetchone()[0]
orphans_tgt = c.execute('SELECT count(*) FROM network_edges WHERE target_agent_norm NOT IN (SELECT agent_norm FROM network_agents)').fetchone()[0]
self_refs = c.execute('SELECT count(*) FROM network_edges WHERE source_agent_norm = target_agent_norm').fetchone()[0]
zero_conn = c.execute('SELECT count(*) FROM network_agents WHERE connection_count = 0').fetchone()[0]
print(f'Edges: {edges}, Agents: {agents}')
print(f'Orphan edges: src={orphans_src}, tgt={orphans_tgt}')
print(f'Self-references: {self_refs}')
print(f'Zero-connection agents: {zero_conn}')
# Check dedup worked
dupes = c.execute('''SELECT ae.wikidata_id, count(DISTINCT na.agent_norm) FROM network_agents na
    JOIN agents a ON a.agent_norm = na.agent_norm
    JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
    WHERE ae.wikidata_id IS NOT NULL
    GROUP BY ae.wikidata_id HAVING count(DISTINCT na.agent_norm) > 1''').fetchall()
print(f'Duplicate persons (same wikidata_id, multiple network_agents): {len(dupes)}')
"

Expected: 0 orphan edges, 0 self-references, 0 duplicate persons.

Commit: git add scripts/network/build_network_tables.py && git commit -m "fix: 4 network data quality issues — orphans, dedup, directionality, counts"`,
    testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('data/index/bibliographic.db'); o=c.execute('SELECT count(*) FROM network_edges WHERE source_agent_norm NOT IN (SELECT agent_norm FROM network_agents)').fetchone()[0]; s=c.execute('SELECT count(*) FROM network_edges WHERE source_agent_norm = target_agent_norm').fetchone()[0]; print(f'orphans={o}, self_refs={s}'); assert o == 0 and s == 0"`,
  });

  // Task 2: Write methodology report on the FIXED system
  const report = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Write network methodology report',
    description: `Write a detailed methodology report about how the Scholarly Network Map works AFTER the fixes.

Read these files to understand the full pipeline:
1. scripts/network/build_network_tables.py — how edges and agents are built
2. app/api/network.py — how the API serves map data
3. frontend/src/components/network/MapView.tsx — how the map renders
4. frontend/src/components/network/ControlBar.tsx — how filters work
5. frontend/src/pages/Network.tsx — page structure
6. frontend/src/types/network.ts — connection type config

Also check the actual data:
python3 -c "
import sqlite3
c = sqlite3.connect('data/index/bibliographic.db')
print('=== Edge types ===')
for r in c.execute('SELECT connection_type, count(*), avg(confidence) FROM network_edges GROUP BY connection_type ORDER BY count(*) DESC').fetchall():
    print(f'  {r[0]}: {r[1]} (avg conf {r[2]:.2f})')
print(f'Total edges: {c.execute(\"SELECT count(*) FROM network_edges\").fetchone()[0]}')
print(f'Total agents: {c.execute(\"SELECT count(*) FROM network_agents\").fetchone()[0]}')
print(f'Agents with connections: {c.execute(\"SELECT count(*) FROM network_agents WHERE connection_count > 0\").fetchone()[0]}')
"

Write the report to: reports/network-methodology.md

The report MUST cover these sections (short, specific, concrete):

1. **Network Construction** — What is the process of building the network? What decisions are made, and in what order? What determines whether a connection is created or not?

2. **Connection Types** — What are the 6 types, how is each computed, what data source does each use, what confidence level, what does each actually mean?

3. **Agent Deduplication** — How are Hebrew/Latin variants merged? What is the canonical form? How are edges normalized?

4. **Roles** — How do agent roles factor into the network logic? Does a role affect connections or just appearance?

5. **Time Spans** — How is time handled? Does the network change over time, or is time just a visual attribute? What drives time-based behavior?

6. **Rendering Logic** — How does the network get placed on the map? What determines position, visibility, color, size? How does filtering work?

7. **Data Quality Measures** — What cleanup steps exist? Orphan removal, self-reference deletion, deduplication, confidence thresholds?

8. **Ambiguities and Limitations** — Where is the logic fragile? What could produce unexpected results? What assumptions are made?

Be specific — quote actual SQL queries, function names, line numbers. Report what ACTUALLY HAPPENS, not what should happen.

Commit: git add reports/network-methodology.md && git commit -m "docs: add network methodology report" && git push origin main`,
    testCommand: `cd ${projectRoot} && test -f reports/network-methodology.md && wc -l reports/network-methodology.md`,
  });

  ctx.log('info', 'Network data fix + methodology report complete');
  return { success: true };
}

const agentTask = defineTask('netfix-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior data engineer fixing network data quality and documenting methodology',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        args.description,
        `Verification: ${args.testCommand}`,
        'Return JSON: { taskName, status }',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
