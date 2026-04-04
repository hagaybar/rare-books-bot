/**
 * @process interpreter-mini-eval
 * @description Evaluate gpt-4.1-mini as interpreter — same 13 queries as nano eval, compare to actual DB holdings, recommend
 * @inputs { model: string, dbPath: string }
 * @outputs { success: boolean, recommendations: string }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    model = 'gpt-4.1-mini',
    dbPath = 'data/index/bibliographic.db',
  } = inputs;

  ctx.log('info', `Starting interpreter-only evaluation with model: ${model}`);

  // ============================================================================
  // PHASE 1: RUN INTERPRETER ON ALL 13 QUERIES (reuse existing query set)
  // ============================================================================

  ctx.log('info', `Phase 1: Run interpreter with ${model} on all 13 queries`);

  const runInterpreter = await ctx.task(runInterpreterTask, { model, dbPath });

  // ============================================================================
  // PHASE 2: VERIFY RESULTS AGAINST ACTUAL DB HOLDINGS
  // ============================================================================

  ctx.log('info', 'Phase 2: Verify interpreter plans against actual DB holdings');

  const verifyResults = await ctx.task(verifyResultsTask, { model, dbPath });

  // ============================================================================
  // PHASE 3: ANALYSIS & RECOMMENDATIONS
  // ============================================================================

  ctx.log('info', 'Phase 3: Analyze results and produce recommendations');

  const analyzeAndRecommend = await ctx.task(analyzeTask, { model });

  ctx.log('info', `Interpreter ${model} evaluation complete`);
  return { success: true, model, queryCount: 13 };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

const runInterpreterTask = defineTask('run-interpreter-mini', (args) => ({
  kind: 'agent',
  title: `Run ${args.model} interpreter on all 13 queries`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer running LLM evaluation',
      task: `Run the interpreter stage on all 13 queries from data/eval/interpreter_nano_queries.json using model "${args.model}".

IMPORTANT: This will make API calls to OpenAI. Proceed carefully.

Write and run a Python script that:
1. Reads the queries from data/eval/interpreter_nano_queries.json (same queries used for the nano evaluation)
2. For each query, calls the interpreter:
   \`\`\`python
   import asyncio, json, time, sys, os
   sys.path.insert(0, '/home/hagaybar/projects/rare-books-bot')
   os.chdir('/home/hagaybar/projects/rare-books-bot')
   from scripts.chat.interpreter import interpret

   queries = json.load(open('data/eval/interpreter_nano_queries.json'))
   results = []
   for q in queries:
       print(f"Running {q['id']}: {q['query'][:60]}...")
       start = time.time()
       try:
           plan = asyncio.run(interpret(q['query'], model='${args.model}'))
           elapsed = time.time() - start
           steps = []
           for s in plan.execution_steps:
               step_info = {'action': s.action}
               if hasattr(s.params, '__dict__'):
                   step_info['params'] = {k: v for k, v in s.params.__dict__.items() if v is not None}
               else:
                   step_info['params'] = str(s.params)
               steps.append(step_info)
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
               'steps': steps
           })
           print(f"  OK ({elapsed:.1f}s) confidence={plan.confidence} intents={plan.intents}")
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
           print(f"  FAIL ({elapsed:.1f}s): {e}")
       time.sleep(0.5)

   with open('data/eval/interpreter_mini_results.json', 'w') as f:
       json.dump(results, f, indent=2, default=str)
   print(f"\\n=== SUMMARY ===")
   successes = sum(1 for r in results if r['success'])
   failures = sum(1 for r in results if not r['success'])
   avg_lat = sum(r['latency_s'] for r in results) / len(results)
   print(f"Total: {len(results)}, Success: {successes}, Failed: {failures}, Avg latency: {avg_lat:.2f}s")
   \`\`\`
3. Save results to data/eval/interpreter_mini_results.json

CRITICAL: The interpret() function is async, use asyncio.run() for each call. Delete the script after running.

Return a summary with: total queries, successes, failures, average latency, and any errors encountered.`,
      instructions: [
        'Read the queries file first',
        'Run interpreter on each query with the specified model',
        'Save results to data/eval/interpreter_mini_results.json',
        'Report summary statistics',
        'Delete the script after running'
      ],
      outputFormat: 'JSON summary with statistics'
    }
  }
}));

const verifyResultsTask = defineTask('verify-results-mini', (args) => ({
  kind: 'agent',
  title: 'Verify interpreter plans against actual DB holdings',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data analyst verifying query plan accuracy against a bibliographic database',
      task: `Verify the interpreter results from data/eval/interpreter_mini_results.json against the actual database at ${args.dbPath}.

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

6. Write detailed verification results to data/eval/interpreter_mini_verification.json with:
   - id, query, category, interpreter_score (0-3)
   - filters_produced (what the interpreter output)
   - sql_equivalent (what SQL you ran to verify)
   - actual_count (records that SQL returns)
   - expected_count (from the query spec)
   - assessment (1-2 sentence explanation)
   - issues (list of specific problems found, empty if none)

Use the SAME scoring criteria as the nano evaluation for consistency:
- OUT-OF-SCOPE: Score 3 if low confidence (<0.7) OR clarification OR filters return 0. Score 2 if moderate confidence (0.7-0.85) with reasonable filters. Score 1 if confidently (>0.85) produces filters for OOS content. Score 0 if hallucination.
- AMBIGUOUS: Score 3 if asked for clarification OR handled ambiguity explicitly. Score 2 if reasonable default. Score 1 if poor default. Score 0 if misinterpreted entirely.

Return a summary with: average score per category (in_scope, out_of_scope, ambiguous), overall average, and list of queries scoring 0 or 1.`,
      instructions: [
        'Read data/eval/interpreter_mini_results.json and data/eval/interpreter_nano_queries.json',
        'For each query, construct and run verification SQL',
        'Score objectively — use same criteria as nano eval',
        'Write to data/eval/interpreter_mini_verification.json',
        'Return summary with scores per category'
      ],
      outputFormat: 'JSON summary with scores and issues'
    }
  }
}));

const analyzeTask = defineTask('analyze-recommend-mini', (args) => ({
  kind: 'agent',
  title: 'Analyze evaluation results and produce recommendations',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior ML engineer analyzing model evaluation results for a production system',
      task: `Analyze the gpt-4.1-mini evaluation results and produce a comprehensive report comparing it against the nano evaluation.

Read these files:
1. data/eval/interpreter_nano_queries.json (the 13 test queries)
2. data/eval/interpreter_mini_results.json (the mini interpreter outputs)
3. data/eval/interpreter_mini_verification.json (the mini verification scores)
4. data/eval/interpreter_nano_results.json (the nano results for comparison)
5. data/eval/interpreter_nano_verification.json (the nano scores for comparison)
6. docs/testing/models_comparisons/4_tests_03042026.txt (previous gpt-4.1 baseline test)
7. docs/testing/models_comparisons/interpreter_nano_eval_report.md (the nano report for reference)

Produce a comprehensive analysis report at docs/testing/models_comparisons/interpreter_mini_eval_report.md with:

## 1. Executive Summary
- Overall verdict: should ${args.model} replace gpt-4.1 as the default interpreter model?
- Key metrics: avg score, success rate, avg latency

## 2. Results by Category

### In-Scope Queries (8)
- Table: id | query (truncated) | score | latency | key issues
- Patterns: what does mini handle well vs poorly?

### Out-of-Scope Queries (2)
- Did it correctly identify these as out of scope?

### Ambiguous Queries (3)
- How did it handle ambiguity?

## 3. Head-to-Head: mini vs nano vs gpt-4.1
- Side-by-side table: query | nano score | mini score | gpt-4.1 baseline (from previous test)
- Cost comparison: nano (~$0.10/$0.40 per M tokens), mini (~$0.40/$1.60 per M tokens), gpt-4.1 ($2/$8 per M tokens)
- Latency comparison
- Quality comparison: which model handles which query types better?

## 4. Failure Analysis
- Which queries scored 0-1 and why?
- Compare failure patterns between mini and nano
- Are mini failures a subset of nano failures or different?

## 5. Recommendations
- Clear recommendation: which model should be the default interpreter?
- Decision matrix: cost vs quality vs latency tradeoff
- Suggested follow-up evaluations

Write this report to docs/testing/models_comparisons/interpreter_mini_eval_report.md.

Return a concise 5-10 line summary of the key recommendation.`,
      instructions: [
        'Read all evaluation files for both models',
        'Be objective and data-driven',
        'Create side-by-side comparisons where possible',
        'Write the full report to the specified path',
        'Return only the key recommendation summary'
      ],
      outputFormat: 'Concise recommendation text'
    }
  }
}));
