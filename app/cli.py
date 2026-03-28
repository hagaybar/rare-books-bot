"""CLI for rare-books-bot.

Clean CLI with only MARC-specific commands.
All RAG-specific commands have been removed.
"""
import sys
import pathlib

# Ensure the root directory (where pyproject.toml lives) is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import typer
from pathlib import Path

app = typer.Typer()


@app.command()
def parse_marc(
    input_file: Path = typer.Argument(
        ...,
        help="Path to MARC XML file to parse"
    ),
    output_file: Path = typer.Option(
        None,
        "--output", "-o",
        help="Path to output JSONL file (default: data/canonical/records.jsonl)"
    ),
    report_file: Path = typer.Option(
        None,
        "--report", "-r",
        help="Path to extraction report JSON file (default: data/canonical/extraction_report.json)"
    ),
):
    """
    Parse MARC XML file and output canonical JSONL records.

    This implements M1: MARC XML → Canonical JSONL
    """
    from scripts.marc.parse import parse_marc_xml_file

    # Set defaults if not provided
    if output_file is None:
        output_file = Path("data/canonical/records.jsonl")
    if report_file is None:
        report_file = Path("data/canonical/extraction_report.json")

    typer.echo(f"Parsing MARC XML file: {input_file}")

    if not input_file.exists():
        typer.echo(f"Error: Input file does not exist: {input_file}")
        raise typer.Exit(code=1)

    # Run the parser
    report = parse_marc_xml_file(
        marc_xml_path=input_file,
        output_path=output_file,
        report_path=report_file
    )

    # Print summary
    typer.echo("\n✅ Parsing complete!")
    typer.echo("\nExtraction Report:")
    typer.echo(f"  Source file: {report.source_file}")
    typer.echo(f"  Total records: {report.total_records}")
    typer.echo(f"  Successful: {report.successful_extractions}")
    typer.echo(f"  Failed: {report.failed_extractions}")
    typer.echo("\nField Coverage:")
    typer.echo(f"  With title: {report.records_with_title}")
    typer.echo(f"  With imprints: {report.records_with_imprints}")
    typer.echo(f"  With languages (041$a): {report.records_with_languages}")
    typer.echo(f"  With language_fixed (008): {report.records_with_language_fixed}")
    typer.echo(f"  With subjects: {report.records_with_subjects}")
    typer.echo(f"  With agents: {report.records_with_agents}")
    typer.echo(f"  With notes: {report.records_with_notes}")
    typer.echo(f"\nOutput: {output_file}")
    typer.echo(f"Report: {report_file}")


@app.command()
def chat_init(
    db_path: Path = typer.Option(
        Path("data/chat/sessions.db"),
        "--db",
        help="Path to session database"
    ),
    user_id: str = typer.Option(None, "--user-id", help="Optional user ID")
):
    """
    Initialize new chat session.

    Creates a new session and prints session_id for use in subsequent queries.
    """
    from scripts.chat.session_store import SessionStore

    store = SessionStore(db_path)
    session = store.create_session(user_id=user_id)

    typer.echo(f"Created session: {session.session_id}")
    typer.echo(f"User: {session.user_id or 'anonymous'}")
    typer.echo(f"Database: {db_path}")

    store.close()


@app.command()
def chat_history(
    session_id: str = typer.Argument(..., help="Session ID"),
    db_path: Path = typer.Option(
        Path("data/chat/sessions.db"),
        "--db",
        help="Path to session database"
    )
):
    """View conversation history for a session."""
    from scripts.chat.session_store import SessionStore

    store = SessionStore(db_path)
    session = store.get_session(session_id)

    if not session:
        typer.echo(f"Session {session_id} not found", err=True)
        raise typer.Exit(1)

    typer.echo(f"Session: {session.session_id}")
    typer.echo(f"User: {session.user_id or 'anonymous'}")
    typer.echo(f"Messages: {len(session.messages)}")
    typer.echo(f"Created: {session.created_at}")
    typer.echo(f"Updated: {session.updated_at}")
    typer.echo("\n--- Messages ---\n")

    for i, msg in enumerate(session.messages, 1):
        typer.echo(f"{i}. [{msg.role}] {msg.content}")
        if msg.query_plan:
            typer.echo(f"   QueryPlan: {len(msg.query_plan.filters)} filters")
        if msg.candidate_set:
            typer.echo(f"   Results: {msg.candidate_set.total_count} candidates")
        typer.echo(f"   Time: {msg.timestamp}")
        typer.echo()

    store.close()


@app.command()
def chat_cleanup(
    db_path: Path = typer.Option(
        Path("data/chat/sessions.db"),
        "--db",
        help="Path to session database"
    ),
    max_age_hours: int = typer.Option(24, "--max-age-hours", help="Expire sessions older than this")
):
    """Expire old sessions."""
    from scripts.chat.session_store import SessionStore

    store = SessionStore(db_path)
    count = store.expire_old_sessions(max_age_hours=max_age_hours)

    typer.echo(f"Expired {count} sessions older than {max_age_hours} hours")

    store.close()


@app.command()
def query(
    query_text: str = typer.Argument(
        ...,
        help="Natural language query (e.g., 'books by Oxford between 1500 and 1599')"
    ),
    db: Path = typer.Option(
        Path("data/index/bibliographic.db"),
        "--db",
        help="Path to SQLite database"
    ),
    out: Path = typer.Option(
        None,
        "--out",
        help="Output directory (default: data/runs/query_YYYYMMDD_HHMMSS/)"
    ),
    limit: int = typer.Option(
        None,
        "--limit",
        help="Limit number of results"
    ),
    session_id: str = typer.Option(
        None,
        "--session-id",
        help="Optional session ID to save query to session history"
    ),
    session_db_path: Path = typer.Option(
        Path("data/chat/sessions.db"),
        "--session-db",
        help="Path to session database"
    ),
):
    """
    Execute bibliographic query (M4).

    Compiles natural language query to QueryPlan, executes against database,
    and returns CandidateSet with evidence.

    If --session-id is provided, saves query and results to session history.
    """
    from datetime import datetime
    from scripts.query import QueryService, QueryOptions, QueryCompilationError
    from scripts.query.compile import write_plan_to_file
    from scripts.query.execute import write_sql_to_file, write_candidates_to_file

    # Validate database exists
    if not db.exists():
        typer.echo(f"Error: Database not found: {db}")
        typer.echo("\nHint: Have you run M3 indexing yet?")
        typer.echo(
            "  python -m scripts.marc.m3_index data/m2/records_m1m2.jsonl"
            " data/index/bibliographic.db scripts/marc/m3_schema.sql"
        )
        raise typer.Exit(code=1)

    # Generate output directory if not provided
    if out is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(f"data/runs/query_{timestamp}")

    # Create output directory
    out.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Query: {query_text}")
    typer.echo(f"Database: {db}")
    typer.echo(f"Output: {out}")
    typer.echo()

    # Execute query via unified QueryService
    typer.echo("Executing query via QueryService...")
    try:
        service = QueryService(db)
        options = QueryOptions(
            compute_facets=False,
            include_warnings=True,
            limit=limit,
        )
        result = service.execute(query_text, options=options)

        # Write outputs to files
        plan_path = out / "plan.json"
        write_plan_to_file(result.query_plan, plan_path)
        write_sql_to_file(result.sql, out / "sql.txt")
        write_candidates_to_file(result.candidate_set, out / "candidates.json")

        typer.echo(f"  ✓ Plan generated: {len(result.query_plan.filters)} filters")
        if result.query_plan.debug and "patterns_matched" in result.query_plan.debug:
            typer.echo(f"  ✓ Patterns matched: {', '.join(result.query_plan.debug['patterns_matched'])}")
        typer.echo(f"  ✓ Query executed in {result.execution_time_ms:.1f}ms")
        typer.echo("  ✓ SQL written to: sql.txt")
        typer.echo("  ✓ Results written to: candidates.json")

        # Show warnings if any
        if result.warnings:
            typer.echo("\n⚠ Warnings:")
            for warning in result.warnings:
                typer.echo(f"  - [{warning.code}] {warning.message}")

    except QueryCompilationError as e:
        # LLM compilation failure - display helpful error message
        typer.echo("  ✗ Query compilation failed\n")
        typer.echo(str(e))
        raise typer.Exit(code=1)
    except Exception as e:
        # Unexpected error
        typer.echo(f"  ✗ Error executing query: {e}")
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)

    # Print summary
    candidate_set = result.candidate_set
    typer.echo(f"\n{'='*60}")
    typer.echo("Query Results Summary")
    typer.echo(f"{'='*60}")
    typer.echo(f"Query: {query_text}")
    typer.echo(f"Candidates found: {candidate_set.total_count}")
    typer.echo(f"Plan hash: {candidate_set.plan_hash[:16]}...")
    typer.echo(f"\nOutput directory: {out}")
    typer.echo("  - plan.json     (QueryPlan)")
    typer.echo("  - sql.txt       (Executed SQL)")
    typer.echo("  - candidates.json (CandidateSet with evidence)")
    typer.echo(f"{'='*60}")

    # Show sample of results if any
    if candidate_set.candidates:
        typer.echo("\nSample results (showing first 3):")
        for i, candidate in enumerate(candidate_set.candidates[:3], 1):
            typer.echo(f"\n{i}. Record ID: {candidate.record_id}")
            typer.echo(f"   Match: {candidate.match_rationale}")
            typer.echo(f"   Evidence fields: {len(candidate.evidence)}")
    else:
        typer.echo("\n⚠ No matching records found.")
        typer.echo("Hint: Try a different query or check if your database has indexed records.")

    # Save to session if session_id provided
    if session_id:
        from scripts.chat.session_store import SessionStore
        from scripts.chat.models import Message

        try:
            store = SessionStore(session_db_path)

            # Add user message with query plan
            user_msg = Message(
                role="user",
                content=query_text,
                query_plan=result.query_plan
            )
            store.add_message(session_id, user_msg)

            # Add assistant response with results
            response_text = f"Found {candidate_set.total_count} books matching your query"
            assistant_msg = Message(
                role="assistant",
                content=response_text,
                candidate_set=candidate_set
            )
            store.add_message(session_id, assistant_msg)

            typer.echo(f"\n✓ Saved to session {session_id}")
            store.close()
        except ValueError as e:
            typer.echo(f"\n⚠ Warning: Could not save to session: {e}", err=True)
        except Exception as e:
            typer.echo(f"\n⚠ Warning: Unexpected error saving to session: {e}", err=True)


@app.command()
def regression(
    gold: Path = typer.Option(
        ...,
        "--gold",
        help="Path to gold.json"
    ),
    db: Path = typer.Option(
        ...,
        "--db",
        help="Path to bibliographic.db"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show detailed output"
    ),
    log_file: Path = typer.Option(
        None,
        "--log-file",
        help="Write detailed results to log file"
    ),
):
    """
    Run regression tests from QA gold set.

    Executes all queries in the gold set and validates that:
    - All expected_includes are present in results
    - None of expected_excludes are present in results

    Exit code 0 = all tests passed, exit code 1 = one or more tests failed.
    """
    import json as json_mod
    from datetime import datetime
    from scripts.query.compile import compile_query
    from scripts.query.execute import execute_plan

    # Validate inputs
    if not gold.exists():
        typer.echo(f"Error: Gold set not found: {gold}", err=True)
        raise typer.Exit(code=1)
    if not db.exists():
        typer.echo(f"Error: Database not found: {db}", err=True)
        raise typer.Exit(code=1)

    # Load gold set
    try:
        gold_data = json_mod.loads(gold.read_text())
        queries = gold_data['queries']
    except Exception as e:
        typer.echo(f"Error loading gold set: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Running regression on {len(queries)} queries...")
    typer.echo(f"Gold set: {gold}")
    typer.echo(f"Database: {db}")
    typer.echo()

    passed = 0
    failed = 0
    errors = 0
    results = []

    for idx, query_spec in enumerate(queries, 1):
        query_text = query_spec['query_text']
        expected_includes = set(query_spec['expected_includes'])
        expected_excludes = set(query_spec['expected_excludes'])

        if verbose:
            typer.echo(f"[{idx}/{len(queries)}] Running: {query_text}")

        try:
            plan = compile_query(query_text)
            result = execute_plan(plan, db)
            actual_ids = {c.record_id for c in result.candidates}

            missing = expected_includes - actual_ids
            unexpected = expected_excludes & actual_ids

            if missing or unexpected:
                failed += 1
                status_str = "FAIL"
                typer.echo(f"FAIL: {query_text}")
                if missing:
                    typer.echo(f"   Missing {len(missing)} expected records:")
                    for record_id in list(missing)[:5]:
                        typer.echo(f"     - {record_id}")
                    if len(missing) > 5:
                        typer.echo(f"     ... and {len(missing) - 5} more")
                if unexpected:
                    typer.echo(f"   Found {len(unexpected)} unexpected records:")
                    for record_id in list(unexpected)[:5]:
                        typer.echo(f"     - {record_id}")
                    if len(unexpected) > 5:
                        typer.echo(f"     ... and {len(unexpected) - 5} more")
            else:
                passed += 1
                status_str = "PASS"
                if verbose:
                    typer.echo(f"PASS: {query_text}")

            results.append({
                'query': query_text,
                'status': status_str,
                'expected_includes': list(expected_includes),
                'expected_excludes': list(expected_excludes),
                'actual_results': list(actual_ids),
                'missing': list(missing),
                'unexpected': list(unexpected)
            })

        except Exception as e:
            errors += 1
            typer.echo(f"ERROR: {query_text}")
            typer.echo(f"   {e}")
            results.append({
                'query': query_text,
                'status': "ERROR",
                'error': str(e)
            })

    typer.echo()
    typer.echo("=" * 60)
    typer.echo("Regression Test Results")
    typer.echo("=" * 60)
    typer.echo(f"Total queries: {len(queries)}")
    typer.echo(f"Passed: {passed}")
    typer.echo(f"Failed: {failed}")
    typer.echo(f"Errors: {errors}")
    typer.echo("=" * 60)

    if log_file:
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'gold_set': str(gold),
            'database': str(db),
            'total': len(queries),
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'results': results
        }
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(json_mod.dumps(log_data, indent=2))
        typer.echo(f"\nDetailed results written to: {log_file}")

    if failed > 0 or errors > 0:
        typer.echo(f"\nRegression failed: {failed + errors} queries did not pass", err=True)
        raise typer.Exit(code=1)
    else:
        typer.echo(f"\nAll {passed} queries passed!")
        raise typer.Exit(code=0)


@app.command()
def seed_agent_authorities(
    db: Path = typer.Option(
        Path("data/index/bibliographic.db"),
        "--db",
        help="Path to bibliographic SQLite database",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be seeded without writing to the database",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show detailed output",
    ),
):
    """
    Seed agent authority records from enrichment data.

    Groups agents by authority_uri, creates authorities with primary aliases,
    adds enrichment labels and Hebrew labels, and generates word-reorder variants.
    Idempotent (safe to run multiple times).
    """
    from scripts.metadata.agent_authority import AgentAuthorityStore
    from scripts.metadata.seed_agent_authorities import seed_all
    import sqlite3

    if not db.exists():
        typer.echo(f"Error: Database not found: {db}", err=True)
        raise typer.Exit(code=1)

    if verbose:
        typer.echo(f"Database: {db}")
        typer.echo(f"Dry run: {dry_run}")
        typer.echo()

    # Open connection
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Ensure schema exists
    store = AgentAuthorityStore(db)
    store.init_schema(conn=conn)

    if dry_run:
        # Use a savepoint so we can roll back
        conn.execute("SAVEPOINT dry_run")
        try:
            stats = seed_all(conn)
            typer.echo("Dry run results (no changes written):")
            for key, value in stats.items():
                if key != "aliases_by_type":
                    typer.echo(f"  {key}: {value}")
            if "aliases_by_type" in stats:
                typer.echo("  Alias breakdown:")
                for alias_type, count in stats["aliases_by_type"].items():
                    typer.echo(f"    {alias_type}: {count}")
        finally:
            conn.execute("ROLLBACK TO dry_run")
            conn.close()
    else:
        stats = seed_all(conn)
        conn.close()

        typer.echo("Agent authority seeding complete!")
        typer.echo()
        for key, value in stats.items():
            if key != "aliases_by_type":
                typer.echo(f"  {key}: {value}")
        if "aliases_by_type" in stats:
            typer.echo("  Alias breakdown:")
            for alias_type, count in stats["aliases_by_type"].items():
                typer.echo(f"    {alias_type}: {count}")


@app.command("create-user")
def create_user_cmd(
    username: str = typer.Argument(..., help="Username"),
    password: str = typer.Argument(..., help="Password (min 8 chars)"),
    role: str = typer.Option("admin", help="Role: admin, full, limited, guest"),
):
    """Create a new user (for bootstrapping the first admin)."""
    from app.api.auth_db import init_auth_db
    from app.api.auth_service import create_user as _create_user

    init_auth_db()
    try:
        user_id = _create_user(username, password, role)
        typer.echo(f"Created user '{username}' (id={user_id}, role={role})")
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)


@app.command("purge-audit")
def purge_audit(
    days: int = typer.Option(90, help="Delete audit entries older than N days"),
):
    """Purge old audit log entries."""
    from app.api.auth_db import purge_audit_log

    count = purge_audit_log(days)
    print(f"Purged {count} audit log entries older than {days} days")


if __name__ == "__main__":
    app()
