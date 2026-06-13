"""Tests for the diagnostic-suite evidence audit (issue #59 Defect B).

``RecordSet.filters_applied`` is polymorphic: retrieve steps store real
filter dicts (carrying a ``field`` key), while sample steps store
``{"strategy", "n"}``. The evidence audit reconstructs ``Filter`` objects
from these entries, so it must skip the sample-shaped entries rather than
crash when it encounters one.
"""

from scripts.eval.run_diagnostic_suite import _evidence_pass


class TestEvidencePassPolymorphicFilters:
    def test_sample_shaped_entry_does_not_crash(self):
        """A sample step's filters_applied ({strategy, n}) must not raise.

        With no field-bearing entries to audit, the pass reports cleanly
        rather than raising a Filter reconstruction error.
        """
        result = _evidence_pass([{"strategy": "diverse", "n": 10}], "any query")

        assert isinstance(result, dict)
        # Must not surface a Filter-reconstruction crash; the entry is skipped.
        assert "filter reconstruction failed" not in result.get("error", "")

    def test_empty_filters_applied_does_not_crash(self):
        result = _evidence_pass([], "any query")

        assert isinstance(result, dict)
        assert "filter reconstruction failed" not in result.get("error", "")
