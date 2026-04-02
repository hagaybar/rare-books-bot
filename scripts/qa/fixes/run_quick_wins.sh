#!/usr/bin/env bash
# Run all 7 data quality fix scripts in order.
# Usage:
#   ./scripts/qa/fixes/run_quick_wins.sh              # apply all fixes
#   ./scripts/qa/fixes/run_quick_wins.sh --dry-run     # preview only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

EXTRA_ARGS="${*:-}"

echo "=========================================="
echo "Data Quality Quick Wins — Fix Runner"
echo "=========================================="
echo "Project root: $PROJECT_ROOT"
echo "Extra args:   ${EXTRA_ARGS:-<none>}"
echo ""

for script in \
    fix_01_role_trailing_periods.py \
    fix_02_hebrew_role_terms.py \
    fix_03_missing_relator_terms.py \
    fix_04_subject_scheme_normalize.py \
    fix_05_calendar_confusion_dates.py \
    fix_06_place_country_mismatches.py \
    fix_07_germany_place_norm.py \
; do
    echo "------------------------------------------"
    echo "Running: $script"
    echo "------------------------------------------"
    python3 "$SCRIPT_DIR/$script" $EXTRA_ARGS
    echo ""
done

echo "=========================================="
echo "All fix scripts complete."
echo "=========================================="
