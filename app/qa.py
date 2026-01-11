"""CLI regression runner for QA gold set testing.

Run with: poetry run python -m app.qa --gold data/qa/gold.json --db data/index/bibliographic.db
"""
import sys
import pathlib

# Ensure the root directory (where pyproject.toml lives) is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import typer
import json
from pathlib import Path
from datetime import datetime
from scripts.query.compile import compile_query
from scripts.query.execute import execute_plan

app = typer.Typer()


@app.callback(invoke_without_command=True)
def regress(
    gold: Path = typer.Option(..., help="Path to gold.json"),
    db: Path = typer.Option(..., help="Path to bibliographic.db"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    log_file: Path = typer.Option(None, help="Write detailed results to log file")
):
    """Run regression tests from gold set.

    Executes all queries in the gold set and validates that:
    - All expected_includes are present in results
    - None of expected_excludes are present in results

    Exit code:
    - 0: All tests passed
    - 1: One or more tests failed
    """

    # Validate inputs
    if gold is None:
        typer.echo("❌ Error: --gold is required", err=True)
        raise typer.Exit(code=1)

    if db is None:
        typer.echo("❌ Error: --db is required", err=True)
        raise typer.Exit(code=1)

    if not gold.exists():
        typer.echo(f"❌ Error: Gold set not found: {gold}", err=True)
        raise typer.Exit(code=1)

    if not db.exists():
        typer.echo(f"❌ Error: Database not found: {db}", err=True)
        raise typer.Exit(code=1)

    # Load gold set
    try:
        gold_data = json.loads(gold.read_text())
        queries = gold_data['queries']
    except Exception as e:
        typer.echo(f"❌ Error loading gold set: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"🔍 Running regression on {len(queries)} queries...")
    typer.echo(f"📂 Gold set: {gold}")
    typer.echo(f"🗄️  Database: {db}")
    typer.echo()

    # Run queries
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
            # Run query
            plan = compile_query(query_text)
            result = execute_plan(plan, db)

            # Check results
            actual_ids = {c.record_id for c in result.candidates}

            missing = expected_includes - actual_ids
            unexpected = expected_excludes & actual_ids

            if missing or unexpected:
                # Failed
                failed += 1
                status = "FAIL"
                typer.echo(f"❌ FAIL: {query_text}", fg=typer.colors.RED)

                if missing:
                    typer.echo(f"   Missing {len(missing)} expected records:")
                    for record_id in list(missing)[:5]:  # Show first 5
                        typer.echo(f"     - {record_id}")
                    if len(missing) > 5:
                        typer.echo(f"     ... and {len(missing) - 5} more")

                if unexpected:
                    typer.echo(f"   Found {len(unexpected)} unexpected records:")
                    for record_id in list(unexpected)[:5]:  # Show first 5
                        typer.echo(f"     - {record_id}")
                    if len(unexpected) > 5:
                        typer.echo(f"     ... and {len(unexpected) - 5} more")

            else:
                # Passed
                passed += 1
                status = "PASS"
                if verbose:
                    typer.echo(f"✅ PASS: {query_text}", fg=typer.colors.GREEN)

            results.append({
                'query': query_text,
                'status': status,
                'expected_includes': list(expected_includes),
                'expected_excludes': list(expected_excludes),
                'actual_results': list(actual_ids),
                'missing': list(missing),
                'unexpected': list(unexpected)
            })

        except Exception as e:
            errors += 1
            status = "ERROR"
            typer.echo(f"💥 ERROR: {query_text}", fg=typer.colors.YELLOW)
            typer.echo(f"   {e}")

            results.append({
                'query': query_text,
                'status': status,
                'error': str(e)
            })

    # Summary
    typer.echo()
    typer.echo("=" * 60)
    typer.echo("Regression Test Results")
    typer.echo("=" * 60)
    typer.echo(f"Total queries: {len(queries)}")
    typer.echo(f"✅ Passed: {passed}")
    typer.echo(f"❌ Failed: {failed}")
    typer.echo(f"💥 Errors: {errors}")
    typer.echo("=" * 60)

    # Write log file if requested
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
        log_file.write_text(json.dumps(log_data, indent=2))
        typer.echo(f"\n📝 Detailed results written to: {log_file}")

    # Exit with appropriate code
    if failed > 0 or errors > 0:
        typer.echo(f"\n❌ Regression failed: {failed + errors} queries did not pass", err=True)
        raise typer.Exit(code=1)
    else:
        typer.echo(f"\n✅ All {passed} queries passed!")
        raise typer.Exit(code=0)


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
