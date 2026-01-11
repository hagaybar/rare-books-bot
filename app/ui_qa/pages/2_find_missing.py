"""Page 2: Find Missing - Search for false negatives."""
import sys
import pathlib

# Ensure the root directory is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT))

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from scripts.query.db_adapter import get_connection
from app.ui_qa.db import (
    get_query_runs,
    get_query_by_id,
    upsert_label,
    get_labels_for_query
)
from app.ui_qa.config import ISSUE_TAGS, BIBLIO_DB_PATH, DEFAULT_SEARCH_LIMIT

st.set_page_config(page_title="Find Missing", page_icon="🔍", layout="wide")

st.title("🔍 Find Missing (False Negatives)")
st.markdown("Search for records that should have matched a query but didn't.")

# Query Selection
st.header("1. Select Query")

# Get recent queries
queries = get_query_runs(limit=50)

if not queries:
    st.warning("No queries found. Run a query on Page 1 first!")
    st.stop()

# Format query options for dropdown
query_options = {}
for q in queries:
    if q['status'] == 'OK':
        label = f"{q['created_at'][:19]} - {q['query_text'][:60]} ({q['total_candidates']} candidates)"
        query_options[label] = q['id']

if not query_options:
    st.warning("No successful queries found. Run a query on Page 1 first!")
    st.stop()

selected_label = st.selectbox(
    "Select a query to find missing results for:",
    options=list(query_options.keys())
)

selected_query_id = query_options[selected_label]
selected_query = get_query_by_id(selected_query_id)

# Show query context
with st.expander("📋 Query Context", expanded=False):
    st.write(f"**Query:** {selected_query['query_text']}")
    st.write(f"**Total Candidates:** {selected_query['total_candidates']}")

    # Parse and show plan
    try:
        plan_data = json.loads(selected_query['plan_json'])
        st.json(plan_data)
    except:
        pass

st.divider()

# Search Controls
st.header("2. Search Database")
st.markdown("Use these controls to search for records that might be missing from the results.")

col1, col2 = st.columns(2)

with col1:
    year_start = st.number_input("Year Start", min_value=1000, max_value=2100, value=1500)
    year_end = st.number_input("Year End", min_value=1000, max_value=2100, value=1600)

with col2:
    place = st.text_input("Place Contains", help="Search in place_norm (leave empty to skip)")
    publisher = st.text_input("Publisher Contains", help="Search in publisher_norm (leave empty to skip)")

search_limit = st.number_input(
    "Search Limit",
    min_value=1,
    max_value=500,
    value=DEFAULT_SEARCH_LIMIT,
    help="Maximum number of search results"
)

search_button = st.button("🔍 Search Database", type="primary")

# Execute Search
if search_button or 'search_results' in st.session_state:
    if search_button:
        with st.spinner("Searching database..."):
            try:
                conn = get_connection(Path(BIBLIO_DB_PATH))

                # Build SQL query
                sql = """
                    SELECT DISTINCT
                        r.mms_id,
                        i.publisher_norm,
                        i.place_norm,
                        i.date_start,
                        i.date_end
                    FROM records r
                    JOIN imprints i ON r.id = i.record_id
                    WHERE i.date_start <= :year_end
                      AND i.date_end >= :year_start
                """
                params = {"year_start": year_start, "year_end": year_end}

                if place and place.strip():
                    sql += " AND LOWER(i.place_norm) LIKE LOWER(:place)"
                    params["place"] = f"%{place}%"

                if publisher and publisher.strip():
                    sql += " AND LOWER(i.publisher_norm) LIKE LOWER(:publisher)"
                    params["publisher"] = f"%{publisher}%"

                sql += " ORDER BY r.mms_id LIMIT :limit"
                params["limit"] = search_limit

                cursor = conn.execute(sql, params)
                search_results = cursor.fetchall()
                conn.close()

                # Get existing candidates and labels for this query
                labels = get_labels_for_query(selected_query_id)
                candidate_ids = set()
                fn_ids = set()

                # Get candidate IDs from the original result
                try:
                    plan_data = json.loads(selected_query['plan_json'])
                    # Note: We don't have candidates stored, so we check labels
                    for label in labels:
                        if label['label'] in ['TP', 'FP']:
                            candidate_ids.add(label['record_id'])
                        if label['label'] == 'FN':
                            fn_ids.add(label['record_id'])
                except:
                    pass

                st.session_state['search_results'] = search_results
                st.session_state['candidate_ids'] = candidate_ids
                st.session_state['fn_ids'] = fn_ids
                st.session_state['selected_query_id'] = selected_query_id

                st.success(f"✅ Found {len(search_results)} matching records")

            except Exception as e:
                st.error(f"❌ Search error: {e}")
                st.stop()

    # Display Results
    if 'search_results' in st.session_state:
        search_results = st.session_state['search_results']
        candidate_ids = st.session_state['candidate_ids']
        fn_ids = st.session_state['fn_ids']
        query_id = st.session_state['selected_query_id']

        st.divider()
        st.header("3. Search Results")
        st.markdown(f"**{len(search_results)} records found** - Mark any that should have matched the query as False Negatives.")

        if not search_results:
            st.info("No results found. Try adjusting your search criteria.")
            st.stop()

        # Display results table with actions
        for idx, row in enumerate(search_results):
            record_id = row['mms_id']
            publisher_val = row['publisher_norm'] or 'N/A'
            place_val = row['place_norm'] or 'N/A'
            date_range = f"{row['date_start']}-{row['date_end']}" if row['date_start'] else 'N/A'

            # Status indicators
            in_candidates = record_id in candidate_ids
            already_fn = record_id in fn_ids

            # Row layout
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 1, 2])

            with col1:
                st.write(f"**{record_id}**")

            with col2:
                st.write(f"📖 {publisher_val[:30]}")

            with col3:
                st.write(f"📍 {place_val[:30]}")

            with col4:
                st.write(f"📅 {date_range}")

            with col5:
                if already_fn:
                    st.write("🏷️ Already FN")
                elif in_candidates:
                    st.write("✅ In results")
                else:
                    # Mark as FN button
                    if st.button(f"➕ Mark as FN", key=f"fn_{idx}"):
                        st.session_state[f'show_fn_form_{idx}'] = True
                        st.rerun()

            # Show FN form if button clicked
            if st.session_state.get(f'show_fn_form_{idx}', False):
                with st.container(border=True):
                    st.write(f"**Mark {record_id} as False Negative**")

                    col1, col2 = st.columns(2)

                    with col1:
                        issue_tag = st.selectbox(
                            "Issue Tag",
                            options=[''] + ISSUE_TAGS,
                            key=f"tag_{idx}",
                            help="Select the reason this was missed"
                        )

                    with col2:
                        note = st.text_input(
                            "Note (optional)",
                            key=f"note_{idx}",
                            help="Additional details"
                        )

                    col1, col2 = st.columns([1, 1])

                    with col1:
                        if st.button("💾 Save FN", key=f"save_{idx}", type="primary"):
                            issue_tags_list = [issue_tag] if issue_tag else []
                            upsert_label(
                                query_id=query_id,
                                record_id=record_id,
                                label="FN",
                                issue_tags=issue_tags_list if issue_tags_list else None,
                                note=note if note else None
                            )
                            st.success(f"✅ Marked {record_id} as FN")
                            del st.session_state[f'show_fn_form_{idx}']
                            # Update fn_ids
                            fn_ids.add(record_id)
                            st.session_state['fn_ids'] = fn_ids
                            st.rerun()

                    with col2:
                        if st.button("Cancel", key=f"cancel_{idx}"):
                            del st.session_state[f'show_fn_form_{idx}']
                            st.rerun()

            st.divider()

else:
    st.info("👆 Configure search criteria and click 'Search Database' to find potential false negatives.")
