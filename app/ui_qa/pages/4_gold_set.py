"""Page 4: Gold Set - Export and run regression tests."""
import sys
import pathlib

# Ensure the root directory is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT))

import streamlit as st
import json
import pandas as pd
from pathlib import Path
from scripts.query import QueryService, QueryOptions
from app.ui_qa.db import export_gold_set, get_queries_with_labels, delete_query
from app.ui_qa.config import GOLD_SET_PATH, BIBLIO_DB_PATH

st.set_page_config(page_title="Gold Set", page_icon="🏆", layout="wide")

st.title("🏆 Gold Set & Regression")
st.markdown("Export labeled queries as a gold set and run regression tests.")

# Query Management Section
st.header("Manage Queries")
st.markdown("View and delete queries with labels before exporting to gold set.")

queries_with_labels = get_queries_with_labels()

if queries_with_labels:
    # Prepare data for display
    query_display_data = []
    for q in queries_with_labels:
        query_display_data.append({
            'ID': q['id'],
            'Query Text': q['query_text'][:60] + ('...' if len(q['query_text']) > 60 else ''),
            'Labels': q['label_count'],
            'Status': q['status'],
            'Created': q['created_at'][:19]
        })

    queries_df = pd.DataFrame(query_display_data)

    # Display table with selection
    st.dataframe(
        queries_df,
        use_container_width=True,
        hide_index=True
    )

    # Delete section
    st.markdown("### Delete Query")
    col1, col2 = st.columns([3, 1])

    with col1:
        query_id_to_delete = st.number_input(
            "Enter Query ID to delete",
            min_value=1,
            step=1,
            key="delete_query_id"
        )

        # Show query details if valid ID
        selected_query = next((q for q in queries_with_labels if q['id'] == query_id_to_delete), None)
        if selected_query:
            st.info(f"**Query:** {selected_query['query_text']}\n\n**Labels:** {selected_query['label_count']}")

    with col2:
        st.write("")  # Spacing
        st.write("")  # Spacing
        if st.button("🗑️ Delete Query", type="secondary", use_container_width=True):
            if selected_query:
                # Confirmation
                if st.session_state.get(f'confirm_delete_{query_id_to_delete}', False):
                    # Actually delete
                    if delete_query(query_id_to_delete):
                        st.success(f"✅ Deleted query #{query_id_to_delete}")
                        st.session_state[f'confirm_delete_{query_id_to_delete}'] = False
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to delete query #{query_id_to_delete}")
                else:
                    # Ask for confirmation
                    st.session_state[f'confirm_delete_{query_id_to_delete}'] = True
                    st.warning("⚠️ Click again to confirm deletion")
            else:
                st.error("❌ Query ID not found")

    # Show confirmation state
    if st.session_state.get(f'confirm_delete_{query_id_to_delete}', False):
        st.warning("⚠️ **Confirmation required!** Click 'Delete Query' again to permanently delete this query and all its labels.")
        if st.button("Cancel"):
            st.session_state[f'confirm_delete_{query_id_to_delete}'] = False
            st.rerun()

else:
    st.info("No queries with labels found. Create queries in the Run + Review or QA Sessions pages first.")

st.divider()

# Export Section
st.header("Export Gold Set")

col1, col2, col3 = st.columns(3)
col1.metric("Queries with Labels", len(queries_with_labels))

# Count total labels
total_tp = 0
total_fp = 0
total_fn = 0

for q in queries_with_labels:
    if 'label_count' in q:
        # We'd need to query individual labels to get counts by type
        # For now, just show total
        pass

col2.metric("Ready for Export", len(queries_with_labels))

if st.button("📥 Export Gold Set", type="primary"):
    with st.spinner("Exporting gold set..."):
        try:
            gold_data = export_gold_set()

            # Ensure directory exists
            GOLD_SET_PATH.parent.mkdir(parents=True, exist_ok=True)

            # Write to file
            GOLD_SET_PATH.write_text(json.dumps(gold_data, indent=2))

            st.success(f"✅ Exported {len(gold_data['queries'])} queries to {GOLD_SET_PATH}")

            # Show preview
            with st.expander("📄 Preview Gold Set", expanded=True):
                st.json(gold_data)

            # Download button
            st.download_button(
                label="⬇️ Download Gold Set",
                data=json.dumps(gold_data, indent=2),
                file_name="gold.json",
                mime="application/json"
            )

        except Exception as e:
            st.error(f"❌ Export error: {e}")

st.divider()

# Regression Section
st.header("Run Regression Tests")
st.markdown("Run queries from the gold set and validate results match expected includes/excludes.")

col1, col2 = st.columns(2)

with col1:
    gold_path_input = st.text_input(
        "Gold Set Path",
        value=str(GOLD_SET_PATH),
        help="Path to gold.json file"
    )

with col2:
    db_path_input = st.text_input(
        "Database Path",
        value=str(BIBLIO_DB_PATH),
        help="Path to bibliographic.db"
    )

run_regression_button = st.button("▶️ Run Regression", type="primary")

if run_regression_button:
    gold_path = Path(gold_path_input)
    db_path = Path(db_path_input)

    if not gold_path.exists():
        st.error(f"❌ Gold set not found: {gold_path}")
        st.stop()

    if not db_path.exists():
        st.error(f"❌ Database not found: {db_path}")
        st.stop()

    with st.spinner("Running regression tests..."):
        try:
            # Load gold set
            gold_data = json.loads(gold_path.read_text())
            queries = gold_data['queries']

            st.info(f"Running {len(queries)} queries...")

            results = []

            # Progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, query_spec in enumerate(queries):
                query_text = query_spec['query_text']
                expected_includes = set(query_spec['expected_includes'])
                expected_excludes = set(query_spec['expected_excludes'])

                status_text.text(f"Running query {idx+1}/{len(queries)}: {query_text[:60]}...")

                try:
                    # Run query via QueryService
                    service = QueryService(db_path)
                    query_result = service.execute(query_text, options=QueryOptions(compute_facets=False))
                    result = query_result.candidate_set

                    # Check results
                    actual_ids = {c.record_id for c in result.candidates}

                    missing = expected_includes - actual_ids
                    unexpected = expected_excludes & actual_ids

                    if missing or unexpected:
                        status = "FAIL"
                    else:
                        status = "PASS"

                    results.append({
                        'Query': query_text[:60],
                        'Status': status,
                        'Expected Includes': len(expected_includes),
                        'Expected Excludes': len(expected_excludes),
                        'Actual Results': len(actual_ids),
                        'Missing': len(missing),
                        'Unexpected': len(unexpected),
                        'missing_ids': list(missing),
                        'unexpected_ids': list(unexpected)
                    })

                except Exception as e:
                    results.append({
                        'Query': query_text[:60],
                        'Status': 'ERROR',
                        'Expected Includes': len(expected_includes),
                        'Expected Excludes': len(expected_excludes),
                        'Actual Results': 0,
                        'Missing': 0,
                        'Unexpected': 0,
                        'error': str(e)
                    })

                # Update progress
                progress_bar.progress((idx + 1) / len(queries))

            status_text.empty()
            progress_bar.empty()

            # Display results
            passed = sum(1 for r in results if r['Status'] == 'PASS')
            failed = sum(1 for r in results if r['Status'] == 'FAIL')
            errors = sum(1 for r in results if r['Status'] == 'ERROR')

            st.divider()

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Queries", len(queries))
            col2.metric("Passed", passed, delta_color="normal")
            col3.metric("Failed", failed, delta_color="inverse")
            col4.metric("Errors", errors, delta_color="inverse")

            # Results table
            if passed == len(queries):
                st.success(f"✅ All {len(queries)} queries passed!")
            else:
                st.error(f"❌ {failed + errors}/{len(queries)} queries failed")

            # Display detailed results
            results_df = pd.DataFrame([
                {
                    'Query': r['Query'],
                    'Status': r['Status'],
                    'Expected Inc.': r['Expected Includes'],
                    'Expected Exc.': r['Expected Excludes'],
                    'Actual': r['Actual Results'],
                    'Missing': r['Missing'],
                    'Unexpected': r['Unexpected']
                }
                for r in results
            ])

            # Color code status
            def color_status(val):
                if val == 'PASS':
                    return 'background-color: #d4edda'
                elif val == 'FAIL':
                    return 'background-color: #f8d7da'
                elif val == 'ERROR':
                    return 'background-color: #fff3cd'
                return ''

            styled_df = results_df.style.applymap(color_status, subset=['Status'])

            event = st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row"
            )

            # Show details for selected row
            if event.selection.rows:
                selected_idx = event.selection.rows[0]
                selected_result = results[selected_idx]

                st.divider()
                st.subheader(f"Details: {selected_result['Query']}")

                if selected_result['Status'] == 'ERROR':
                    st.error(f"Error: {selected_result.get('error', 'Unknown error')}")
                else:
                    col1, col2 = st.columns(2)

                    with col1:
                        if selected_result['missing_ids']:
                            st.write("**Missing Records (should be included):**")
                            for record_id in selected_result['missing_ids']:
                                st.write(f"- {record_id}")
                        else:
                            st.success("✅ No missing records")

                    with col2:
                        if selected_result['unexpected_ids']:
                            st.write("**Unexpected Records (should be excluded):**")
                            for record_id in selected_result['unexpected_ids']:
                                st.write(f"- {record_id}")
                        else:
                            st.success("✅ No unexpected records")

        except Exception as e:
            st.error(f"❌ Regression error: {e}")
            import traceback
            st.code(traceback.format_exc())

st.divider()

# CLI Command
st.header("CLI Regression Runner")
st.markdown("For CI integration, use the CLI command:")

st.code(f"""poetry run python -m app.qa regress \\
    --gold {gold_path_input} \\
    --db {db_path_input}""", language="bash")

st.info("💡 Add this command to your CI pipeline (GitHub Actions, GitLab CI, etc.) to automatically run regression tests.")
