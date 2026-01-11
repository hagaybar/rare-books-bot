"""Page 3: Dashboard - Analytics and issue tracking."""
import sys
import pathlib

# Ensure the root directory is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT))

import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
from app.ui_qa.db import (
    get_label_stats,
    get_worst_queries,
    get_query_by_id,
    get_labels_for_query
)
from app.ui_qa.config import ISSUE_TAGS, LABEL_TYPES

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")

st.title("📊 Issues Dashboard")
st.markdown("Analyze labeling patterns and identify problem queries.")

# Stats Section
st.header("Overview")

stats = get_label_stats()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Queries Reviewed",
        stats['queries_reviewed'],
        help="Queries with at least one label"
    )

with col2:
    st.metric(
        "True Positives",
        stats['tp_count'],
        delta_color="normal"
    )

with col3:
    st.metric(
        "False Positives",
        stats['fp_count'],
        delta_color="inverse"
    )

with col4:
    st.metric(
        "False Negatives",
        stats['fn_count'],
        delta_color="inverse"
    )

st.divider()

# Issue Tags Analysis
st.header("Issue Analysis")

# Get all labels with issue tags
import sqlite3
from app.ui_qa.config import QA_DB_PATH

conn = sqlite3.connect(str(QA_DB_PATH))
conn.row_factory = sqlite3.Row

cursor = conn.execute("""
    SELECT issue_tags, label, COUNT(*) as count
    FROM qa_candidate_labels
    WHERE issue_tags IS NOT NULL
    GROUP BY issue_tags, label
""")

issue_tag_data = cursor.fetchall()
conn.close()

# Parse issue tags and aggregate
tag_counts = {}
for row in issue_tag_data:
    try:
        tags = json.loads(row['issue_tags'])
        for tag in tags:
            if tag not in tag_counts:
                tag_counts[tag] = 0
            tag_counts[tag] += row['count']
    except:
        pass

if tag_counts:
    # Sort by count
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Top Issue Tags")
        # Create bar chart
        tag_df = pd.DataFrame(sorted_tags, columns=['Issue Tag', 'Count'])
        st.bar_chart(tag_df.set_index('Issue Tag'))

    with col2:
        st.subheader("Issue Counts")
        for tag, count in sorted_tags:
            st.write(f"**{tag}:** {count}")
else:
    st.info("No issue tags recorded yet. Label some false positives/negatives with issue tags on Page 1.")

st.divider()

# Worst Queries Section
st.header("Problem Queries")
st.markdown("Queries sorted by number of false positives + false negatives.")

worst_queries = get_worst_queries(limit=20)

if worst_queries:
    # Display as table
    worst_df = pd.DataFrame([
        {
            'Query': q['query_text'][:60],
            'Created': q['created_at'][:19],
            'FP': q['fp_count'],
            'FN': q['fn_count'],
            'Total Issues': q['fp_count'] + q['fn_count'],
            'query_id': q['id']
        }
        for q in worst_queries
    ])

    # Display table with selection
    event = st.dataframe(
        worst_df.drop('query_id', axis=1),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # Query Detail Modal
    if event.selection.rows:
        selected_idx = event.selection.rows[0]
        selected_query_id = worst_df.iloc[selected_idx]['query_id']
        query = get_query_by_id(selected_query_id)
        labels = get_labels_for_query(selected_query_id)

        st.divider()

        st.subheader(f"Query Detail: {query['query_text']}")

        # Query metadata
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**Created:** {query['created_at'][:19]}")
        with col2:
            st.write(f"**Status:** {query['status']}")
        with col3:
            st.write(f"**Total Candidates:** {query['total_candidates']}")

        # Show plan and SQL
        col1, col2 = st.columns(2)

        with col1:
            with st.expander("📋 Query Plan", expanded=False):
                try:
                    plan_data = json.loads(query['plan_json'])
                    st.json(plan_data)
                except:
                    st.write("Error parsing plan")

        with col2:
            with st.expander("🔍 SQL", expanded=False):
                st.code(query['sql_text'], language="sql")

        # Labels breakdown
        st.subheader("Labels Breakdown")

        label_counts = {'TP': 0, 'FP': 0, 'FN': 0, 'UNK': 0}
        fp_labels = []
        fn_labels = []

        for label in labels:
            label_counts[label['label']] = label_counts.get(label['label'], 0) + 1
            if label['label'] == 'FP':
                fp_labels.append(label)
            elif label['label'] == 'FN':
                fn_labels.append(label)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("TP", label_counts['TP'])
        col2.metric("FP", label_counts['FP'])
        col3.metric("FN", label_counts['FN'])
        col4.metric("UNK", label_counts['UNK'])

        # Show FP details
        if fp_labels:
            st.subheader("False Positives")
            fp_data = []
            for label in fp_labels:
                issue_tags = json.loads(label['issue_tags']) if label['issue_tags'] else []
                fp_data.append({
                    'Record ID': label['record_id'],
                    'Issue Tags': ', '.join(issue_tags) if issue_tags else 'None',
                    'Note': label['note'] or ''
                })
            st.dataframe(pd.DataFrame(fp_data), use_container_width=True, hide_index=True)

        # Show FN details
        if fn_labels:
            st.subheader("False Negatives")
            fn_data = []
            for label in fn_labels:
                issue_tags = json.loads(label['issue_tags']) if label['issue_tags'] else []
                fn_data.append({
                    'Record ID': label['record_id'],
                    'Issue Tags': ', '.join(issue_tags) if issue_tags else 'None',
                    'Note': label['note'] or ''
                })
            st.dataframe(pd.DataFrame(fn_data), use_container_width=True, hide_index=True)

else:
    st.info("No queries with FP/FN labels yet. Label some queries on Page 1 to see them here.")
