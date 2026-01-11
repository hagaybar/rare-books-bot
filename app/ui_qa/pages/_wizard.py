"""Wizard - Guided QA session step-by-step workflow.

This page is in pages/ subdirectory but prefixed with underscore to prevent auto-discovery.
It's launched explicitly via st.switch_page() from the landing page.
"""
import sys
import pathlib

# Ensure the root directory is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT))

import streamlit as st
import json
import pandas as pd
from pathlib import Path
from datetime import datetime

from app.ui_qa.db import (
    get_session_by_id,
    update_session_step,
    update_session_config,
    update_session_query_id,
    finish_session,
    abort_session,
    insert_query_run,
    upsert_label,
    get_query_by_id,
    get_labels_for_query,
    get_random_labeled_candidates,
    get_label_for_candidate
)
from app.ui_qa.config import CANONICAL_QUERIES, BIBLIO_DB_PATH, ISSUE_TAGS
from app.ui_qa.wizard_components import (
    render_stepper,
    get_step_instruction,
    render_bulk_label_actions,
    get_label_counts_for_session,
    compute_session_summary,
    render_navigation_buttons
)
from scripts.query.compile import compile_query
from scripts.query.execute import execute_plan
from scripts.query.db_adapter import get_connection

st.set_page_config(page_title="QA Wizard", page_icon="🧙", layout="wide")

# Check if session_id is in session state
if 'wizard_session_id' not in st.session_state:
    st.error("❌ No session loaded. Please start from the QA Sessions page.")
    if st.button("← Back to Sessions"):
        st.switch_page("pages/0_qa_sessions.py")
    st.stop()

session_id = st.session_state['wizard_session_id']

# Load session
session = get_session_by_id(session_id)

if not session:
    st.error(f"❌ Session #{session_id} not found.")
    if st.button("← Back to Sessions"):
        st.switch_page("pages/0_qa_sessions.py")
    st.stop()

# Check if session is still in progress
if session['status'] != 'IN_PROGRESS':
    st.warning(f"⚠️ Session #{session_id} is {session['status']}. Cannot edit.")
    if st.button("← Back to Sessions"):
        st.switch_page("pages/0_qa_sessions.py")
    st.stop()

# Get session details
session_type = session['session_type']
current_step = session['current_step']
total_steps = 5

# Step names
step_names = [
    "Setup Query",
    "Run + Plan Check",
    "Label Candidates",
    "Evidence Spot Check" if session_type == "SMOKE" else "Find Missing",
    "Session Summary"
]

# Header
st.title(f"🧙 {session_type} Session #{session_id}")

# Render stepper
render_stepper(current_step, total_steps, step_names)

st.divider()

# Show instruction
instruction = get_step_instruction(current_step, session_type)
if instruction:
    st.info(f"**Instructions:** {instruction}")

st.divider()


# ==================== Step Functions ====================


def render_step_1():
    """Step 1: Setup Query"""
    st.subheader("Step 1: Setup Query")

    # Load current config
    config = json.loads(session['session_config_json'])

    # Canonical query selection
    st.markdown("### Choose Query")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.write("**Option 1: Select Canonical Query**")
        canonical_options = ["(Custom query)"] + [
            f"{q['id']}. {q['query_text']} - {q['description']}"
            for q in CANONICAL_QUERIES
        ]

        selected_canonical = st.selectbox(
            "Canonical Queries",
            canonical_options,
            index=0,
            key="canonical_query_select"
        )

        if selected_canonical != "(Custom query)":
            # Extract query text from selection
            canonical_id = int(selected_canonical.split(".")[0])
            canonical_query = next((q for q in CANONICAL_QUERIES if q['id'] == canonical_id), None)
            if canonical_query:
                query_text = canonical_query['query_text']
                st.success(f"✅ Selected: {query_text}")
                config['query_text'] = query_text
                config['canonical_query_id'] = canonical_id

    with col2:
        st.write("**Option 2: Type Custom Query**")
        custom_query = st.text_area(
            "Custom Query Text",
            value=config.get('query_text', ''),
            height=100,
            key="custom_query_text"
        )

        if custom_query.strip():
            config['query_text'] = custom_query
            config['canonical_query_id'] = None

    st.divider()

    # Query parameters
    st.markdown("### Query Parameters")

    col1, col2 = st.columns(2)

    with col1:
        limit = st.number_input(
            "Result Limit",
            min_value=1,
            max_value=200,
            value=config.get('limit', 30),
            key="query_limit"
        )
        config['limit'] = limit

    with col2:
        db_path = st.text_input(
            "Database Path",
            value=config.get('db_path', str(BIBLIO_DB_PATH)),
            key="db_path_input"
        )
        config['db_path'] = db_path

    # Show current config
    with st.expander("📋 Current Configuration", expanded=False):
        st.json(config)

    # Save config button
    if st.button("💾 Save Configuration"):
        update_session_config(session_id, config)
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.success(f"Saved configuration at {timestamp}")
        st.rerun()


def render_step_2():
    """Step 2: Run + Plan Check"""
    st.subheader("Step 2: Run Query & Verify Plan")

    # Load config
    config = json.loads(session['session_config_json'])
    query_text = config.get('query_text', '')
    limit = config.get('limit', 30)
    db_path = Path(config.get('db_path', str(BIBLIO_DB_PATH)))

    st.write(f"**Query:** {query_text}")
    st.write(f"**Limit:** {limit}")

    # Run query button
    if not session.get('query_id'):
        if st.button("▶️ Run Query Now", type="primary"):
            with st.spinner("Running query..."):
                try:
                    # Compile
                    plan = compile_query(query_text, limit=limit)

                    # Execute
                    result = execute_plan(plan, db_path)

                    # Persist
                    query_id = insert_query_run(
                        query_text=query_text,
                        plan=plan,
                        result=result,
                        db_path=str(db_path),
                        status="OK",
                        session_id=session_id
                    )

                    # Link to session
                    update_session_query_id(session_id, query_id)

                    st.success(f"✅ Query executed successfully! {result.total_count} candidates found.")
                    st.rerun()

                except Exception as e:
                    # Store error
                    query_id = insert_query_run(
                        query_text=query_text,
                        plan=None,
                        result=None,
                        db_path=str(db_path),
                        status="ERROR",
                        error_message=str(e),
                        session_id=session_id
                    )
                    st.error(f"❌ Query execution failed: {e}")
    else:
        st.success("✅ Query already executed.")

        # Load query results
        query = get_query_by_id(session['query_id'])

        if query:
            st.write(f"**Status:** {query['status']}")
            st.write(f"**Total Candidates:** {query['total_candidates']}")

            # Show plan
            with st.expander("📋 Query Plan", expanded=True):
                plan_data = json.loads(query['plan_json'])
                st.json(plan_data)

            # Show SQL
            with st.expander("🔍 Generated SQL", expanded=False):
                st.code(query['sql_text'], language="sql")

            st.divider()

            # Plan verification checkbox
            st.markdown("### ✅ Plan Verification")

            plan_matches = st.checkbox(
                "The query plan matches my intent",
                value=st.session_state.get('plan_matches_intent', False),
                key="plan_matches_intent_checkbox"
            )

            if plan_matches:
                st.session_state['plan_matches_intent'] = True
            else:
                st.session_state['plan_matches_intent'] = False

                # Optional: What's wrong?
                whats_wrong = st.text_area(
                    "What's wrong with the plan? (optional)",
                    key="plan_whats_wrong"
                )


def render_step_3():
    """Step 3: Label Candidates"""
    st.subheader("Step 3: Label Candidates")

    query_id = session['query_id']

    if not query_id:
        st.error("❌ No query executed yet. Go back to Step 2.")
        return

    # Load query
    query = get_query_by_id(query_id)

    if not query:
        st.error("❌ Query not found.")
        return

    # Load results from query
    plan = json.loads(query['plan_json'])

    # Re-execute to get candidates (since we don't store them)
    config = json.loads(session['session_config_json'])
    db_path = Path(config.get('db_path', str(BIBLIO_DB_PATH)))

    try:
        from scripts.schemas.query_plan import QueryPlan
        plan_obj = QueryPlan(**plan)
        result = execute_plan(plan_obj, db_path)
        candidates = result.candidates
    except Exception as e:
        st.error(f"❌ Error loading candidates: {e}")
        return

    # Get label counts
    label_counts = get_label_counts_for_session(session_id, query_id)
    labeled_count = label_counts['TP'] + label_counts['FP']

    # Threshold
    config = json.loads(session['session_config_json'])
    threshold = config.get('thresholds', {}).get('min_labels', 10)

    # Show counters
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Candidates", len(candidates))
    col2.metric("Labeled (TP+FP)", labeled_count)
    col3.metric("Required", f"{threshold}")

    # Progress
    progress = min(labeled_count / threshold, 1.0) if threshold > 0 else 1.0
    st.progress(progress)

    if labeled_count >= threshold:
        st.success(f"✅ Requirement met! ({labeled_count}/{threshold} labeled)")
    else:
        st.warning(f"⚠️ Please label {threshold - labeled_count} more candidates.")

        # Override option when there are fewer results than threshold
        if len(candidates) < threshold:
            st.info(f"ℹ️ This query returned only {len(candidates)} candidates (less than the {threshold} required).")
            override = st.checkbox(
                f"✓ Override requirement (proceed with {labeled_count} labels)",
                key="step3_override",
                help="Check this box to proceed to the next step even though you have fewer than the required labels."
            )
            if override:
                st.success(f"✅ Override enabled. You can proceed with {labeled_count} labels.")

    st.divider()

    # Bulk actions
    st.markdown("### Bulk Actions")
    render_bulk_label_actions(session_id, query_id, candidates)

    st.divider()

    # Candidates table
    st.markdown("### Candidates")

    if candidates:
        # Prepare table data
        candidates_data = []
        for candidate in candidates:
            # Get existing label
            label_info = get_label_for_candidate(query_id, candidate.record_id)
            current_label = label_info['label'] if label_info else 'UNK'

            candidates_data.append({
                'Record ID': candidate.record_id,
                'Rationale': candidate.match_rationale[:80] + '...' if len(candidate.match_rationale) > 80 else candidate.match_rationale,
                'Evidence Count': len(candidate.evidence),
                'Label': current_label
            })

        candidates_df = pd.DataFrame(candidates_data)

        # Display with selection
        event = st.dataframe(
            candidates_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        # Show detail pane for selected candidate
        if event.selection.rows:
            selected_idx = event.selection.rows[0]
            selected_candidate = candidates[selected_idx]

            with st.sidebar:
                st.subheader(f"📝 Label Candidate")
                st.write(f"**Record ID:** {selected_candidate.record_id}")
                st.write(f"**Rationale:** {selected_candidate.match_rationale}")

                # Evidence table
                if selected_candidate.evidence:
                    st.markdown("**Evidence:**")
                    evidence_data = []
                    for ev in selected_candidate.evidence:
                        evidence_data.append({
                            'Field': ev.field,
                            'Value': str(ev.value)[:50],
                            'Operator': ev.operator,
                            'Matched': str(ev.matched_against)[:50]
                        })
                    st.dataframe(pd.DataFrame(evidence_data), use_container_width=True, hide_index=True)

                st.divider()

                # Get current label
                label_info = get_label_for_candidate(query_id, selected_candidate.record_id)
                current_label = label_info['label'] if label_info else 'UNK'
                current_tags = json.loads(label_info['issue_tags']) if label_info and label_info['issue_tags'] else []
                current_note = label_info['note'] if label_info else ''

                # Label controls
                label = st.radio(
                    "Label",
                    ["TP", "FP", "FN", "UNK"],
                    index=["TP", "FP", "FN", "UNK"].index(current_label),
                    key=f"label_{selected_candidate.record_id}"
                )

                issue_tags = []
                if label in ["FP", "FN"]:
                    issue_tags = st.multiselect(
                        "Issue Tags",
                        ISSUE_TAGS,
                        default=current_tags,
                        key=f"tags_{selected_candidate.record_id}"
                    )

                note = st.text_area(
                    "Notes (optional)",
                    value=current_note,
                    key=f"note_{selected_candidate.record_id}"
                )

                if st.button("💾 Save Label", use_container_width=True):
                    upsert_label(
                        query_id=query_id,
                        record_id=selected_candidate.record_id,
                        label=label,
                        issue_tags=issue_tags if issue_tags else None,
                        note=note if note else None,
                        session_id=session_id
                    )
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    st.success(f"Saved label at {timestamp}")
                    st.rerun()
    else:
        st.info("No candidates found.")


def render_step_4_smoke():
    """Step 4 (SMOKE): Evidence Spot Check"""
    st.subheader("Step 4: Evidence Spot Check")

    query_id = session['query_id']

    # Get 3 random labeled candidates
    if 'evidence_candidates' not in st.session_state:
        candidates_data = get_random_labeled_candidates(session_id, count=3)
        st.session_state['evidence_candidates'] = candidates_data
        st.session_state['reshuffle_count'] = 0

    candidates_data = st.session_state['evidence_candidates']

    st.write("**Review these 3 randomly selected candidates to verify evidence quality:**")

    if len(candidates_data) < 3:
        st.warning(f"⚠️ Only {len(candidates_data)} labeled candidates available. Label more in Step 3.")

    # Reshuffle button
    col1, col2 = st.columns([3, 1])
    with col2:
        reshuffle_count = st.session_state.get('reshuffle_count', 0)
        if reshuffle_count < 2:
            if st.button("🔄 Reshuffle", use_container_width=True):
                candidates_data = get_random_labeled_candidates(session_id, count=3)
                st.session_state['evidence_candidates'] = candidates_data
                st.session_state['reshuffle_count'] = reshuffle_count + 1
                st.rerun()
        else:
            st.button("🔄 Reshuffle", disabled=True, use_container_width=True)
            st.caption("(Max 2 reshuffles)")

    st.divider()

    # Display each candidate
    for idx, cand_data in enumerate(candidates_data, 1):
        with st.container(border=True):
            st.write(f"### Candidate {idx}: {cand_data['record_id']}")
            st.write(f"**Label:** {cand_data['label']}")

            # Load full candidate details
            config = json.loads(session['session_config_json'])
            db_path = Path(config.get('db_path', str(BIBLIO_DB_PATH)))
            query = get_query_by_id(query_id)
            plan = json.loads(query['plan_json'])

            try:
                from scripts.schemas.query_plan import QueryPlan
                plan_obj = QueryPlan(**plan)
                result = execute_plan(plan_obj, db_path)

                # Find this candidate
                candidate = next((c for c in result.candidates if c.record_id == cand_data['record_id']), None)

                if candidate:
                    st.write(f"**Rationale:** {candidate.match_rationale}")

                    if candidate.evidence:
                        evidence_data = []
                        for ev in candidate.evidence:
                            evidence_data.append({
                                'Field': ev.field,
                                'Value': str(ev.value)[:50],
                                'Operator': ev.operator,
                                'Matched': str(ev.matched_against)[:50]
                            })
                        st.dataframe(pd.DataFrame(evidence_data), use_container_width=True, hide_index=True)

                    # Checkbox
                    st.checkbox(
                        "✅ Evidence supports rationale",
                        key=f"evidence_check_{idx}"
                    )
            except Exception as e:
                st.error(f"Error loading candidate: {e}")

    st.divider()

    # Skip option
    st.markdown("### Or Skip Evidence Check")
    skip_reason = st.text_area(
        "Reason for skipping (if any)",
        key="evidence_skip_reason"
    )


def render_step_4_recall():
    """Step 4 (RECALL): Find Missing"""
    st.subheader("Step 4: Find Missing Records")

    st.write("**Search for likely matches that didn't appear in results and mark them as FN.**")

    query_id = session['query_id']
    config = json.loads(session['session_config_json'])
    db_path = Path(config.get('db_path', str(BIBLIO_DB_PATH)))

    # Get existing candidate IDs
    query = get_query_by_id(query_id)
    plan = json.loads(query['plan_json'])

    try:
        from scripts.schemas.query_plan import QueryPlan
        plan_obj = QueryPlan(**plan)
        result = execute_plan(plan_obj, db_path)
        existing_ids = {c.record_id for c in result.candidates}
    except:
        existing_ids = set()

    st.divider()

    # Search form
    st.markdown("### Search Database")

    col1, col2, col3 = st.columns(3)

    with col1:
        year_start = st.number_input("Year Start", value=1500, min_value=1000, max_value=2100)
        year_end = st.number_input("Year End", value=1600, min_value=1000, max_value=2100)

    with col2:
        place = st.text_input("Place contains")
        publisher = st.text_input("Publisher contains")

    with col3:
        search_limit = st.number_input("Limit", value=50, min_value=1, max_value=500)

    if st.button("🔍 Search Database"):
        # Execute search
        try:
            conn = get_connection(db_path)
            sql = """
                SELECT DISTINCT r.mms_id, i.publisher_norm, i.place_norm, i.date_start, i.date_end
                FROM records r
                JOIN imprints i ON r.id = i.record_id
                WHERE i.date_start <= :year_end AND i.date_end >= :year_start
            """
            params = {"year_start": year_start, "year_end": year_end}

            if place:
                sql += " AND LOWER(i.place_norm) LIKE LOWER(:place)"
                params["place"] = f"%{place}%"

            if publisher:
                sql += " AND LOWER(i.publisher_norm) LIKE LOWER(:publisher)"
                params["publisher"] = f"%{publisher}%"

            sql += f" ORDER BY r.mms_id LIMIT {search_limit}"

            cursor = conn.execute(sql, params)
            search_results = cursor.fetchall()
            conn.close()

            st.session_state['search_results'] = search_results

        except Exception as e:
            st.error(f"Search error: {e}")

    # Display results
    if 'search_results' in st.session_state:
        search_results = st.session_state['search_results']

        st.divider()
        st.write(f"**Search Results:** {len(search_results)} records found")

        # Get FN count
        label_counts = get_label_counts_for_session(session_id, query_id)
        fn_count = label_counts['FN']
        st.metric("FN Marked", fn_count)

        # Display results
        for idx, row in enumerate(search_results):
            record_id = row[0]
            already_in = record_id in existing_ids

            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 1, 1])

                with col1:
                    st.write(f"**{record_id}**")
                    st.caption(f"Place: {row[2]}, Publisher: {row[1]}, Dates: {row[3]}-{row[4]}")

                with col2:
                    if already_in:
                        st.success("✅ In results")
                    else:
                        st.warning("Not in results")

                with col3:
                    if st.button("Mark as FN", key=f"fn_{idx}"):
                        upsert_label(
                            query_id=query_id,
                            record_id=record_id,
                            label="FN",
                            session_id=session_id
                        )
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        st.success(f"Marked FN at {timestamp}")
                        st.rerun()

    st.divider()

    # No missing option
    st.checkbox("✅ No missing records found", key="no_missing_found")


def render_step_5():
    """Step 5: Session Summary"""
    st.subheader("Step 5: Session Summary")

    query_id = session['query_id']

    # Compute summary
    summary = compute_session_summary(session_id, query_id)

    # Display metrics
    st.markdown("### Session Statistics")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("TP Count", summary['tp_count'])
    col2.metric("FP Count", summary['fp_count'])
    col3.metric("FN Count", summary['fn_count'])
    col4.metric("TP Rate", f"{summary['tp_rate']:.1%}")

    if summary['top_issue_tags']:
        st.write("**Top Issue Tags:**")
        st.write(", ".join(summary['top_issue_tags']))

    st.divider()

    # Query details
    st.markdown("### Query Details")
    config = json.loads(session['session_config_json'])
    st.write(f"**Query Text:** {config.get('query_text', 'N/A')}")
    st.write(f"**Limit:** {config.get('limit', 'N/A')}")

    st.divider()

    # User inputs
    st.markdown("### Session Verdict")

    verdict = st.radio(
        "Verdict",
        ["PASS", "NEEDS_WORK", "INCONCLUSIVE"],
        key="session_verdict"
    )

    notes = st.text_area(
        "Session Notes",
        key="session_notes",
        height=100
    )

    # Additional for RECALL
    if session_type == 'RECALL':
        st.markdown("### Suspected Root Causes (optional)")
        root_causes = st.multiselect(
            "What might be causing the false negatives?",
            [
                "Parser issue",
                "Normalization issue",
                "SQL logic issue",
                "Insufficient data in records"
            ],
            key="root_causes"
        )
        summary['root_causes'] = root_causes

    summary['user_notes'] = notes

    st.divider()

    # Finish buttons
    col1, col2 = st.columns(2)

    with col1:
        if st.button("✅ Finish Session", type="primary", use_container_width=True):
            finish_session(session_id, verdict, notes, summary)
            st.success("✅ Session completed!")
            st.balloons()
            st.switch_page("pages/0_qa_sessions.py")

    with col2:
        if st.button("❌ Abort Session", use_container_width=True):
            abort_session(session_id)
            st.warning("Session aborted.")
            st.switch_page("pages/0_qa_sessions.py")


# ==================== Main Render Logic ====================

# Render current step
if current_step == 1:
    render_step_1()
elif current_step == 2:
    render_step_2()
elif current_step == 3:
    render_step_3()
elif current_step == 4:
    if session_type == 'SMOKE':
        render_step_4_smoke()
    else:  # RECALL
        render_step_4_recall()
elif current_step == 5:
    render_step_5()

st.divider()

# Navigation buttons
def on_back():
    new_step = max(1, current_step - 1)
    update_session_step(session_id, new_step)
    st.rerun()

def on_next():
    new_step = min(total_steps, current_step + 1)
    update_session_step(session_id, new_step)
    st.rerun()

render_navigation_buttons(
    session=session,
    session_id=session_id,
    current_step=current_step,
    total_steps=total_steps,
    session_type=session_type,
    on_back=on_back,
    on_next=on_next
)

# Footer
st.divider()

col1, col2 = st.columns([3, 1])
with col1:
    st.caption(f"Session #{session_id} • {session_type} • Updated: {session['updated_at'][:19]}")

with col2:
    if st.button("🏠 Exit to Sessions"):
        st.switch_page("pages/0_qa_sessions.py")
