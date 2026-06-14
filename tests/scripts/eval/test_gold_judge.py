from scripts.eval.judge import NarratorGoldJudgment, GoldScore, parse_gold_judgment, build_gold_judge_prompt


def _judgment(**over):
    base = dict(
        grounding=3,
        coverage=3,
        evidence_fidelity=3,
        scholarly_quality=3,
        scope_handling=3,
        fabrication_detected=False,
        fabricated_claims=[],
        rationale="ok",
    )
    base.update(over)
    return NarratorGoldJudgment(**base)


def test_composite_weights_sum_to_one():
    s = GoldScore.from_judgment(_judgment())
    assert abs(s.composite - 3.0) < 1e-9  # all 3s -> 3.0


def test_composite_weighting():
    s = GoldScore.from_judgment(
        _judgment(grounding=3, coverage=0, evidence_fidelity=0, scholarly_quality=0, scope_handling=0)
    )
    assert abs(s.composite - (3 * 0.40)) < 1e-9


def test_fabrication_hard_caps_score():
    s = GoldScore.from_judgment(_judgment(fabrication_detected=True, fabricated_claims=["invented title X"]))
    assert s.composite <= 1.0


def test_parse_gold_judgment_from_json():
    raw = _judgment(coverage=2).model_dump_json()
    s = parse_gold_judgment(raw)
    assert s.coverage == 2 and not s.fabrication_detected


def test_judge_prompt_includes_all_parts():
    system, user = build_gold_judge_prompt(
        query="books in Venice",
        bounded_grounding="TOTAL_RECORDS: 3",
        gold_text="GOLD NARRATIVE",
        candidate_text="CANDIDATE NARRATIVE",
    )
    assert "books in Venice" in user
    assert "TOTAL_RECORDS: 3" in user
    assert "GOLD NARRATIVE" in user
    assert "CANDIDATE NARRATIVE" in user
    assert "fabricat" in system.lower()
    assert "0" in system and "3" in system  # 0-3 scale described
