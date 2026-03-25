/**
 * @process narrative-agent-prototype
 * @description Build a narrative agent that enriches chatbot responses with biographical
 * context from Wikidata-enriched agent data. Limited to agents (authors, printers, etc.).
 * @inputs { projectRoot: string }
 * @outputs { success: boolean }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  const startTime = ctx.now();

  ctx.log('info', 'Building Narrative Agent Prototype');

  // Phase 1: Build the narrative agent backend module
  const narrativeAgent = await ctx.task(buildNarrativeAgentTask, { projectRoot });

  // Phase 2: Integrate into the chat flow
  const integration = await ctx.task(integrateChatFlowTask, { projectRoot, narrativeAgent });

  // Phase 3: Verify with real queries
  const verification = await ctx.task(verifyNarrativeTask, { projectRoot });

  return {
    success: true,
    duration: ctx.now() - startTime,
    metadata: { processId: 'narrative-agent-prototype' }
  };
}

export const buildNarrativeAgentTask = defineTask('build-narrative-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Build narrative agent backend module',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer building a narrative enrichment agent',
      task: 'Create a narrative agent module that looks up Wikidata enrichment data for agents in query results and constructs contextual biographical narrative.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read these files first to understand the existing system:',
        '- /home/hagaybar/projects/rare-books-bot/app/api/main.py (lines 544-615, the chat response construction)',
        '- /home/hagaybar/projects/rare-books-bot/scripts/schemas/candidate_set.py (Candidate model)',
        '- /home/hagaybar/projects/rare-books-bot/scripts/chat/formatter.py (existing formatting)',
        '- /home/hagaybar/projects/rare-books-bot/scripts/chat/models.py (ChatResponse model)',
        '',
        'Create: /home/hagaybar/projects/rare-books-bot/scripts/chat/narrative_agent.py',
        '',
        'The narrative agent should:',
        '',
        '1. DETECT: Given a CandidateSet, extract all unique agent names from candidates',
        '   - Each Candidate has an "author" field (primary agent) and record_id',
        '   - Also look up ALL agents for those record_ids from the agents table in bibliographic.db',
        '   - This gives us authors, printers, translators, editors, etc.',
        '',
        '2. LOOKUP: For each agent, check authority_enrichment table for enrichment data',
        '   - Join agents table → authority_enrichment on authority_uri',
        '   - Get: label, description, person_info (JSON with birth/death/occupations/nationality)',
        '   - Get: wikidata_id, viaf_id, wikipedia_url',
        '',
        '3. CONSTRUCT NARRATIVE: Build a contextual paragraph that:',
        '   - Highlights the most notable agents in the result set (by record_count and data richness)',
        '   - Mentions birth/death years, occupations, nationality when available',
        '   - Notes connections between agents if they appear in the same records',
        '   - Cites sources: "(Wikidata Q12345)" or "(VIAF 12345)"',
        '   - Is concise: 2-4 sentences for a result set, not a wall of text',
        '   - Adapts to context: for a single-record result, give more detail about that author;',
        '     for a multi-record set, summarize the key figures',
        '',
        '4. KNOW WHEN TO STAY SILENT: Return None/empty when:',
        '   - No enrichment data exists for any agent in the results',
        '   - The query is about dates/places/subjects, not people',
        '   - The result set is too large (>100) for meaningful agent summary',
        '   - The enrichment data is too thin (just IDs, no bio)',
        '',
        'The main function signature should be:',
        '```python',
        'def generate_agent_narrative(',
        '    candidate_set: CandidateSet,',
        '    db_path: Path,',
        '    max_agents: int = 5,',
        ') -> Optional[str]:',
        '    """Generate biographical narrative for agents in query results.',
        '    ',
        '    Returns a markdown string with agent context, or None if no meaningful',
        '    narrative can be constructed.',
        '    """',
        '```',
        '',
        'Also add a helper:',
        '```python',
        'def get_agent_enrichment_for_records(',
        '    record_ids: list[str],',
        '    db_path: Path,',
        ') -> list[dict]:',
        '    """Fetch enrichment data for all agents in the given records."""',
        '```',
        '',
        'IMPORTANT DESIGN RULES:',
        '- Do NOT use an LLM to generate narrative — use deterministic templates',
        '- The narrative must be factual (from enrichment data only), never invented',
        '- Citations must be included for every biographical claim',
        '- The module must work WITHOUT any API key — pure database lookups + templates',
        '- Keep it under 200 lines',
        '- Write unit-testable pure functions',
        '',
        'After creating the module, write a quick test:',
        '```python',
        'poetry run python -c "',
        'from scripts.chat.narrative_agent import generate_agent_narrative',
        'from scripts.query.service import QueryService',
        'from pathlib import Path',
        'qs = QueryService(Path(\"data/index/bibliographic.db\"))',
        'result = qs.execute(\"books by Maimonides\")',
        'narrative = generate_agent_narrative(result.candidate_set, Path(\"data/index/bibliographic.db\"))',
        'print(narrative)',
        '"',
        '```',
        '',
        'Return JSON with: { moduleCreated, lineCount, testOutput }'
      ],
      outputFormat: 'JSON with moduleCreated, lineCount, testOutput'
    },
    outputSchema: {
      type: 'object',
      required: ['moduleCreated'],
      properties: {
        moduleCreated: { type: 'string' },
        lineCount: { type: 'number' },
        testOutput: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['backend', 'narrative', 'agent']
}));

export const integrateChatFlowTask = defineTask('integrate-chat-flow', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Integrate narrative agent into chat flow',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python backend developer integrating a new feature into the chat API',
      task: 'Integrate the narrative agent into the POST /chat response flow so biographical context is automatically included when relevant.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read the narrative agent module: /home/hagaybar/projects/rare-books-bot/scripts/chat/narrative_agent.py',
        'Read the chat endpoint: /home/hagaybar/projects/rare-books-bot/app/api/main.py (focus on handle_query_definition_phase)',
        '',
        'Integration point: After the CandidateSet is built (line ~544) and before the ChatResponse is constructed (line ~605):',
        '',
        '1. Call generate_agent_narrative(candidate_set, db_path) to get narrative text',
        '2. If narrative is not None:',
        '   - Prepend it to the response_message AFTER the user_explanation',
        '   - Add it to response_metadata["agent_narrative"] for the frontend to display separately if desired',
        '3. If narrative is None: do nothing (existing behavior preserved)',
        '',
        'The integration should be:',
        '- A single function call, not a refactor',
        '- Safe: wrapped in try/except so narrative failures never break the chat response',
        '- Logged: log when narrative is generated and when it is skipped',
        '- Non-blocking: the narrative lookup should be fast (SQLite query, not API call)',
        '',
        'Also add agent_narrative to the frontend Chat types:',
        '- In frontend/src/types/chat.ts, the ChatResponse.metadata is Record<string, any> — no type change needed',
        '- In frontend/src/components/chat/MessageBubble.tsx, if metadata.agent_narrative exists,',
        '  render it as a collapsible "About the people" section with a person icon,',
        '  styled with a subtle blue-gray background, below the main message text',
        '  Use react-markdown to render the narrative (it may contain bold text and citations)',
        '',
        'After integration:',
        '- cd /home/hagaybar/projects/rare-books-bot && poetry run python -m pytest tests/app/test_api.py -x -q 2>&1 | tail -10',
        '- cd /home/hagaybar/projects/rare-books-bot/frontend && npm run build 2>&1 | tail -5',
        '',
        'Return JSON with: { backendChanged, frontendChanged, testsPass, buildStatus }'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['testsPass', 'buildStatus'],
      properties: {
        backendChanged: { type: 'array' },
        frontendChanged: { type: 'array' },
        testsPass: { type: 'boolean' },
        buildStatus: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['integration', 'chat', 'narrative']
}));

export const verifyNarrativeTask = defineTask('verify-narrative', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Verify narrative agent with real queries',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer testing the narrative agent with real queries',
      task: 'Run real queries through the chat pipeline and verify the narrative agent produces meaningful, accurate output.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Test the narrative agent by running queries that should trigger narrative:',
        '',
        '1. "books by Maimonides" — should produce narrative about Maimonides',
        '2. "books by Josephus" — should produce narrative about Josephus (Roman-Jewish historian)',
        '3. "Hebrew books printed in Venice" — should produce narrative about printers (if enriched)',
        '',
        'Also test queries that should NOT trigger narrative:',
        '4. "books from the 16th century" — date query, no specific agent focus',
        '5. "books" — too broad, should be silent',
        '',
        'For each test, run via the CLI or Python directly:',
        '```bash',
        'cd /home/hagaybar/projects/rare-books-bot',
        'poetry run python -c "',
        'from scripts.chat.narrative_agent import generate_agent_narrative',
        'from scripts.query.service import QueryService',
        'from pathlib import Path',
        'qs = QueryService(Path(\"data/index/bibliographic.db\"))',
        'result = qs.execute(\"<QUERY>\")',
        'narrative = generate_agent_narrative(result.candidate_set, Path(\"data/index/bibliographic.db\"))',
        'print(f\"Query: <QUERY>\")',
        'print(f\"Results: {len(result.candidate_set.candidates)}\")',
        'print(f\"Narrative: {narrative}\")',
        'print()',
        '"',
        '```',
        '',
        'Document results for all 5 queries.',
        'If any narrative is incorrect or poorly formatted, note the issue.',
        '',
        'Return JSON with: { tests: [{query, resultCount, narrativeGenerated, narrativeText, issues}], overallVerdict }'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['tests', 'overallVerdict'],
      properties: {
        tests: { type: 'array' },
        overallVerdict: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['verification', 'testing', 'narrative']
}));
