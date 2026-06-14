"""Thin wrapper over the OpenAI Batch API for offline eval runs.

Pure helpers (write_batch_jsonl, reconcile, parse_output_line) are unit-tested;
the networked submit/poll/download functions take an OpenAI client so they can
be exercised with a fake in tests.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def write_batch_jsonl(requests: list[dict], path: Path) -> Path:
    """Serialize batch request dicts to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in requests:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def parse_output_line(line: str) -> tuple[str, dict | None, Any]:
    """Parse one Batch API output line -> (custom_id, response_body|None, error)."""
    obj = json.loads(line)
    cid = obj["custom_id"]
    err = obj.get("error")
    resp = obj.get("response") or {}
    body = resp.get("body") if err is None else None
    return cid, body, err


def reconcile(requests: list[dict], results: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Split requested custom_ids into matched results and missing ids."""
    matched: dict[str, Any] = {}
    missing: list[str] = []
    for r in requests:
        cid = r["custom_id"]
        if cid in results:
            matched[cid] = results[cid]
        else:
            missing.append(cid)
    return matched, missing


def submit_batch(client: Any, jsonl_path: Path, description: str) -> str:
    """Upload the JSONL and create a batch; return the batch id.

    Uploads via an explicit (filename, bytes) tuple so the Batch API always sees
    a clean ``.jsonl`` filename regardless of the on-disk relative path.
    """
    uploaded = client.files.create(
        file=(jsonl_path.name, jsonl_path.read_bytes()), purpose="batch"
    )
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={"description": description},
    )
    return batch.id


def poll_until_done(client: Any, batch_id: str, interval: float = 20.0, timeout: float = 86400.0) -> Any:
    """Poll a batch until terminal state; return the batch object."""
    waited = 0.0
    terminal = {"completed", "failed", "expired", "cancelled"}
    while True:
        batch = client.batches.retrieve(batch_id)
        if batch.status in terminal:
            return batch
        if waited >= timeout:
            raise TimeoutError(f"Batch {batch_id} not done after {timeout}s (status={batch.status})")
        time.sleep(interval)
        waited += interval


def download_results(client: Any, batch: Any) -> dict[str, dict | None]:
    """Download the output file and map custom_id -> response body (None on error)."""
    if not getattr(batch, "output_file_id", None):
        return {}
    content = client.files.content(batch.output_file_id).text
    out: dict[str, dict | None] = {}
    for line in content.splitlines():
        if not line.strip():
            continue
        cid, body, _err = parse_output_line(line)
        out[cid] = body
    return out
