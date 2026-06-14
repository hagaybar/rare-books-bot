import json
from pathlib import Path
from scripts.eval.batch_client import write_batch_jsonl, reconcile, parse_output_line


def test_write_batch_jsonl(tmp_path: Path):
    reqs = [{"custom_id": "a::m", "method": "POST", "url": "/v1/chat/completions", "body": {"model": "m"}}]
    p = write_batch_jsonl(reqs, tmp_path / "in.jsonl")
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["custom_id"] == "a::m"


def test_reconcile_flags_missing():
    reqs = [{"custom_id": "a"}, {"custom_id": "b"}]
    results = {"a": {"ok": 1}}  # b missing
    matched, missing = reconcile(reqs, results)
    assert "a" in matched and missing == ["b"]


def test_parse_output_line_extracts_body_and_custom_id():
    line = json.dumps(
        {
            "custom_id": "a::m",
            "response": {"status_code": 200, "body": {"choices": [], "usage": {}}},
            "error": None,
        }
    )
    cid, body, err = parse_output_line(line)
    assert cid == "a::m" and err is None and "choices" in body
