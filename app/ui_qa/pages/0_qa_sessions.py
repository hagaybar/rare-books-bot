"""Page 0: QA Sessions - Landing page for guided testing sessions."""
import sys
import pathlib

# Ensure the root directory is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT))

import streamlit as st
import pandas as pd
import json
from datetime import datetime
from app.ui_qa.db import (
    get_session_by_status,
    get_recent_sessions,
    create_session,
    abort_session,
    delete_session
)
from app.ui_qa.config import BIBLIO_DB_PATH

st.set_page_config(page_title="QA Sessions", page_icon="🧪", layout="wide")

st.title("🧪 Guided QA Sessions")
st.markdown("Structured testing workflows for query validation and issue tracking.")

# Check for IN_PROGRESS session
in_progress = get_session_by_status('IN_PROGRESS')

if in_progress:
    st.info("⚠️ You have a session in progress")

    with st.container(border=True):
        st.subheader("🔄 Continue Session")

        # Parse config to show details
        try:
            config = json.loads(in_progress['session_config_json'])
            query_text = config.get('query_text', 'N/A')
            session_type = in_progress['session_type']
            current_step = in_progress['current_step']

            # Determine total steps based on session type
            total_steps = 5

            # Step names for display
            step_names = {
                1: "Setup Query",
                2: "Run + Plan Check",
                3: "Label Candidates",
                4: "Evidence Spot Check" if session_type == "SMOKE" else "Find Missing",
                5: "Session Summary"
            }

            col1, col2, col3 = st.columns(3)
            col1.metric("Type", session_type)
            col2.metric("Step", f"{current_step}/{total_steps}")
            col3.metric("Progress", f"{int((current_step / total_steps) * 100)}%")

            st.write(f"**Current Step:** {step_names.get(current_step, 'Unknown')}")
            st.write(f"**Query:** {query_text[:80]}{'...' if len(query_text) > 80 else ''}")
            st.write(f"**Started:** {in_progress['created_at'][:19]}")

            # Action buttons
            col1, col2, col3 = st.columns([2, 1, 1])

            with col1:
                if st.button("▶️ Continue Session", type="primary", use_container_width=True):
                    # Navigate to wizard with session_id
                    st.session_state['wizard_session_id'] = in_progress['id']
                    st.switch_page("pages/_wizard.py")

            with col2:
                if st.button("⏸️ Abort Session", use_container_width=True):
                    abort_session(in_progress['id'])
                    st.success(f"✅ Session #{in_progress['id']} aborted")
                    st.rerun()

            with col3:
                # Delete with confirmation
                session_id = in_progress['id']
                confirm_key = f'confirm_delete_session_{session_id}'

                if st.button("🗑️ Delete", use_container_width=True):
                    if st.session_state.get(confirm_key, False):
                        # Actually delete
                        if delete_session(session_id):
                            st.success(f"✅ Deleted session #{session_id}")
                            st.session_state[confirm_key] = False
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to delete session #{session_id}")
                    else:
                        # Ask for confirmation
                        st.session_state[confirm_key] = True
                        st.rerun()

            # Show confirmation warning if needed
            if st.session_state.get(f'confirm_delete_session_{in_progress["id"]}', False):
                st.warning("⚠️ **Click 'Delete' again to permanently remove this session and all its data.**")
                if st.button("Cancel Deletion"):
                    st.session_state[f'confirm_delete_session_{in_progress["id"]}'] = False
                    st.rerun()

        except Exception as e:
            st.error(f"Error parsing session data: {e}")

st.divider()

# Begin New Test section
st.subheader("🆕 Begin New Test")

if in_progress:
    st.warning("⚠️ You must complete or abort the current session before starting a new one.")
else:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### SMOKE Test")
        st.write("**Goal:** Validate parser + candidate precision")
        st.write("**Steps:** 5")
        st.write("**Focus:** TP/FP labeling, evidence quality")
        st.write("**Time:** ~10-15 minutes")

        if st.button("🚀 Start SMOKE Session", type="primary", use_container_width=True):
            # Create new SMOKE session with default config
            config = {
                "query_text": "",
                "limit": 30,
                "db_path": str(BIBLIO_DB_PATH),
                "canonical_query_id": None,
                "thresholds": {
                    "min_labels": 10,
                    "evidence_spot_check_count": 3
                }
            }
            session_id = create_session("SMOKE", config)
            st.session_state['wizard_session_id'] = session_id
            st.success(f"✅ Created SMOKE session #{session_id}")
            st.switch_page("pages/_wizard.py")

    with col2:
        st.markdown("### RECALL Test")
        st.write("**Goal:** Find false negatives (missing records)")
        st.write("**Steps:** 5")
        st.write("**Focus:** FN discovery + labeling")
        st.write("**Time:** ~15-20 minutes")

        if st.button("🔍 Start RECALL Session", type="primary", use_container_width=True):
            # Create new RECALL session with default config
            config = {
                "query_text": "",
                "limit": 30,
                "db_path": str(BIBLIO_DB_PATH),
                "canonical_query_id": None,
                "thresholds": {
                    "min_labels": 5,  # Lower threshold for RECALL
                    "evidence_spot_check_count": 3
                }
            }
            session_id = create_session("RECALL", config)
            st.session_state['wizard_session_id'] = session_id
            st.success(f"✅ Created RECALL session #{session_id}")
            st.switch_page("pages/_wizard.py")

st.divider()

# Recent Sessions section
st.subheader("📋 Recent Sessions")

recent_sessions = get_recent_sessions(limit=20)

if recent_sessions:
    # Prepare data for display
    sessions_data = []
    for session in recent_sessions:
        # Parse config to get query text
        try:
            config = json.loads(session['session_config_json'])
            query_text = config.get('query_text', 'N/A')
        except:
            query_text = 'N/A'

        # Calculate completion percentage
        current_step = session['current_step']
        total_steps = 5
        completion_pct = int((current_step / total_steps) * 100) if session['status'] != 'DONE' else 100

        sessions_data.append({
            'ID': session['id'],
            'Created': session['created_at'][:19],
            'Type': session['session_type'],
            'Status': session['status'],
            'Step': f"{current_step}/{total_steps}" if session['status'] == 'IN_PROGRESS' else '-',
            'Progress': f"{completion_pct}%",
            'Verdict': session['verdict'] or '-',
            'Query': query_text[:50] + '...' if len(query_text) > 50 else query_text
        })

    sessions_df = pd.DataFrame(sessions_data)

    # Display table with selection
    event = st.dataframe(
        sessions_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # Show detail for selected session
    if event.selection.rows:
        selected_idx = event.selection.rows[0]
        selected_session = recent_sessions[selected_idx]

        st.divider()

        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

        with col1:
            st.subheader(f"Session #{selected_session['id']} Details")

        with col2:
            if selected_session['status'] == 'IN_PROGRESS':
                if st.button("▶️ Open Session", use_container_width=True):
                    st.session_state['wizard_session_id'] = selected_session['id']
                    st.switch_page("pages/_wizard.py")

        with col3:
            if selected_session['status'] == 'DONE':
                st.success("✅ Complete")
            elif selected_session['status'] == 'ABORTED':
                st.error("❌ Aborted")

        with col4:
            # Delete button for any session
            session_id = selected_session['id']
            confirm_key = f'confirm_delete_session_{session_id}'

            if st.button("🗑️ Delete", key=f"delete_session_{session_id}", use_container_width=True):
                if st.session_state.get(confirm_key, False):
                    # Actually delete
                    if delete_session(session_id):
                        st.success(f"✅ Deleted session #{session_id}")
                        st.session_state[confirm_key] = False
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to delete session #{session_id}")
                else:
                    # Ask for confirmation
                    st.session_state[confirm_key] = True
                    st.rerun()

        # Show confirmation warning if needed
        if st.session_state.get(f'confirm_delete_session_{selected_session["id"]}', False):
            st.warning("⚠️ **Click 'Delete' again to permanently remove this session and all its data.**")
            if st.button("Cancel Deletion", key=f"cancel_delete_{selected_session['id']}"):
                st.session_state[f'confirm_delete_session_{selected_session["id"]}'] = False
                st.rerun()

        # Show session details
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Type", selected_session['session_type'])
        col2.metric("Status", selected_session['status'])
        col3.metric("Verdict", selected_session['verdict'] or 'N/A')
        col4.metric("Step", f"{selected_session['current_step']}/5")

        # Show config
        with st.expander("📋 Configuration", expanded=False):
            try:
                config = json.loads(selected_session['session_config_json'])
                st.json(config)
            except:
                st.write("Error parsing configuration")

        # Show summary if available
        if selected_session['summary_json']:
            with st.expander("📊 Summary", expanded=True):
                try:
                    summary = json.loads(selected_session['summary_json'])

                    if summary:
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("TP Count", summary.get('tp_count', 0))
                        col2.metric("FP Count", summary.get('fp_count', 0))
                        col3.metric("FN Count", summary.get('fn_count', 0))
                        col4.metric("TP Rate", f"{summary.get('tp_rate', 0):.1%}")

                        if summary.get('top_issue_tags'):
                            st.write("**Top Issue Tags:**")
                            st.write(", ".join(summary['top_issue_tags']))

                        if summary.get('user_notes'):
                            st.write("**Notes:**")
                            st.write(summary['user_notes'])
                except:
                    st.write("Error parsing summary")

        # Show notes if available
        if selected_session['note']:
            st.write("**Session Note:**")
            st.info(selected_session['note'])

else:
    st.info("No sessions yet. Start your first guided test above!")

st.divider()

# Help section
with st.expander("ℹ️ About Guided QA Sessions"):
    st.markdown("""
    ### What are Guided QA Sessions?

    Guided QA Sessions provide a **structured, step-by-step workflow** for testing queries
    and building gold regression sets. Each session type follows a predefined sequence of
    steps with automatic validation and progress tracking.

    ### Session Types

    **SMOKE (Precision-Focused)**
    - Tests parser correctness and candidate precision
    - Steps: Setup → Run → Label 10+ candidates → Spot-check evidence → Summarize
    - Use for: Quick validation of parser changes, building TP/FP examples

    **RECALL (False Negative Hunt)**
    - Actively searches for missing records (false negatives)
    - Steps: Setup → Run → Label 5+ candidates → Find missing → Summarize
    - Use for: Identifying gaps in recall, building FN examples

    ### Key Features

    - **Resume capability**: Close browser mid-session and continue later
    - **Automatic gating**: Can't advance until step requirements met
    - **Session history**: Review past sessions, verdicts, and summaries
    - **Isolated tracking**: Labels tagged with session_id
    - **Export to gold sets**: Convert sessions to regression tests

    ### Tips

    - Complete one session at a time (only one IN_PROGRESS allowed)
    - Use canonical queries for consistency across sessions
    - Add issue tags to FP/FN labels to track patterns
    - Review session summaries in Dashboard (Page 3)
    """)
