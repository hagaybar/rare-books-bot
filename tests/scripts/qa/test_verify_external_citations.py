"""Tests for the external-citation verification harness (issue #2 D10).

Cross-checks externally-claimed (title, mms_id) pairs — e.g. from a ChatGPT
answer — against bibliographic.db to flag fabricated identifiers.
"""
from pathlib import Path

import pytest

from scripts.qa.verify_external_citations import verify_claim, verify_claims

DB_PATH = Path("data/index/bibliographic.db")

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_db():
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")


def test_fabricated_id_with_real_title_is_flagged():
    # The actual ChatGPT fabrication from issue #2: real title, invented MMS ID.
    result = verify_claim(
        title="Palaestina ex monumentis veteribus illustrata",
        mms_id="9933433384704146",
        db_path=DB_PATH,
    )
    assert result["status"] == "id_fabricated_title_real"
    assert "9933749415904146" in result["real_mms_ids"]


def test_correct_pair_verifies():
    result = verify_claim(
        title="Palaestina ex monumentis veteribus illustrata",
        mms_id="9933749415904146",
        db_path=DB_PATH,
    )
    assert result["status"] == "verified"


def test_unknown_title_and_id_not_found():
    result = verify_claim(
        title="A Totally Invented Treatise of Nowhere",
        mms_id="9999999999999999",
        db_path=DB_PATH,
    )
    assert result["status"] == "not_found"


def test_verify_claims_batch_summarizes():
    report = verify_claims(
        [
            {"title": "Palaestina ex monumentis veteribus illustrata", "mms_id": "9933433384704146"},
            {"title": "A Totally Invented Treatise of Nowhere", "mms_id": "9999999999999999"},
        ],
        db_path=DB_PATH,
    )
    assert report["summary"]["total"] == 2
    assert report["summary"]["id_fabricated_title_real"] == 1
    assert report["summary"]["not_found"] == 1
