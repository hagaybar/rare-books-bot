"""Test M1 upgrade with occurrence indexing and new access points.

Uses MMS 990011964120204146 as reference record to validate:
1. Occurrence indexing for repeated fields
2. Uniform title (240) extraction
3. Variant titles (246) extraction
4. Acquisition (541) extraction
5. Subject scheme and heading_lang extraction
6. Manufacturer as consistent SourcedValue pattern
"""

import json
from pathlib import Path


def test_reference_record_990011964120204146():
    """Test canonical output for reference record MMS 990011964120204146."""
    # Load records
    records_path = Path("data/canonical/records.jsonl")
    assert records_path.exists(), "Canonical records file not found"

    # Find the test record
    test_record = None
    with open(records_path, 'r', encoding='utf-8') as f:
        for line in f:
            record = json.loads(line)
            if record['source']['control_number']['value'] == "990011964120204146":
                test_record = record
                break

    assert test_record is not None, "Test record 990011964120204146 not found"

    # Validation 1: Control number
    assert test_record['source']['control_number']['value'] == "990011964120204146"

    # Validation 2: Title source
    assert test_record['title']['source'] == ["245$a"]

    # Validation 3: Uniform title
    assert test_record['uniform_title'] is not None
    assert test_record['uniform_title']['value'] == "[Office, Holy Week]"
    assert test_record['uniform_title']['source'] == ["240[0]$a"]

    # Validation 4: Variant titles
    assert len(test_record['variant_titles']) > 0
    assert test_record['variant_titles'][0]['value'] == "A complies des jours saints"
    assert test_record['variant_titles'][0]['source'] == ["246[0]$a"]

    # Validation 5: Acquisition
    assert len(test_record['acquisition']) > 0
    assert test_record['acquisition'][0]['value'] == "Newman, Dushka and Yaakov"
    assert test_record['acquisition'][0]['source'] == ["541[0]$a"]

    # Validation 6: Notes with occurrence indexing
    notes = test_record['notes']
    assert len(notes) == 5  # 4x 500 + 1x 590

    # Check occurrence indexing on 500 fields
    note_500_sources = [n['source'][0] for n in notes if n['tag'] == '500']
    assert "500[0]$a" in note_500_sources
    assert "500[1]$a" in note_500_sources
    assert "500[2]$a" in note_500_sources
    assert "500[3]$a" in note_500_sources

    # Check 590 has occurrence index too
    note_590 = [n for n in notes if n['tag'] == '590'][0]
    assert note_590['source'] == ["590[0]$a"]

    # Validation 7: Subjects with scheme and heading_lang
    subjects = test_record['subjects']
    assert len(subjects) == 2  # 610 and 650

    # Check 610 subject
    subj_610 = [s for s in subjects if s['source_tag'] == '610'][0]
    assert subj_610['scheme']['value'] == "nli"
    assert subj_610['scheme']['source'] == ["610[0]$2"]
    assert subj_610['heading_lang']['value'] == "lat"
    assert subj_610['heading_lang']['source'] == ["610[0]$9"]

    # Check occurrence indexing in sources
    assert "610[0]$a" in subj_610['source']
    assert "610[0]$v" in subj_610['source']
    assert "610[0]$x" in subj_610['source']

    # Validation 8: Subject parts as arrays for v/x/y/z
    assert isinstance(subj_610['parts']['v'], list)
    assert subj_610['parts']['v'] == ["Prayers and devotions"]
    assert isinstance(subj_610['parts']['x'], list)
    assert subj_610['parts']['x'] == ["French."]

    # Validation 9: Imprint with occurrence indexing and consistent manufacturer
    imprints = test_record['imprints']
    assert len(imprints) == 1
    imprint = imprints[0]

    # Check occurrence indexing
    assert imprint['place']['source'] == ["260[0]$a"]
    assert imprint['publisher']['source'] == ["260[0]$b"]
    assert imprint['date']['source'] == ["260[0]$c"]

    # Check manufacturer is consistent SourcedValue pattern (not bare null)
    assert imprint['manufacturer'] is not None
    assert isinstance(imprint['manufacturer'], dict)
    assert imprint['manufacturer']['value'] is None
    assert imprint['manufacturer']['source'] == []

    print("✅ All validations passed for reference record 990011964120204146")


if __name__ == "__main__":
    test_reference_record_990011964120204146()
