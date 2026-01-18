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
    typer.echo(f"\n✅ Parsing complete!")
    typer.echo(f"\nExtraction Report:")
    typer.echo(f"  Source file: {report.source_file}")
    typer.echo(f"  Total records: {report.total_records}")
    typer.echo(f"  Successful: {report.successful_extractions}")
    typer.echo(f"  Failed: {report.failed_extractions}")
    typer.echo(f"\nField Coverage:")
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
    import json
    from datetime import datetime
    from scripts.query import QueryService, QueryOptions, QueryCompilationError
    from scripts.query.compile import write_plan_to_file
    from scripts.query.execute import write_sql_to_file, write_candidates_to_file

    # Validate database exists
    if not db.exists():
        typer.echo(f"Error: Database not found: {db}")
        typer.echo("\nHint: Have you run M3 indexing yet?")
        typer.echo("  python -m scripts.marc.m3_index data/m2/records_m1m2.jsonl data/index/bibliographic.db scripts/marc/m3_schema.sql")
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
        typer.echo(f"  ✓ SQL written to: sql.txt")
        typer.echo(f"  ✓ Results written to: candidates.json")

        # Show warnings if any
        if result.warnings:
            typer.echo(f"\n⚠ Warnings:")
            for warning in result.warnings:
                typer.echo(f"  - [{warning.code}] {warning.message}")

    except QueryCompilationError as e:
        # LLM compilation failure - display helpful error message
        typer.echo(f"  ✗ Query compilation failed\n")
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
    typer.echo(f"Query Results Summary")
    typer.echo(f"{'='*60}")
    typer.echo(f"Query: {query_text}")
    typer.echo(f"Candidates found: {candidate_set.total_count}")
    typer.echo(f"Plan hash: {candidate_set.plan_hash[:16]}...")
    typer.echo(f"\nOutput directory: {out}")
    typer.echo(f"  - plan.json     (QueryPlan)")
    typer.echo(f"  - sql.txt       (Executed SQL)")
    typer.echo(f"  - candidates.json (CandidateSet with evidence)")
    typer.echo(f"{'='*60}")

    # Show sample of results if any
    if candidate_set.candidates:
        typer.echo(f"\nSample results (showing first 3):")
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


if __name__ == "__main__":
    app()
