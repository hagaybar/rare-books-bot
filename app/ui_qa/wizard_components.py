"""Wizard components for guided QA sessions."""
import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
import streamlit as st
from app.ui_qa.config import QA_DB_PATH


def render_stepper(current_step: int, total_steps: int, step_names: List[str]):
    """Render visual stepper indicator."""
    # Progress bar
    progress_pct = (current_step - 1) / (total_steps - 1) if total_steps > 1 else 0
    st.progress(progress_pct)

    # Step caption
    step_name = step_names[current_step - 1] if current_step <= len(step_names) else "Unknown"
    st.caption(f"**Step {current_step}/{total_steps}:** {step_name}")


def get_step_instruction(step_number: int, session_type: str) -> str:
    """Get instruction text for a step."""
    instructions = {
        ('SMOKE', 1): "Choose a canonical query or type your own. Set the result limit.",
        ('SMOKE', 2): "Run the query and verify the plan matches your intent.",
        ('SMOKE', 3): "Label at least 10 candidates as TP (correct) or FP (incorrect). Override available if query returns fewer results.",
        ('SMOKE', 4): "Spot-check 3 random candidates to verify evidence quality.",
        ('SMOKE', 5): "Review session summary and assign a verdict.",

        ('RECALL', 1): "Choose a canonical query or type your own. Set the result limit.",
        ('RECALL', 2): "Run the query and verify the plan matches your intent.",
        ('RECALL', 3): "Label at least 5 candidates as TP or FP. Override available if query returns fewer results.",
        ('RECALL', 4): "Search for likely matches that didn't appear and mark them as FN.",
        ('RECALL', 5): "Review session summary (including FN count) and assign a verdict.",
    }
    return instructions.get((session_type, step_number), "")


def check_step_1_gating(session: Dict) -> Tuple[bool, str]:
    """Check if step 1 requirements met (query_text non-empty)."""
    import json
    config = json.loads(session['session_config_json'])
    query_text = config.get('query_text', '')

    if query_text.strip():
        return True, ""
    else:
        return False, "Please enter a query or select a canonical query."


def check_step_2_gating(session: Dict) -> Tuple[bool, str]:
    """Check if step 2 requirements met (query executed, plan checked)."""
    # Check if query_id exists
    if not session.get('query_id'):
        return False, "Please run the query first."

    # Check if query status is OK
    conn = sqlite3.connect(str(QA_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT status FROM qa_queries WHERE id = ?", (session['query_id'],))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False, "Query not found in database."

    if row['status'] != 'OK':
        return False, "Query execution failed. Please fix and re-run."

    # Check if plan_matches checkbox is checked (stored in session state)
    if not st.session_state.get('plan_matches_intent', False):
        return False, "Please verify the plan matches your intent."

    return True, ""


def check_step_3_gating(session_id: int, threshold: int) -> Tuple[bool, str]:
    """Check if step 3 requirements met (min_labels reached)."""
    # Check if override is enabled
    if st.session_state.get('step3_override', False):
        return True, ""

    conn = sqlite3.connect(str(QA_DB_PATH))
    cursor = conn.execute("""
        SELECT COUNT(*) as labeled_count
        FROM qa_candidate_labels
        WHERE session_id = ? AND label IN ('TP', 'FP')
    """, (session_id,))
    count = cursor.fetchone()[0]
    conn.close()

    if count >= threshold:
        return True, ""
    else:
        return False, f"Please label at least {threshold} candidates (currently {count} labeled)."


def check_step_4_smoke_gating(session_id: int) -> Tuple[bool, str]:
    """Check if SMOKE step 4 requirements met (evidence checked or skipped)."""
    # Check if all evidence checkboxes are checked
    evidence_checked_1 = st.session_state.get('evidence_check_1', False)
    evidence_checked_2 = st.session_state.get('evidence_check_2', False)
    evidence_checked_3 = st.session_state.get('evidence_check_3', False)

    all_checked = evidence_checked_1 and evidence_checked_2 and evidence_checked_3

    # Or check if skip reason provided
    skip_reason = st.session_state.get('evidence_skip_reason', '')

    if all_checked or skip_reason.strip():
        return True, ""
    else:
        return False, "Please check all 3 evidence items or provide a skip reason."


def check_step_4_recall_gating(session_id: int) -> Tuple[bool, str]:
    """Check if RECALL step 4 requirements met (at least 1 FN or no_missing)."""
    # Check FN count
    conn = sqlite3.connect(str(QA_DB_PATH))
    cursor = conn.execute("""
        SELECT COUNT(*) as fn_count
        FROM qa_candidate_labels
        WHERE session_id = ? AND label = 'FN'
    """, (session_id,))
    fn_count = cursor.fetchone()[0]
    conn.close()

    # Or check if "no missing found" is checked
    no_missing = st.session_state.get('no_missing_found', False)

    if fn_count >= 1 or no_missing:
        return True, ""
    else:
        return False, "Please mark at least 1 record as FN or check 'No missing found'."


def bulk_label(session_id: int, query_id: int, candidates: List[Any], label: str) -> int:
    """Bulk label all candidates. Returns count."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    now = datetime.now().isoformat()

    count = 0
    for candidate in candidates:
        conn.execute("""
            INSERT INTO qa_candidate_labels (
                session_id, query_id, record_id, label, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(query_id, record_id) DO UPDATE SET
                label = excluded.label,
                session_id = excluded.session_id,
                updated_at = excluded.updated_at
        """, (session_id, query_id, candidate.record_id, label, now, now))
        count += 1

    conn.commit()
    conn.close()
    return count


def clear_labels(session_id: int, query_id: int) -> int:
    """Clear all labels for a query in a session. Returns count."""
    conn = sqlite3.connect(str(QA_DB_PATH))

    cursor = conn.execute("""
        DELETE FROM qa_candidate_labels
        WHERE session_id = ? AND query_id = ?
    """, (session_id, query_id))

    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def render_bulk_label_actions(session_id: int, query_id: int, candidates: List[Any]):
    """Render bulk labeling buttons with save confirmations."""
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("✅ Mark All as TP", use_container_width=True):
            count = bulk_label(session_id, query_id, candidates, 'TP')
            timestamp = datetime.now().strftime("%H:%M:%S")
            st.success(f"Saved {count} labels (TP) at {timestamp}")
            st.rerun()

    with col2:
        if st.button("❌ Mark All as FP", use_container_width=True):
            count = bulk_label(session_id, query_id, candidates, 'FP')
            timestamp = datetime.now().strftime("%H:%M:%S")
            st.success(f"Saved {count} labels (FP) at {timestamp}")
            st.rerun()

    with col3:
        if st.button("🗑️ Clear All Labels", use_container_width=True):
            count = clear_labels(session_id, query_id)
            timestamp = datetime.now().strftime("%H:%M:%S")
            st.info(f"Cleared {count} labels at {timestamp}")
            st.rerun()


def get_label_counts_for_session(session_id: int, query_id: int) -> Dict[str, int]:
    """Get label counts for a session query."""
    conn = sqlite3.connect(str(QA_DB_PATH))
    cursor = conn.execute("""
        SELECT label, COUNT(*) as count
        FROM qa_candidate_labels
        WHERE session_id = ? AND query_id = ?
        GROUP BY label
    """, (session_id, query_id))

    counts = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    return {
        'TP': counts.get('TP', 0),
        'FP': counts.get('FP', 0),
        'FN': counts.get('FN', 0),
        'UNK': counts.get('UNK', 0)
    }


def compute_session_summary(session_id: int, query_id: int) -> Dict[str, Any]:
    """Compute summary statistics for a session."""
    counts = get_label_counts_for_session(session_id, query_id)

    tp_count = counts['TP']
    fp_count = counts['FP']
    fn_count = counts['FN']

    # Calculate TP rate
    tp_rate = tp_count / (tp_count + fp_count) if (tp_count + fp_count) > 0 else 0

    # Get top issue tags
    conn = sqlite3.connect(str(QA_DB_PATH))
    cursor = conn.execute("""
        SELECT issue_tags
        FROM qa_candidate_labels
        WHERE session_id = ? AND issue_tags IS NOT NULL
    """, (session_id,))

    import json
    all_tags = []
    for row in cursor.fetchall():
        try:
            tags = json.loads(row[0])
            all_tags.extend(tags)
        except:
            pass

    conn.close()

    # Count tag frequencies
    from collections import Counter
    tag_counts = Counter(all_tags)
    top_tags = [tag for tag, count in tag_counts.most_common(3)]

    return {
        'tp_count': tp_count,
        'fp_count': fp_count,
        'fn_count': fn_count,
        'tp_rate': tp_rate,
        'top_issue_tags': top_tags
    }


def render_navigation_buttons(
    session: Dict,
    session_id: int,
    current_step: int,
    total_steps: int,
    session_type: str,
    on_back=None,
    on_next=None
):
    """Render Back/Next navigation buttons with gating."""
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if current_step > 1:
            if st.button("← Back", use_container_width=True):
                if on_back:
                    on_back()
        else:
            st.button("← Back", disabled=True, use_container_width=True)

    with col3:
        # Check gating for current step
        can_proceed = False
        error_msg = ""

        if current_step == 1:
            can_proceed, error_msg = check_step_1_gating(session)
        elif current_step == 2:
            can_proceed, error_msg = check_step_2_gating(session)
        elif current_step == 3:
            import json
            config = json.loads(session['session_config_json'])
            threshold = config.get('thresholds', {}).get('min_labels', 10)
            can_proceed, error_msg = check_step_3_gating(session_id, threshold)
        elif current_step == 4:
            if session_type == 'SMOKE':
                can_proceed, error_msg = check_step_4_smoke_gating(session_id)
            else:  # RECALL
                can_proceed, error_msg = check_step_4_recall_gating(session_id)
        elif current_step == 5:
            # Step 5 is summary, no gating needed for Next (becomes Finish)
            can_proceed = True

        if current_step < total_steps:
            if st.button("Next →", disabled=not can_proceed, use_container_width=True, type="primary"):
                if on_next:
                    on_next()

        # Show error message if gating fails
        if not can_proceed and error_msg:
            st.error(error_msg)
