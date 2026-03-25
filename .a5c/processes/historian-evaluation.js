/**
 * @process historian-evaluation
 * @description Professional historian persona evaluation of the Rare Books Bot.
 * Creates 20 domain-expert questions, simulates answers through the actual pipeline,
 * performs gap analysis, and produces top 5 enhancement recommendations.
 * @inputs { projectRoot: string }
 * @outputs { success: boolean, reportPath: string }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  const startTime = ctx.now();

  ctx.log('info', 'Starting Historian Persona Evaluation');

  // Phase 1: Design 20 questions + quality criteria
  // The agent must understand our data to create grounded questions
  const questionsResult = await ctx.task(designQuestionsTask, { projectRoot });

  // Phase 2: Simulate — run all 20 questions through the actual pipeline
  const simulationResult = await ctx.task(simulateQueriesTask, { projectRoot, questions: questionsResult });

  // Phase 3: Gap analysis + synthesis → final report
  const analysisResult = await ctx.task(analyzeAndSynthesizeTask, { projectRoot, questions: questionsResult, simulation: simulationResult });

  return {
    success: true,
    reportPath: analysisResult.reportPath,
    duration: ctx.now() - startTime
  };
}

export const designQuestionsTask = defineTask('design-questions', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Step 1-2: Design 20 historian questions with quality criteria',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are simultaneously: (A) Professor David Stern, a historian of the printed book at a major university, specializing in early modern Hebrew printing, with deep expertise in Venetian, Amsterdam, and Ottoman print houses. You bring students to the rare books floor to study physical copies. AND (B) a systems analyst who understands database schemas.',
      task: 'Create 20 questions that Professor Stern would naturally ask the Rare Books Bot. These questions must NOT be designed to fit our DB structure — they must reflect how a real historian thinks about books.',
      context: {
        projectRoot: args.projectRoot,
        collectionProfile: {
          totalRecords: 2796,
          dateRange: '1244-2025',
          topLanguages: 'Hebrew (806), Latin (505), French (500), German (496), English (366)',
          topPlaces: 'Paris (356), London (230), Amsterdam (196), Venice (164), Berlin (123), Jerusalem (109)',
          topAgents: 'Faitlovitch (40), Wurmbrand (38), Josephus (21), Buxtorf (19)',
          topSubjects: 'Ethiopic manuscripts (39), Hiddushim/Jewish law (30), Hebrew grammar (27), Book collecting (24)',
          enrichedAgents: '2665 with Wikidata bios, teachers/students, notable works',
          publisherAuthorities: '227 (18 printing houses, 202 unresearched)',
          hebrewPublishers: '553 in Hebrew script',
          agentRoles: 'author (2164), other (1924), printer (38), editor (36), translator (36)'
        }
      },
      instructions: [
        'IMPORTANT: First, run these SQL queries to understand the actual data deeply:',
        'sqlite3 /home/hagaybar/projects/rare-books-bot/data/index/bibliographic.db "SELECT value, count(*) FROM subjects GROUP BY value ORDER BY count(*) DESC LIMIT 30;"',
        'sqlite3 /home/hagaybar/projects/rare-books-bot/data/index/bibliographic.db "SELECT agent_norm, role_raw, count(DISTINCT record_id) FROM agents WHERE role_raw = \'printer\' OR role_raw = \'printer.\' GROUP BY agent_norm ORDER BY count(DISTINCT record_id) DESC LIMIT 15;"',
        'sqlite3 /home/hagaybar/projects/rare-books-bot/data/index/bibliographic.db "SELECT t.value, i.place_norm, i.date_start FROM titles t JOIN records r ON t.record_id = r.id JOIN imprints i ON r.id = i.record_id WHERE i.date_start < 1500 ORDER BY i.date_start LIMIT 10;"',
        'sqlite3 /home/hagaybar/projects/rare-books-bot/data/index/bibliographic.db "SELECT place_norm, count(*), min(date_start), max(date_end) FROM imprints WHERE place_norm = \'venice\' GROUP BY place_norm;"',
        '',
        'Now create 20 questions across these categories:',
        '',
        'CATEGORY A: Printing History (5 questions)',
        'Questions about how printing developed in specific cities, the role of specific print houses,',
        'the relationship between printers and authors. Example: "What can you tell me about Hebrew',
        'printing in Venice?" or "Which printers in this collection were active before 1550?"',
        '',
        'CATEGORY B: Intellectual Networks (5 questions)',
        'Questions about teacher-student relationships, schools of thought, how ideas traveled.',
        'Example: "Which rabbinic authorities in this collection were connected to Nahmanides?"',
        'or "Can you trace the intellectual lineage of the authors in the Jewish law section?"',
        '',
        'CATEGORY C: Collection Character (5 questions)',
        'Questions about what makes this collection distinctive, what themes emerge, what gaps exist.',
        'Example: "What is the geographic distribution of this collection?" or "How does this',
        'collection represent the history of Hebrew printing?"',
        '',
        'CATEGORY D: Teaching Support (5 questions)',
        'Questions a professor would ask when preparing a class or guiding students.',
        'Example: "I need 5 examples of incunabula for my students to examine" or',
        '"Which books would best illustrate the Counter-Reformation\'s impact on Hebrew printing?"',
        '',
        'For each question, specify QUALITY CRITERIA — what a good answer must include:',
        '- Accuracy: factual correctness',
        '- Richness: contextual depth beyond bare metadata',
        '- Cross-referencing: connecting books to authors to historical context',
        '- Narrative quality: readable, scholarly, not just a data dump',
        '- Source citation: provenance of claims',
        '- Pedagogical value: useful for teaching/learning',
        '',
        'Return JSON with questions array, each: {id, category, question, qualityCriteria[], expectedAnswerElements[]}',
        'Do NOT write any files yet.'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['questions'],
      properties: { questions: { type: 'array' } }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['research', 'questions', 'historian']
}));

export const simulateQueriesTask = defineTask('simulate-queries', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Step 3: Simulate all 20 questions through the actual pipeline',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer running systematic query simulations',
      task: 'Run all 20 historian questions through the actual query pipeline and the narrative agent, capturing complete results.',
      context: {
        projectRoot: args.projectRoot,
        questions: args.questions
      },
      instructions: [
        'For each of the 20 questions from the previous step, run this Python script pattern:',
        '',
        'cd /home/hagaybar/projects/rare-books-bot && poetry run python -c "',
        'import sys, json',
        'sys.path.insert(0, \\".\\")',
        'from scripts.query.service import QueryService',
        'from scripts.chat.narrative_agent import generate_agent_narrative',
        'from pathlib import Path',
        'qs = QueryService(Path(\\"data/index/bibliographic.db\\"))',
        'try:',
        '    result = qs.execute(\\"<QUESTION>\\")',
        '    cs = result.candidate_set',
        '    count = len(cs.candidates)',
        '    titles = [c.title for c in cs.candidates[:5]]',
        '    authors = [c.author for c in cs.candidates[:5]]',
        '    places = list(set(c.place_norm for c in cs.candidates if c.place_norm))[:10]',
        '    dates = sorted(set(c.date_start for c in cs.candidates if c.date_start))[:5]',
        '    narrative = generate_agent_narrative(cs, Path(\\"data/index/bibliographic.db\\"))',
        '    plan_filters = [(f.field.value, f.op.value, f.value or f\\"{f.start}-{f.end}\\") for f in result.query_plan.filters] if result.query_plan else []',
        '    print(json.dumps({',
        '        \\"count\\": count,',
        '        \\"titles\\": titles,',
        '        \\"authors\\": authors,',
        '        \\"places\\": places,',
        '        \\"dates\\": dates,',
        '        \\"narrative\\": narrative[:500] if narrative else None,',
        '        \\"filters\\": plan_filters,',
        '        \\"time_ms\\": result.execution_time_ms',
        '    }))',
        'except Exception as e:',
        '    print(json.dumps({\\"error\\": str(e), \\"count\\": 0}))',
        '"',
        '',
        'Run ALL 20 queries. For each, capture:',
        '- result_count: number of candidates',
        '- filters_applied: what the query compiler extracted',
        '- sample_titles: first 5 titles',
        '- sample_authors: first 5 authors',
        '- places_in_results: distinct places',
        '- date_range_in_results: earliest and latest dates',
        '- narrative_generated: yes/no and first 500 chars',
        '- execution_time_ms',
        '- error: if any',
        '',
        'Return JSON with simulations array, each: {questionId, query, resultCount, filtersApplied, sampleTitles, narrative, executionTimeMs, error}'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['simulations'],
      properties: { simulations: { type: 'array' } }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['simulation', 'testing', 'pipeline']
}));

export const analyzeAndSynthesizeTask = defineTask('analyze-synthesize', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Steps 4-7: Gap analysis + code proposals + final synthesis report',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior product analyst and software architect performing a comprehensive gap analysis',
      task: 'Analyze gaps between what a historian professor would expect and what the bot actually delivered, then produce a final synthesis report with top 5 enhancement recommendations.',
      context: {
        projectRoot: args.projectRoot,
        questions: args.questions,
        simulations: args.simulation
      },
      instructions: [
        'Read the questions (with quality criteria) and simulation results.',
        'Also read these key code files to understand what changes would be needed:',
        '- /home/hagaybar/projects/rare-books-bot/app/api/main.py (chat endpoint, Phase 2 exploration)',
        '- /home/hagaybar/projects/rare-books-bot/scripts/chat/narrative_agent.py (narrative generation)',
        '- /home/hagaybar/projects/rare-books-bot/scripts/query/service.py (query execution)',
        '- /home/hagaybar/projects/rare-books-bot/scripts/chat/formatter.py (response formatting)',
        '',
        'Write the FULL report to: /home/hagaybar/projects/rare-books-bot/reports/historian-evaluation.md',
        '',
        'The report MUST have these sections:',
        '',
        '## 1. Professor Persona & Methodology',
        'Brief description of the professor persona and why these questions matter.',
        '',
        '## 2. The 20 Questions',
        'Table: #, Category, Question, Quality Criteria (abbreviated)',
        '',
        '## 3. Simulation Results',
        'For each question: query sent, filters applied, result count, sample results,',
        'whether narrative was generated, execution time.',
        'Use a condensed format — one subsection per question with a results box.',
        '',
        '## 4. Gap Analysis',
        'For each question, analyze:',
        '- What the professor would expect in a good answer',
        '- What the bot actually returned',
        '- Score each on: Accuracy (0-5), Richness (0-5), Cross-referencing (0-5),',
        '  Narrative Quality (0-5), Pedagogical Value (0-5)',
        '- Identify the ROOT CAUSE of each gap (is it data? query compilation? formatting? missing capability?)',
        '',
        '## 5. Gap Pattern Analysis',
        'Group the gaps into patterns:',
        '- Which types of questions fail systematically?',
        '- What capabilities are missing?',
        '- What data is missing vs what data exists but is not used?',
        '',
        '## 6. Top 5 Enhancements',
        'For each enhancement:',
        '- Name and one-sentence description',
        '- Which questions it would improve (by number)',
        '- Expected impact: how many questions go from FAIL/POOR to GOOD',
        '- Implementation tasks (specific, actionable):',
        '  - Files to modify',
        '  - Functions to create or change',
        '  - Data to add or transform',
        '  - Estimated effort',
        '- Priority: CRITICAL / HIGH / MEDIUM',
        '',
        '## 7. Score Summary',
        'Table: Question #, Accuracy, Richness, Cross-ref, Narrative, Pedagogical, Total/25',
        'Average scores. Before/after projections for each enhancement.',
        '',
        'Be decisive and specific. Reference actual code paths and data shapes.',
        'The enhancement recommendations should be immediately implementable.',
        '',
        'Return JSON with: {reportPath, averageScore, topEnhancements: [{name, impact, effort}]}'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['reportPath'],
      properties: {
        reportPath: { type: 'string' },
        averageScore: { type: 'number' },
        topEnhancements: { type: 'array' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['analysis', 'synthesis', 'report']
}));
