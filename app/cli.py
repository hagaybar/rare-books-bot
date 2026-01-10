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
):
    """
    Execute bibliographic query (M4).

    Compiles natural language query to QueryPlan, executes against database,
    and returns CandidateSet with evidence.
    """
    from datetime import datetime
    from scripts.query.compile import compile_query, write_plan_to_file
    from scripts.query.execute import execute_plan_from_file

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

    # Step 1: Compile query to plan
    typer.echo("Step 1/2: Compiling query to plan...")
    try:
        plan = compile_query(query_text, limit=limit)
        plan_path = out / "plan.json"
        write_plan_to_file(plan, plan_path)
        typer.echo(f"  ✓ Plan generated: {len(plan.filters)} filters")
        if plan.debug and "patterns_matched" in plan.debug:
            typer.echo(f"  ✓ Patterns matched: {', '.join(plan.debug['patterns_matched'])}")
    except Exception as e:
        typer.echo(f"  ✗ Error compiling query: {e}")
        raise typer.Exit(code=1)

    # Step 2: Execute plan
    typer.echo("\nStep 2/2: Executing query...")
    try:
        candidate_set = execute_plan_from_file(plan_path, db, out)
        typer.echo(f"  ✓ Query executed successfully")
        typer.echo(f"  ✓ SQL written to: sql.txt")
        typer.echo(f"  ✓ Results written to: candidates.json")
    except Exception as e:
        typer.echo(f"  ✗ Error executing query: {e}")
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)

    # Print summary
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


if __name__ == "__main__":
    app()
