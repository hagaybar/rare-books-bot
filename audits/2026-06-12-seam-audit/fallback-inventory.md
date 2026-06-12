# Silent-Fallback Inventory

Date: 2026-06-12 | Branch: dev | Scope: `scripts/` and `app/` (160 .py files; 70 files contain `except`)
Method: full `rg` sweep of every `except` block (745 context lines reviewed), plus `.get(..., default)` and `or ''/[]/{}` coercions on cross-module/loaded data. Every row verified by reading the cited excerpt. Risk classes: HIGH = silently changes results/evidence; MEDIUM = degrades quality visibly; LOW = cosmetic / intentional best-effort.

Calibration (known + fixed, listed for completeness, NOT new findings):
- **FIXED #43** — `scripts/query/execute.py:214-235` `_marc_source_from_provenance` previously emitted `marc:unknown` for agent evidence; now parses both provenance shapes (commit 7aa4610). Residual `default="unknown"` only fires on corrupt provenance JSON.
- **FIXED #53** — `scripts/metadata/seed_agent_authorities.py` agent_aliases comma-split seeding (commit e8dff58 + fix_29 repair).

## Inventory table (sorted by risk)

| file:line | pattern | failure hidden | user-visible effect | logged? | risk |
|---|---|---|---|---|---|
| scripts/query/db_adapter.py:52-53 | `except Exception: _agent_alias_tables_present = False` (cached module-wide) | Any error in the `sqlite_master` existence check (locked DB, bad conn, transient I/O) | Alias-resolution EXISTS branch (db_adapter.py:388-410) silently omitted from SQL → agent queries miss alias/cross-script matches → smaller CandidateSet; result cached for process lifetime | no | HIGH |
| scripts/marc/parse.py:769-771 | `except Exception: print(...); records = []` around whole-file `parse_xml_to_array` | Total MARC XML parse failure (corrupt export, bad path contents) | Pipeline continues with 0 records, writes an empty canonical JSONL; only a stdout print + zero counts in ExtractionReport. Violates project hard rule: "On MARC parse failure: log the error to data/runs/ ... and stop" | partial (stdout print only; not data/runs/, no stop) | HIGH |
| scripts/chat/narrator.py:269-271 | `except Exception: return 0.85` in post-streaming meta extraction | Meta-extraction LLM call failure | A fabricated confidence score of 0.85 is presented as if measured — violates "never invent values" | debug-level only | HIGH |
| scripts/metadata/feedback_loop.py:394-395 | `except Exception: return 0` in `_renormalize_records` UPDATE | Any DB error while applying an approved correction (locked DB, missing column, bad SQL) | Correction silently not applied; "0 rows updated" is indistinguishable from "no rows matched" — curator believes the correction landed or had no targets | no | HIGH |
| scripts/query/concept_bridge.py:35-37, 40-45 | missing map file → `return {}`; `raw.get("concepts", [])` | Concept-map file deleted/renamed/moved; or top-level key missing/typo'd in the JSON | Concept expansion silently disabled → queries that depend on bridge expansions return fewer candidates, with zero signal. Docstring declares missing-file intentional ("bridge disabled, not an error"), but there is no log distinguishing intended-absent from accidentally-absent | no | HIGH |
| scripts/query/execute.py:260-262, 278-279, 296-297 | `except (JSONDecodeError, IndexError, TypeError): source_tags = "unknown"` | Corrupt `source_tags` JSON in imprints rows | Evidence `source` degrades to `marc:unknown` for publisher/place/year — provenance lost but at least labeled "unknown" (same family as #43, which fixed only the agent path) | no | MEDIUM |
| scripts/query/execute.py:554-556 | `except Exception: print("Retry failed")` around subject-mapping retry | Retry compilation/execution error after zero-result query | User gets the original zero results; failure reason only on stdout (not logger), invisible in API context | partial (stdout print) | MEDIUM |
| scripts/query/execute.py:568-578 | `except Exception:` → warning + placeholder Evidence | Evidence extraction crash for a filter | Candidate kept but with degraded/placeholder evidence entry | yes (warning + marked in evidence) | MEDIUM |
| scripts/query/execute.py:87-89, 109-111, 134-136, 164-166, 190-192 | `except Exception: logger.warning(...)` per display query in `fetch_display_info` | Title/author/imprint/subjects/notes query failures | Result list renders with missing titles/authors/etc. (None via execute.py:602-612 `.get` defaults); CandidateSet itself unaffected | yes (warning) | MEDIUM |
| scripts/query/llm_compiler.py:428-430 | `except Exception: pass` on cached-plan validation | Cache entry no longer matches QueryPlan schema | Silent re-compile via LLM → plan (and thus CandidateSet) may differ from the previously validated cached plan between runs; nondeterminism with no signal | no | MEDIUM |
| scripts/chat/session_store.py:565-569 | `except Exception:` → warning, `candidate_set` stays None | Stored CandidateSet JSON unparseable | Follow-up turns lose the active-subgroup CandidateSet (record_ids survive); refinements degrade | yes (warning) | MEDIUM |
| scripts/chat/interpreter.py:907-915, 950 | `except (ValueError, KeyError, TypeError):` skip plan step | Malformed LLM plan step | Step dropped from execution; logged and surfaced in `dropped_steps`, but the answer is computed from a reduced plan | yes (warning + `dropped_steps`) | MEDIUM |
| scripts/chat/interpreter.py:933-934 | `except (JSONDecodeError, TypeError): params_dict = {}` | Malformed directive params from LLM | Scholarly directive runs with empty params — behavior silently differs from the planned directive | no | MEDIUM |
| scripts/chat/executor.py:124-125 | `except Exception: pass # Auto-connections are best-effort` | Any failure in `find_connections` grounding enrichment | Connections section silently absent from grounding/narrative; user cannot tell "no connections" from "lookup crashed" | no | MEDIUM |
| scripts/chat/cross_reference.py:83-85, 290-292, 441-443 | `except sqlite3.OperationalError:` → return empty graph/connections | Missing tables or any operational DB error | Cross-reference answers show "no connections" instead of an error | yes (warning) | MEDIUM |
| scripts/chat/cross_reference.py:421-422 | `except sqlite3.OperationalError: return connections` (no log) | Same as above, one branch unlogged | Same as above, fully silent | no | MEDIUM |
| scripts/chat/narrator.py:180-182, 233-244 | `except Exception:` → `_fallback_response` (sync + streaming) | Narrator LLM failure | User gets template fallback narrative instead of scholarly response; grounded data still shown | yes (logger.exception) | MEDIUM |
| scripts/models/config.py:52-54 | `except (JSONDecodeError, KeyError):` → default `ModelConfig()` | Corrupt/incomplete model config file | All pipeline stages silently run on default models — different cost/quality than configured | yes (warning) | MEDIUM |
| scripts/marc/m3_index.py:32-33 | `except (FileNotFoundError, JSONDecodeError): COUNTRY_CODE_MAP = {}` | Missing/corrupt `marc_country_codes.json` | Country-code resolution silently disabled during indexing; place enrichment degrades for the whole build | no | MEDIUM |
| scripts/network/build_network_tables.py:86-87, 262-263, 366-367, 733-734 | `except (JSONDecodeError, TypeError): continue/pass` | Corrupt person_info/categories JSON per agent | Agents silently dropped from network nodes/edges/communities → map view missing people with no count of drops | no | MEDIUM |
| app/api/security.py:113-114, 122-124 | non-200 or `except Exception:` → `return True, None  # Fail open` | Moderation API outage/error | Unmoderated input passes through; deliberate fail-open trade-off | yes (warning) | MEDIUM |
| scripts/query/service.py:437-439 | `except Exception:` → `return {}` for facets | Facet query failure | Facet panel silently empty in UI | yes (warning) | MEDIUM |
| app/api/metadata_corrections.py:84-89 | `except Exception: return 0` in `_count_affected_records` | Any DB error while counting affected records | Workbench shows "0 affected records" for a correction that may affect many | no | MEDIUM |
| scripts/metadata/agent_harness.py:408-409 | `except (JSONDecodeError, KeyError): continue` on cache lines | Corrupt agent-mapping cache entries | Cache misses → repeat (paid) LLM calls for already-resolved values; no count of skipped lines | no | MEDIUM |
| scripts/enrichment/run_name_enrichment.py:65-66 | `except Exception: cached_keys = set()` | Cache DB unreadable/missing table | Treats everything as uncached → re-enriches all agents (re-spends API calls/time); masks cache corruption | no | MEDIUM |
| app/api/feedback_routes.py:153-154 | `except Exception: pass` around `audit_log` | Audit-log write failure | Feedback action succeeds with no audit trail — silent loss of a security/accountability record | no | MEDIUM |
| scripts/eval/run_eval.py:270-272 | `except Exception:` → `score_combined = 0` | Judge scoring crash | Model scored 0 in comparisons — skews eval rankings; warning logged but score is recorded as a real 0 | yes (warning) | MEDIUM |
| app/api/auth_service.py:13-24 | `os.environ.get("JWT_SECRET", "")` → auto-generate if empty | Unset JWT_SECRET in production deploy | Sessions invalidated on every restart; warning printed at import; <32-char secrets do raise | partial (stdout warning) | MEDIUM |
| scripts/marc/parse.py:45-47, 69-71, 113-115, 128-130, 146-148, 164-166, 595-597, 620-622, 644-646, 670-672 | `except KeyError: pass` → return None/[] in field extractors | Absent MARC field (pymarc raises KeyError) | Field absent in canonical record — intentional missing-field semantics; raw values preserved | n/a (by design) | LOW |
| scripts/marc/parse.py:858-868 | per-record `except Exception:` → `failed_records.append` | Single-record extraction crash | Record excluded; counted in ExtractionReport `failed_extractions` + printed traceback (first 3) | yes (report + stdout) | LOW |
| scripts/marc/build_place_freq.py:99-110, 141-143 | `except (KeyError, AttributeError): pass`; parse fail → partial return + print | Missing 260/264; XML parse failure in dev tool | Frequency report partial; printed | partial | LOW |
| scripts/marc/m3_contract.py:443-446 | `except Exception:` → warning + errors list | Schema validation crash | Mismatch reported in returned errors, never raises (documented) | yes | LOW |
| scripts/marc/m3_index.py:166-168, 558-561, 576-578 | `except Exception:` → print + stats counters | Enrichment/load errors per item | Counted in stats, printed | yes (stdout + stats) | LOW |
| scripts/marc/rebuild_pipeline.py:154-157 | `except ImportError:` → shutil backup fallback | Missing backup util module | Equivalent backup via copy2 | n/a | LOW |
| scripts/query/llm_compiler.py:327-338, 435-446 | typed `except` → raise `QueryCompilationError` | (not a swallow — converts and re-raises) | Error surfaced to caller | yes | LOW |
| scripts/query/llm_compiler.py:366-372 | `except (JSONDecodeError, KeyError): continue` on cache lines | Corrupt plan-cache lines | Cache miss → recompile; cosmetic | no | LOW |
| scripts/query/llm_compiler.py:463-465 | `except Exception: pass` on cache write | Cache write failure | None (next query recompiles) | no | LOW |
| scripts/query/execute.py:602-612 | `display_info.get(id, {})` / `info.get(...)` | Missing display row (downstream of logged fetch failures) | None fields in display | upstream warning | LOW |
| scripts/chat/interpreter.py:626-629 | `except ValueError: pass` on year EQUALS coercion | Non-integer year value | Filter left as EQUALS; likely 0 matches reported honestly | no | LOW |
| scripts/chat/interpreter.py:764-776 | JSON repair attempts, re-raises original on failure | (not a swallow — re-raises) | Error surfaced | yes (raise) | LOW |
| scripts/chat/executor.py:374-388 | step `except Exception:` → StepResult(status=error) | Handler crash | Step error surfaced in ExecutionResult | yes (logger.exception + StepResult) | LOW |
| scripts/chat/executor.py:1414-1417, 2018-2021 | `except (JSONDecodeError, TypeError): pass` → `person_info = {}` | Corrupt person_info JSON | Agent bio/dates missing in summary | no | LOW |
| scripts/chat/executor.py:1505-1513 | `except Exception: wiki_row = None  # Table may not exist` | Any sqlite error (broader than missing table) | Wikipedia context absent for agent | no | LOW |
| scripts/chat/executor.py:754-755 | `or ""` / `or []` on step-result attrs | None query_name/variants | Fallback token search uses fewer sources | no | LOW |
| scripts/chat/cross_reference.py:97-98 | `except (JSONDecodeError, TypeError): person_info = {}` | Corrupt person_info | Node lacks bio attributes in graph | no | LOW |
| scripts/chat/cross_reference.py:539-540 | `except Exception: pass  # Table may not exist` | Missing optional table | One connection source skipped | no | LOW |
| scripts/chat/curation_engine.py:85-210 (`or []`/`or ""` x6), 361-365 (`.get("score", 0.0)`) | None-coercions on candidate dicts | Missing candidate fields | Curation heuristics skip signals | no | LOW |
| scripts/chat/aggregation.py:647-679 | `overview.get(..., [])` | Missing keys in same-module overview dict | Aggregation sections omitted | no | LOW |
| scripts/chat/narrator.py:748-772, 945-957 | `.get("agent_a", "")`, `agg_meta.get(field, {})` | Missing keys in connection/meta dicts | Blank names / default meta in prompt text | no | LOW |
| scripts/models/llm_client.py:133-135 | `except Exception: cost = 0.0` | completion_cost() failure | Cost logged as 0.0 | debug | LOW |
| scripts/models/llm_client.py:272-273 | `except Exception:` warning on streaming usage logging | Usage-logging failure | Usage stats missing | yes (warning) | LOW |
| scripts/models/config.py:64-65 | `except AttributeError: raise KeyError` | (re-raise, not a swallow) | Surfaced | yes | LOW |
| scripts/utils/llm_logger.py:115-116, 127-128, 265-266, 327-328 | `pass` / `return 0.0` / `continue` | Cost calc / malformed log lines | LLM usage stats undercount | no | LOW |
| scripts/utils/llm_logger.py:228-229 | warning on log-write failure | Log write failure | LLM call log entry lost | yes (warning) | LOW |
| scripts/utils/config_loader.py:41-44 | logs then `raise` | (not a swallow) | Surfaced | yes | LOW |
| scripts/utils/logger.py:18-19 | `except ImportError: COLORLOG_AVAILABLE = False` | colorlog not installed | Plain log colors | n/a | LOW |
| scripts/metadata/interaction_logger.py:69-70 | `except OSError: pass  # Never let logging break the request` | Interaction-log write failure | One audit-ish log line lost (deliberate) | no (deliberate) | LOW |
| scripts/metadata/review_log.py:210-213 | warning + skip malformed line | Corrupt review-log line | Entry missing from review list | yes (warning) | LOW |
| scripts/metadata/feedback_loop.py:120-126, 307-308 | `except` → error in CorrectionResult / error dict | Correction validation/processing error | Error surfaced in response payload | yes (in payload) | LOW |
| scripts/metadata/publisher_authority.py:174-175; scripts/metadata/agent_authority.py:176-177 | `except (JSONDecodeError, TypeError): return []` on alt_names | Corrupt alias JSON | Authority shows no variants | no | LOW |
| scripts/metadata/seed_agent_authorities.py:71-72, 120-121, 331-332 | IntegrityError → False/pass; person_info → None | Duplicate insert; corrupt JSON | Seeding skips duplicates (intended); bio absent | no | LOW |
| scripts/metadata/populate_publisher_authority.py:356, 398, 461 | IntegrityError → `log_entry(log_file, "error", ...)` | Duplicate/constraint violations | Recorded in run log file | yes (run log) | LOW |
| scripts/metadata/agents/date_agent.py:389-390 | `except (JSONDecodeError, ValueError, TypeError): pass` | Malformed LLM date payload | Date mapping left unset (null-on-uncertainty per data-model rules) | no | LOW |
| scripts/metadata/agent_harness.py:31-32 | `except RuntimeError: loop = None` | No running event loop | Sync path used | n/a | LOW |
| scripts/feedback/report_store.py:41-42 | `except Exception: return "unknown"` git sha | git unavailable | Report stamped "unknown" sha | no | LOW |
| scripts/feedback/report_store.py:101-103 | save-first: `assembly_error` recorded in payload | Transcript assembly failure | Error visible inside saved report | yes (in payload) | LOW |
| scripts/qa/data_quality_checks.py:297-298 | `except (JSONDecodeError, TypeError): continue` | Corrupt person_info in QA scan | Agent skipped from one check | no | LOW |
| scripts/qa/fixes/fix_13:158-159, fix_14:85-86 + 126-128, fix_15:113-114, fix_20:193-195 | pass / return 0 / skipped counter / raise | One-time fix scripts; mostly counted or raised | Operator-run, output printed | mostly yes | LOW |
| scripts/eval/run_eval.py:98-104, 145-150, 196-201 | `except Exception:` → error dict in result | Recall/stage call failure | Error recorded per eval entry | yes (in results) | LOW |
| scripts/eval/run_diagnostic_suite.py:68-69, 88-89, 104-110, 131-134, 148-151 | `except Exception:` → error fields + traceback in result | Diagnostic stage crash | Error visible in suite output | yes (in results) | LOW |
| scripts/enrichment/nli_client.py:143-144, 235-236, 300-301, 344-345, 569-570 | network/JSON `except` → pass/{} /continue | NLI API or manual-mapping file failures | Best-effort enrichment skips entries | no | LOW |
| scripts/enrichment/wikidata_client.py:188-190, 232-233, 269-270, 293-294 | → None/[]/continue/pass | SPARQL/parse failures | Enrichment item skipped (188 printed; 232 silent) | partial | LOW |
| scripts/enrichment/wikipedia_client.py:152-155, 237-239, 294-302 | → None/continue with warning | HTTP failures | Batch items skipped | yes (warning) | LOW |
| scripts/enrichment/wikipedia_connections.py:174-175, 432-437, 872-877, 891-892, 1064-1067 | → []/dup warnings/error logs/pass | Parse/dup/LLM failures | Connections skipped | mostly yes | LOW |
| scripts/enrichment/enrichment_service.py:186-187 | `except Exception: return None` cache_get | Corrupt cache row | Treated as cache miss → re-fetch | no | LOW |
| scripts/enrichment/fast_batch_enrichment.py:157-184, 239-242, 264-265, 319-320 | retry prints / counters / `pass` | SPARQL/cache errors in batch tool | Items skipped; partially printed | partial | LOW |
| scripts/enrichment/batch_wikipedia.py:346-348 | print + skipped counter | Per-agent extraction error | Counted | yes (stdout) | LOW |
| scripts/enrichment/populate_authority_enrichment.py:233-234 | `except Exception:` → stat = 0 | URL-fix step failure | Stat shows 0 fixed | no | LOW |
| scripts/enrichment/reenrich_with_relationships.py:91-93 | error counter, print first 5 | Per-agent failure | Counted | yes (stdout) | LOW |
| scripts/normalization/apply_wikidata_roles.py:127-129, 259-262 | counted skip; rollback + raise | Corrupt JSON; txn failure | Stats counter; txn surfaced | yes | LOW |
| scripts/normalization/fetch_tier2_occupations.py:86-88, 209-210, 415-418, 479-482 | warning→None; `person_info = {}`; logged counters; rollback+raise | SPARQL/JSON/txn failures | Counted/logged; 209 silently resets corrupt person_info to minimal dict | mostly yes | LOW |
| scripts/normalization/generate_place_alias_map.py:331-336, 367-368 | error dict; keep-primary pass | Lookup failure | Recorded in output / primary kept | partial | LOW |
| scripts/normalization/occupation_mapper.py:89-90 | `except ValueError: idx = len(priority_order)` | Role not in priority list | Sorts last (intended) | n/a | LOW |
| app/api/main.py:308-332 | `except Exception:` → error response; inner body-parse `pass` (331-332) | Interaction-middleware body parse failure | Log params less detailed | no | LOW |
| app/api/main.py:427-428 | `except Exception: pass` in health check | DB check crash | /health shows not-ready without reason | no | LOW |
| app/api/main.py:636-641, 1131-1132, 1162-1163, 1174-1189 | logger.exception + error responses; final send/close `pass` | Chat/WebSocket errors | Errors surfaced to client; teardown best-effort | yes | LOW |
| app/api/main.py:679, 1012 | `active_sub.record_ids or []` | None record_ids on subgroup | Follow-up treated as fresh query | no | LOW |
| app/api/main.py:108, 262, 490, 534, 926, 1155 | `.get(..., ""/"unknown")` on payload/user dicts | Missing JWT claims/fields | Role "" → level 0 (deny-safe); username "unknown" in logs | n/a (safe direction) | LOW |
| app/api/auth_service.py:89-92 | expired/invalid token → None/continue | Bad token | 401 (correct) | n/a | LOW |
| app/api/auth_deps.py:22-26 | `ROLE_HIERARCHY.get(..., 0)` | Unknown role | Access denied (safe) | n/a | LOW |
| app/api/auth_routes.py:48, 191-194 | HTTPS env "" default; UNIQUE → 400 else re-raise | Missing env; dup username | Cookie not secure in dev; 400 surfaced | partial | LOW |
| app/api/metadata.py:184-196, 253-265, 307-319, 368-380, 429-441, 683-697, 760-762, 797-799, 843-845 | typed `except` → HTTPException 503/500 | DB/handler failures | Error surfaced to client | yes (HTTP error) | LOW |
| app/api/metadata.py:779-780, 861-862 | `except (ValueError, IndexError): pass` on cluster index | Non-numeric cluster ref | Falls through to explicit "not found" response listing available IDs | yes (response) | LOW |
| app/api/metadata.py:929-931 | `except Exception:` → error text in chat response | Grounding retrieval failure | Error message shown in agent chat | yes (in response) | LOW |
| app/api/metadata_corrections.py:196-198, 405-407 | → HTTPException 500 | Handler failure | Surfaced | yes | LOW |
| app/api/metadata_corrections.py:261-262, 268-272 | `continue` on malformed log lines; `.get(..., "")` display defaults | Corrupt review-log entries | Entries silently missing from corrections list | no | LOW |
| app/api/metadata_publishers.py:174-176, 235-237, 271-273, 319-321, 374-376, 425-427 | → HTTPException (UNIQUE → 4xx) | DB failures | Surfaced | yes | LOW |
| app/api/metadata_enrichment.py:295-296, 336-337 | `except (JSONDecodeError, TypeError): pass` | Corrupt enrichment JSON | Item shown without parsed fields | no | LOW |
| app/api/diagnostics.py:128-148, 323-325, 382-384 | → HTTPException 500 | Run/gold-set load failure | Surfaced | yes | LOW |
| app/api/diagnostics.py:281-282 | `except (JSONDecodeError, TypeError): issue_tags = []` | Corrupt issue_tags JSON | Tags missing in diagnostics UI | no | LOW |
| app/api/diagnostics.py:431-437 | failure counter + per-query error result | Re-run failure per query | Counted and shown | yes (in results) | LOW |
| app/api/diagnostics.py:320-321, 343-344, 388-404 | `.get(..., ""/[])` on gold-set JSON | Missing keys in gold file | Empty expected-sets → checks trivially pass/fail oddly | no | LOW |
| app/api/network.py:84-87 | `except ImportError: return None` | primo util missing | No catalog deep-link on node | no | LOW |
| app/api/network.py:180-181, 717-718, 1079-1081 | `except (JSONDecodeError, TypeError):` → `occupations = []`/pass | Corrupt occupations JSON | Node shown without occupations | no | LOW |
| app/api/compare.py:79-86 | `except Exception:` → ComparisonResult with error + logger.exception | Pipeline failure per config | Error visible in comparison output | yes | LOW |
| app/api/feedback_routes.py:107-111 | typed except → info/warning, sync deferred | GitHub sync disabled/failed | Report saved locally; sync retried later | yes | LOW |
| app/api/feedback_routes.py:74, 82, 119 | `.get("messages", [])`, `or ''`, `or "unknown"` | Missing payload fields | Feedback report less complete | no | LOW |

## Top HIGH risks

### 1. Agent alias expansion silently disabled — scripts/query/db_adapter.py:52-53
The `_agent_alias_tables_exist` helper wraps a `sqlite_master` count in `except Exception: _agent_alias_tables_present = False`, and the result is cached in a module-level global for the life of the process (db_adapter.py:23, 39-40). Any transient failure — a locked database, a connection passed in a bad state, an interrupted read — is interpreted as "the alias tables do not exist", which removes the alias-resolution `EXISTS` sub-query from every subsequent AGENT_NORM filter (db_adapter.py:385-410). The CandidateSet shrinks: cross-script (Hebrew↔Latin) and variant-name matches vanish, with zero log output and no marker in the evidence. This directly violates the project's primary success criterion (deterministic, correct CandidateSet with evidence) because two runs of the same query can return different result sets depending on a swallowed exception. Fix shape: catch only `sqlite3.Error`, log at warning, and do not cache a False derived from an exception.

### 2. Whole-file MARC parse failure proceeds with empty data — scripts/marc/parse.py:769-771
`parse_xml_to_array` failure is caught broadly, printed to stdout, and replaced with `records = []`. The function then proceeds to write an empty canonical JSONL (parse.py:871-876) and an ExtractionReport whose totals are simply zero. CLAUDE.md's hard rule is explicit: "On MARC parse failure: log the error to data/runs/, surface it clearly, and stop — do not proceed with partial data." This path neither logs to data/runs/ nor stops; a corrupt export run inside a longer pipeline (e.g., /marc-ingest --yolo) could replace a populated canonical file with an empty one, and downstream phases would dutifully build an empty database. The stdout print is the only trace. Fix shape: raise (or write a run-error artifact and exit non-zero) instead of continuing.

### 3. Fabricated confidence score 0.85 — scripts/chat/narrator.py:269-271
When post-streaming meta extraction fails, the narrator returns a hard-coded confidence of 0.85 and logs only at debug level. The Answer Contract requires confidence scores to be real, grounded values ("If uncertain: store null/range + explicit reason; never invent data"). Here a failure of the measurement step is converted into a healthy-looking measurement — users and any downstream quality gates see 0.85 regardless of actual response quality, and a systematic meta-extraction outage (bad model name, schema drift) would be invisible: every streamed answer would report 0.85. Fix shape: return None/omit confidence with an explicit "meta_extraction_failed" reason, and log at warning.

### 4. Correction apply failure indistinguishable from "no rows matched" — scripts/metadata/feedback_loop.py:394-395
`_renormalize_records` performs the UPDATE that propagates an approved curator correction into the M3 database; its `except Exception: return 0` makes a locked database, a schema mismatch, or any SQL error look exactly like "the correction matched zero records". Nothing is logged. A curator (or the feedback-loop agent) sees 0 updated rows and may conclude the raw value no longer exists, while the low-confidence normalization the correction was meant to fix remains live in query results. Because corrections are user-approved actions with an expectation of durable effect (see project memory: data fixes shown for approval), silently dropping them undermines the whole metadata-workbench loop. Fix shape: log the exception with field/raw_value context and return a distinct error signal (raise or `None`) instead of 0.

### 5. Concept bridge silently disabled by missing/odd file — scripts/query/concept_bridge.py:35-45
`load_concept_map` returns `{}` when the map file is missing, and `raw.get("concepts", [])` returns `{}`-equivalent when the top-level key is absent or misspelled. The missing-file case is documented as intentional ("bridge disabled, not an error"), but there is no logging in either case, so an accidental rename, a deploy that omits the data file, or a hand-edit that nests `concepts` under another key all silently turn off concept expansion. Queries that rely on bridge expansions (user-vocabulary → catalog-vocabulary) return smaller CandidateSets with no evidence that expansion was skipped — a silent recall change that is invisible in the QueryPlan debug output. Fix shape: log one info line on "bridge disabled (file missing)" and a warning when the file exists but yields zero concepts.

## Counts per risk class

| Risk | Table rows | Distinct fallback sites (cited lines/ranges) |
|---|---|---|
| HIGH | 5 | 5 |
| MEDIUM | 23 | 37 |
| LOW | 79 | ~160 |
| FIXED (calibration, #43/#53 — listed in header, not table) | 2 | 2 |
| **Total table rows** | **107** | |

Notes:
- "Distinct fallback sites" counts each cited line/range; rows group identical patterns within one file.
- LOW includes a large class of *correct* patterns (typed except → HTTPException, error-in-payload results, counted skips) listed for completeness so the sweep is auditable; the genuinely silent LOW items are the `pass`/`= []` JSON-decode swallows on enrichment-derived fields.
- Read-only sweep; no code, DB, or git state modified.

SWEEP-COMPLETE
