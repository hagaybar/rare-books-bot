"""Embed the collection's distinct subject headings -> ``subject_embeddings``.

Offline / on-ingest step for semantic subject search (#63). Collects the distinct
non-empty ``subjects.value`` (lang ``en``) and ``subjects.value_he`` (lang ``he``)
headings, embeds each with the pinned ONNX model via ``OnnxEmbedder`` (the same
encode path used at runtime — the consistency anchor), and stores L2-normalized
float32 vectors as BLOBs alongside ``dim`` and ``model_id``.

Idempotent: re-running deletes the rows for the current ``model_id`` and reinserts.
Additive: the ``subject_embeddings`` table is created with ``IF NOT EXISTS`` and no
other table is touched.

Run:
    PYTHONPATH=. poetry run python scripts/index/embed_subjects.py
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from scripts.chat.onnx_embedder import OnnxEmbedder

DEFAULT_DB = Path("data/index/bibliographic.db")
BATCH_SIZE = 64

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS subject_embeddings (
    heading_value TEXT,
    lang TEXT,
    dim INT,
    model_id TEXT,
    vector BLOB
)
"""


def collect_headings(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Return distinct non-empty (heading_value, lang) pairs.

    English headings come from ``subjects.value`` (NOT NULL but guarded for
    blanks); Hebrew headings from the nullable ``subjects.value_he``.
    """
    pairs: list[tuple[str, str]] = []
    for value, in conn.execute(
        "SELECT DISTINCT value FROM subjects "
        "WHERE value IS NOT NULL AND TRIM(value) != ''"
    ):
        pairs.append((value, "en"))
    for value, in conn.execute(
        "SELECT DISTINCT value_he FROM subjects "
        "WHERE value_he IS NOT NULL AND TRIM(value_he) != ''"
    ):
        pairs.append((value, "he"))
    return pairs


def embed_headings(
    conn: sqlite3.Connection,
    embedder: OnnxEmbedder,
    batch_size: int = BATCH_SIZE,
) -> int:
    """Embed all distinct headings and (re)write ``subject_embeddings``.

    Idempotent for the embedder's ``model_id``: deletes that model's rows first,
    then inserts fresh vectors. Returns the number of rows written.
    """
    conn.execute(CREATE_TABLE_SQL)
    model_id = embedder.model_id
    conn.execute(
        "DELETE FROM subject_embeddings WHERE model_id = ?", (model_id,)
    )

    pairs = collect_headings(conn)
    written = 0
    for start in range(0, len(pairs), batch_size):
        batch = pairs[start : start + batch_size]
        texts = [value for value, _lang in batch]
        vectors = embedder.encode_passages(texts)
        dim = int(vectors.shape[1])
        rows = [
            (
                value,
                lang,
                dim,
                model_id,
                vectors[i].astype("float32").tobytes(),
            )
            for i, (value, lang) in enumerate(batch)
        ]
        conn.executemany(
            "INSERT INTO subject_embeddings "
            "(heading_value, lang, dim, model_id, vector) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        written += len(rows)
    conn.commit()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed distinct subject headings into subject_embeddings."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB,
        help="Path to SQLite database (default: data/index/bibliographic.db)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help="Number of headings to embed per batch.",
    )
    args = parser.parse_args()

    embedder = OnnxEmbedder()
    conn = sqlite3.connect(args.db_path)
    try:
        written = embed_headings(conn, embedder, batch_size=args.batch_size)
    finally:
        conn.close()
    print(f"wrote {written} heading vectors (model_id={embedder.model_id})")


if __name__ == "__main__":
    main()
