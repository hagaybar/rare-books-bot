/**
 * @process interpreter-nano-eval
 * @description Evaluate gpt-4.1-nano as interpreter — 13 queries (8 in-scope, 2 out-of-scope, 3 ambiguous), compare to actual DB holdings, recommend
 * @inputs { model: string, dbPath: string }
 * @outputs { success: boolean, recommendations: string }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    model = 'gpt-4.1-nano',
    dbPath = 'data/index/bibliographic.db',
  } = inputs;

  ctx.log('info', `Starting interpreter-only evaluation with model: ${model}`);

  // ============================================================================
  // PHASE 1: CRAFT TEST QUERIES
  // ============================================================================

  ctx.log('info', 'Phase 1: Craft 13 test queries — 8 in-scope, 2 out-of-scope, 3 ambiguous');

  const craftQueries = await ctx.task(craftQueriesTask, { dbPath });

  // ============================================================================
  // PHASE 2: RUN INTERPRETER ON ALL 13 QUERIES
  // ============================================================================

  ctx.log('info', 'Phase 2: Run interpreter with gpt-4.1-nano on all 13 queries');

  const runInterpreter = await ctx.task(runInterpreterTask, { model, dbPath });

  // ============================================================================
  // PHASE 3: VERIFY RESULTS AGAINST ACTUAL DB HOLDINGS
  // ============================================================================

  ctx.log('info', 'Phase 3: Verify interpreter plans against actual DB holdings');

  const verifyResults = await ctx.task(verifyResultsTask, { dbPath });

  // ============================================================================
  // PHASE 4: ANALYSIS & RECOMMENDATIONS
  // ============================================================================

  ctx.log('info', 'Phase 4: Analyze results and produce recommendations');

  const analyzeAndRecommend = await ctx.task(analyzeTask, { model });

  ctx.log('info', 'Interpreter nano evaluation complete');
  return { success: true, model, queryCount: 13 };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

const craftQueriesTask = defineTask('craft-queries', (args) => ({
  kind: 'agent',
  title: 'Craft 13 test queries for interpreter evaluation',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Bibliographic data analyst creating evaluation queries for a rare books collection',
      task: `You need to craft exactly 13 test queries for evaluating the interpreter stage of a rare books query system. The queries will test how well gpt-4.1-nano can interpret natural language into structured query plans.

IMPORTANT: First, query the actual database at ${args.dbPath} to understand what data exists. Run these SQLite queries to find real data points:

\`\`\`
sqlite3 ${args.dbPath} "SELECT publisher_norm, COUNT(*) as cnt FROM imprints WHERE publisher_norm IS NOT NULL GROUP BY publisher_norm ORDER BY cnt DESC LIMIT 20;"
sqlite3 ${args.dbPath} "SELECT place_norm, COUNT(*) as cnt FROM imprints WHERE place_norm IS NOT NULL GROUP BY place_norm ORDER BY cnt DESC LIMIT 20;"
sqlite3 ${args.dbPath} "SELECT agent_norm, role_norm, COUNT(*) as cnt FROM agents WHERE agent_norm IS NOT NULL GROUP BY agent_norm, role_norm ORDER BY cnt DESC LIMIT 20;"
sqlite3 ${args.dbPath} "SELECT code, COUNT(*) as cnt FROM languages GROUP BY code ORDER BY cnt DESC LIMIT 15;"
sqlite3 ${args.dbPath} "SELECT value, COUNT(*) as cnt FROM subjects GROUP BY value ORDER BY cnt DESC LIMIT 20;"
sqlite3 ${args.dbPath} "SELECT MIN(date_start), MAX(date_start) FROM imprints WHERE date_start IS NOT NULL;"
sqlite3 ${args.dbPath} "SELECT COUNT(DISTINCT mms_id) FROM records;"
\`\`\`

Then create the queries file at data/eval/interpreter_nano_queries.json with exactly this structure:

CATEGORY 1 — IN-SCOPE (8 queries, grounded in actual collection data):
- q_is01: Simple retrieval — single publisher filter (use a real publisher from DB)
- q_is02: Simple retrieval — single place filter (use a real place)
- q_is03: Moderate retrieval — language + date range combination
- q_is04: Moderate retrieval — agent + role filter
- q_is05: Entity exploration — ask about a specific person in the collection
- q_is06: Analytical — aggregation/distribution query
- q_is07: Complex retrieval — 3+ filters combined (place + language + date range)
- q_is08: Curation — ask for a curated selection from a topic area

CATEGORY 2 — OUT-OF-SCOPE (2 queries, topics NOT in this collection):
- q_oos01: Ask about modern computer science books (not in a rare books collection)
- q_oos02: Ask about a specific author who definitely has zero records in the DB (verify with a query first)

CATEGORY 3 — AMBIGUOUS (3 queries, intentionally vague or multi-interpretable):
- q_amb01: Vague temporal reference (e.g., "old books" without specifying what "old" means)
- q_amb02: Ambiguous entity reference (a name that could mean multiple people or things)
- q_amb03: Unclear intent (could be retrieval, overview, or exploration)

Each query object must have: id, query, intent, difficulty, category (in_scope/out_of_scope/ambiguous), expected_filters, expected_record_count (approximate from DB), notes.

For in-scope queries, run the actual SQL to determine expected_record_count. For out-of-scope, expected_record_count should be 0.

Write the file to data/eval/interpreter_nano_queries.json.

Return a summary listing all 13 queries with their categories and expected counts.`,
      instructions: [
        'Query the actual database first to find real data points',
        'Craft queries that test different interpreter capabilities',
        'Ensure out-of-scope queries are clearly outside collection scope',
        'Make ambiguous queries genuinely multi-interpretable',
        'Write the queries to data/eval/interpreter_nano_queries.json',
        'Return summary only, not the full JSON'
      ],
      outputFormat: 'JSON summary with query list'
    }
  }
}));

const runInterpreterTask = defineTask('run-interpreter', (args) => ({
  kind: 'agent',
  title: 'Run gpt-4.1-nano interpreter on all 13 queries',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer running LLM evaluation',
      task: `Run the interpreter stage on all 13 queries from data/eval/interpreter_nano_queries.json using model "${args.model}".

IMPORTANT: This will make API calls to OpenAI. Proceed carefully.

Write and run a Python script that:
1. Reads the queries from data/eval/interpreter_nano_queries.json
2. For each query, calls the interpreter:
   \`\`\`python
   import asyncio, json, time
   from scripts.chat.interpreter import interpret

   queries = json.load(open('data/eval/interpreter_nano_queries.json'))
   results = []
   for q in queries:
       start = time.time()
       try:
           plan = asyncio.run(interpret(q['query'], model='${args.model}'))
           elapsed = time.time() - start
           results.append({
               'id': q['id'],
               'query': q['query'],
               'category': q['category'],
               'success': True,
               'latency_s': round(elapsed, 2),
               'intents': plan.intents,
               'confidence': plan.confidence,
               'clarification': plan.clarification,
               'reasoning': plan.reasoning,
               'num_steps': len(plan.execution_steps),
               'steps': [{'action': s.action, 'params': s.params.__dict__ if hasattr(s.params, '__dict__') else str(s.params)} for s in plan.execution_steps]
           })
       except Exception as e:
           elapsed = time.time() - start
           results.append({
               'id': q['id'],
               'query': q['query'],
               'category': q['category'],
               'success': False,
               'latency_s': round(elapsed, 2),
               'error': str(e)
           })
       print(f"  {q['id']}: {'OK' if results[-1]['success'] else 'FAIL'} ({results[-1]['latency_s']}s)")

   with open('data/eval/interpreter_nano_results.json', 'w') as f:
       json.dump(results, f, indent=2, default=str)
   \`\`\`
3. Save results to data/eval/interpreter_nano_results.json

CRITICAL: The interpret() function is async, so use asyncio.run() for each call. Between calls, give a small delay to avoid rate limiting.

Run the script and return a summary with: total queries, successes, failures, average latency, and any errors encountered.`,
      instructions: [
        'Read the queries file first',
        'Run interpreter on each query with the specified model',
        'Save complete results including execution plans',
        'Report summary statistics'
      ],
      outputFormat: 'JSON summary with statistics'
    }
  }
}));

const verifyResultsTask = defineTask('verify-results', (args) => ({
  kind: 'agent',
  title: 'Verify interpreter plans against actual DB holdings',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data analyst verifying query plan accuracy against a bibliographic database',
      task: `Verify the interpreter results from data/eval/interpreter_nano_results.json against the actual database at ${args.dbPath}.

For each query result:

1. Read the interpreter's execution plan (steps, actions, params/filters)
2. Extract the key filters the interpreter produced (publisher, place, language, agent, date range, subject, etc.)
3. Run the equivalent SQL query against ${args.dbPath} to get the actual record count
4. Compare:
   - Did the interpreter choose the right action types? (retrieve vs aggregate vs resolve_agent etc.)
   - Did it produce correct/reasonable filters?
   - Does the expected record count from the query spec match what the filters would return?
   - For out-of-scope queries: did the interpreter recognize it as out of scope (low confidence, clarification, or empty results)?
   - For ambiguous queries: did the interpreter handle ambiguity well (clarification request, reasonable default, or multiple interpretations)?

5. Score each query on a 0-3 scale:
   - 3 = Perfect: correct action, correct filters, would return expected results
   - 2 = Good: mostly correct, minor filter issues but would still work
   - 1 = Partial: right intent but wrong/missing filters, would return wrong results
   - 0 = Failed: wrong action type, completely wrong filters, or crashed

6. Write detailed verification results to data/eval/interpreter_nano_verification.json with:
   - id, query, category, interpreter_score (0-3)
   - filters_produced (what the interpreter output)
   - sql_equivalent (what SQL you ran to verify)
   - actual_count (records that SQL returns)
   - expected_count (from the query spec)
   - assessment (1-2 sentence explanation)
   - issues (list of specific problems found, empty if none)

Return a summary with: average score per category (in_scope, out_of_scope, ambiguous), overall average, and a list of any queries that scored 0 or 1.`,
      instructions: [
        'Read both the results file and the queries file',
        'For each query, construct and run verification SQL',
        'Score objectively based on filter accuracy',
        'Pay special attention to out-of-scope and ambiguous handling',
        'Write verification results to data/eval/interpreter_nano_verification.json',
        'Return summary with scores per category'
      ],
      outputFormat: 'JSON summary with scores and issues'
    }
  }
}));

const analyzeTask = defineTask('analyze-recommend', (args) => ({
  kind: 'agent',
  title: 'Analyze evaluation results and produce recommendations',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior ML engineer analyzing model evaluation results for a production system',
      task: `Analyze the complete evaluation results and produce actionable recommendations.

Read these files:
1. data/eval/interpreter_nano_queries.json (the test queries)
2. data/eval/interpreter_nano_results.json (the interpreter outputs)
3. data/eval/interpreter_nano_verification.json (the verification scores)

Produce a comprehensive analysis report at docs/testing/models_comparisons/interpreter_nano_eval_report.md with:

## 1. Executive Summary
- Overall verdict: should ${args.model} replace gpt-4.1 as the default interpreter model?
- Key metrics: avg score, success rate, avg latency

## 2. Results by Category

### In-Scope Queries (8)
- Table: id | query | score | latency | key issues
- Patterns: what types of queries does nano handle well? What does it struggle with?

### Out-of-Scope Queries (2)
- Did it correctly identify these as out of scope?
- How did it handle queries about topics not in the collection?

### Ambiguous Queries (3)
- How did it handle ambiguity? Did it ask for clarification?
- Did it make reasonable default interpretations?

## 3. Comparison with gpt-4.1 Baseline
- Reference the previous test from docs/testing/models_comparisons/4_tests_03042026.txt
- Cost comparison (nano vs 4.1 pricing)
- Latency comparison
- Quality comparison

## 4. Failure Analysis
- Which queries scored 0-1 and why?
- Common patterns in failures
- Are failures acceptable for production use?

## 5. Recommendations
- Clear recommendation: change default or not, with reasoning
- If yes: any caveats or guardrails needed?
- If no: what model should be the default instead?
- Suggested follow-up evaluations

Write this report to docs/testing/models_comparisons/interpreter_nano_eval_report.md.

Return a concise summary (5-10 lines) of the key recommendation.`,
      instructions: [
        'Read all three evaluation files',
        'Be objective and data-driven in analysis',
        'Consider production implications (cost, latency, quality tradeoffs)',
        'Write the full report to the specified path',
        'Return only the key recommendation summary'
      ],
      outputFormat: 'Concise recommendation text'
    }
  }
}));
