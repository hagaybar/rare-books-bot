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
    typer.echo(f"  Total records: {report.total_records}")
    typer.echo(f"  Successful: {report.successful_extractions}")
    typer.echo(f"  Failed: {report.failed_extractions}")
    typer.echo(f"\nField Coverage:")
    typer.echo(f"  With title: {report.records_with_title}")
    typer.echo(f"  With imprint: {report.records_with_imprint}")
    typer.echo(f"  With languages: {report.records_with_languages}")
    typer.echo(f"  With subjects: {report.records_with_subjects}")
    typer.echo(f"  With agents: {report.records_with_agents}")
    typer.echo(f"  With notes: {report.records_with_notes}")
    typer.echo(f"\nOutput: {output_file}")
    typer.echo(f"Report: {report_file}")


if __name__ == "__main__":
    app()
