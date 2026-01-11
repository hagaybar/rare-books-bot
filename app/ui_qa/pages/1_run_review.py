"""Page 1: Run + Review - Execute queries and label candidates."""
import sys
import pathlib

# Ensure the root directory is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT))

import streamlit as st
import pandas as pd
from pathlib import Path
from scripts.query.compile import compile_query
from scripts.query.execute import execute_plan
from app.ui_qa.db import (
    insert_query_run,
    upsert_label,
    get_labels_for_query,
    get_label_for_candidate
)
from app.ui_qa.config import ISSUE_TAGS, LABEL_TYPES, DEFAULT_QUERY_LIMIT, BIBLIO_DB_PATH

st.set_page_config(page_title="Run + Review", page_icon="▶️", layout="wide")

st.title("▶️ Run + Review")
st.markdown("Execute queries against the M4 pipeline and label results.")

# Query Input Section
st.header("Query Input")

col1, col2, col3 = st.columns([3, 1, 2])

with col1:
    query_text = st.text_input(
        "Query",
        value="books between 1500 and 1599",
        help="Natural language query (e.g., 'books by Oxford between 1500-1600')"
    )

with col2:
    limit = st.number_input(
        "Limit",
        min_value=1,
        max_value=1000,
        value=DEFAULT_QUERY_LIMIT,
        help="Maximum number of results to return"
    )

with col3:
    db_path = st.text_input(
        "Database Path",
        value=str(BIBLIO_DB_PATH),
        help="Path to bibliographic.db"
    )

# Action buttons
col1, col2, col3 = st.columns([1, 1, 3])

with col1:
    run_button = st.button("▶️ Run Query", type="primary", use_container_width=True)

with col2:
    load_last = st.button("📋 Load Last Run", use_container_width=True)

# Run Query
if run_button:
    with st.spinner("Running query..."):
        try:
            # Compile
            plan = compile_query(query_text, limit=limit)

            # Execute
            result = execute_plan(plan, Path(db_path))

            # Persist to QA DB
            query_id = insert_query_run(
                query_text=query_text,
                plan=plan,
                result=result,
                db_path=db_path,
                status="OK"
            )

            # Store in session state
            st.session_state['current_query_id'] = query_id
            st.session_state['current_query_text'] = query_text
            st.session_state['current_plan'] = plan
            st.session_state['current_result'] = result

            st.success(f"✅ Query executed: {result.total_count} candidates found (Query ID: {query_id})")

        except Exception as e:
            st.error(f"❌ Error: {e}")
            # Store error in DB
            try:
                insert_query_run(
                    query_text=query_text,
                    plan=None,
                    result=None,
                    db_path=db_path,
                    status="ERROR",
                    error_message=str(e)
                )
            except:
                pass

# Display Results Section
if 'current_result' in st.session_state:
    result = st.session_state['current_result']
    plan = st.session_state['current_plan']
    query_id = st.session_state['current_query_id']

    st.divider()

    # Summary Stats
    st.header("Query Results")

    # Get current labels
    labels = get_labels_for_query(query_id)
    label_counts = {'TP': 0, 'FP': 0, 'FN': 0, 'UNK': 0}
    for label in labels:
        label_counts[label['label']] = label_counts.get(label['label'], 0) + 1

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total", result.total_count)
    col2.metric("TP", label_counts['TP'], delta_color="normal")
    col3.metric("FP", label_counts['FP'], delta_color="inverse")
    col4.metric("FN", label_counts['FN'], delta_color="inverse")
    col5.metric("UNK", result.total_count - sum([label_counts['TP'], label_counts['FP'], label_counts['FN']]))

    # Collapsible viewers
    with st.expander("📋 Query Plan", expanded=False):
        st.json(plan.model_dump(), expanded=True)

    with st.expander("🔍 SQL", expanded=False):
        st.code(result.sql, language="sql")
        if st.button("📋 Copy SQL"):
            st.code(result.sql)

    st.divider()

    # Bulk Labeling Section
    st.subheader("Bulk Actions")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("✅ Mark All as TP", use_container_width=True):
            for candidate in result.candidates:
                upsert_label(query_id, candidate.record_id, "TP")
            st.success(f"Marked all {len(result.candidates)} candidates as TP")
            st.rerun()

    with col2:
        if st.button("❌ Mark All as FP", use_container_width=True):
            for candidate in result.candidates:
                upsert_label(query_id, candidate.record_id, "FP")
            st.success(f"Marked all {len(result.candidates)} candidates as FP")
            st.rerun()

    with col3:
        if st.button("🔄 Clear All Labels", use_container_width=True):
            for candidate in result.candidates:
                upsert_label(query_id, candidate.record_id, "UNK")
            st.success("Cleared all labels")
            st.rerun()

    st.divider()

    # Candidates Table
    st.subheader("Candidates")

    # Build dataframe with labels
    candidates_data = []
    for candidate in result.candidates:
        label_info = get_label_for_candidate(query_id, candidate.record_id)
        current_label = label_info['label'] if label_info else 'UNK'

        candidates_data.append({
            'Record ID': candidate.record_id,
            'Match Rationale': candidate.match_rationale,
            'Evidence Count': len(candidate.evidence),
            'Label': current_label
        })

    df = pd.DataFrame(candidates_data)

    # Display table with selection
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # Candidate Detail Pane (Sidebar)
    if event.selection.rows:
        selected_idx = event.selection.rows[0]
        selected_candidate = result.candidates[selected_idx]

        with st.sidebar:
            st.header(f"Candidate Detail")
            st.subheader(f"📄 {selected_candidate.record_id}")

            st.write(f"**Rationale:** {selected_candidate.match_rationale}")

            st.divider()

            # Evidence Table
            st.write("**Evidence:**")
            evidence_data = []
            for ev in selected_candidate.evidence:
                evidence_data.append({
                    'Field': ev.field,
                    'Value': str(ev.value)[:50],  # Truncate long values
                    'Operator': ev.operator,
                    'Matched': str(ev.matched_against)[:30],
                    'Confidence': f"{ev.confidence:.2f}" if ev.confidence else "N/A"
                })

            if evidence_data:
                evidence_df = pd.DataFrame(evidence_data)
                st.dataframe(evidence_df, use_container_width=True, hide_index=True)
            else:
                st.write("No evidence available")

            st.divider()

            # Label Controls
            st.write("**Label:**")

            # Get current label
            label_info = get_label_for_candidate(query_id, selected_candidate.record_id)
            current_label = label_info['label'] if label_info else 'UNK'
            current_issue_tags = label_info.get('issue_tags') if label_info else None
            current_note = label_info.get('note', '') if label_info else ''

            # Parse issue tags from JSON if exists
            if current_issue_tags:
                import json
                try:
                    current_issue_tags = json.loads(current_issue_tags)
                except:
                    current_issue_tags = []
            else:
                current_issue_tags = []

            label = st.radio(
                "Label Type",
                options=LABEL_TYPES,
                index=LABEL_TYPES.index(current_label),
                horizontal=True
            )

            # Issue tags (only for FP/FN)
            issue_tags = []
            if label in ['FP', 'FN']:
                issue_tags = st.multiselect(
                    "Issue Tags",
                    options=ISSUE_TAGS,
                    default=current_issue_tags,
                    help="Select one or more issue tags"
                )

            note = st.text_area("Notes", value=current_note, help="Optional notes about this candidate")

            if st.button("💾 Save Label", type="primary", use_container_width=True):
                upsert_label(
                    query_id=query_id,
                    record_id=selected_candidate.record_id,
                    label=label,
                    issue_tags=issue_tags if issue_tags else None,
                    note=note if note else None
                )
                st.success("✅ Label saved!")
                st.rerun()

else:
    st.info("👆 Enter a query and click 'Run Query' to get started!")
