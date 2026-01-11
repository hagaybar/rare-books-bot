"""Page 5: Database Explorer - Read-only view of bibliographic database tables."""
import sys
import pathlib

# Ensure the root directory is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT))

import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path
from app.ui_qa.config import BIBLIO_DB_PATH

st.set_page_config(page_title="Database Explorer", page_icon="🗄️", layout="wide")

st.title("🗄️ Database Explorer")
st.markdown("Explore tables in the bibliographic database (read-only).")

# Available tables for exploration
AVAILABLE_TABLES = [
    "records",
    "imprints",
    "titles",
    "subjects",
    "languages",
    "agents",
]


def get_readonly_connection(db_path: Path):
    """Get read-only connection to database."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None


def get_table_schema(conn, table_name: str):
    """Get schema information for a table."""
    try:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        return cursor.fetchall()
    except Exception as e:
        st.error(f"Failed to get schema for {table_name}: {e}")
        return []


def get_row_count(conn, table_name: str):
    """Get total row count for a table."""
    try:
        cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        return cursor.fetchone()['count']
    except Exception as e:
        st.error(f"Failed to get row count for {table_name}: {e}")
        return 0


def truncate_long_text(value, max_length=100):
    """Truncate long text values for display."""
    if value is None:
        return None
    text = str(value)
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


# Check if database exists
if not BIBLIO_DB_PATH.exists():
    st.error(f"Database not found at: {BIBLIO_DB_PATH}")
    st.info("Please ensure the bibliographic database has been created.")
    st.stop()

# Database info
st.info(f"📁 Database: `{BIBLIO_DB_PATH}`")

# Table selection
selected_table = st.selectbox("Select Table", AVAILABLE_TABLES, index=0)

if selected_table:
    conn = get_readonly_connection(BIBLIO_DB_PATH)

    if conn is None:
        st.stop()

    # Get schema and row count
    schema = get_table_schema(conn, selected_table)
    row_count = get_row_count(conn, selected_table)

    if not schema:
        st.warning(f"Table '{selected_table}' not found or has no schema.")
        conn.close()
        st.stop()

    st.subheader(f"Table: {selected_table} ({row_count:,} rows)")

    # Show schema in expander
    with st.expander("📋 Schema", expanded=False):
        schema_df = pd.DataFrame([
            {
                "Column": row['name'],
                "Type": row['type'],
                "Not Null": bool(row['notnull']),
                "Default": row['dflt_value'] if row['dflt_value'] else '-',
                "Primary Key": bool(row['pk'])
            }
            for row in schema
        ])
        st.dataframe(schema_df, use_container_width=True, hide_index=True)

    st.divider()

    # Filters section
    st.subheader("🔍 Filters")

    col1, col2, col3 = st.columns(3)

    with col1:
        column_names = [row['name'] for row in schema]
        search_columns = st.multiselect(
            "Search in columns",
            column_names,
            help="Select columns to search in"
        )

    with col2:
        search_text = st.text_input(
            "Contains text",
            help="Case-insensitive search"
        )

    with col3:
        limit = st.number_input(
            "Limit rows",
            min_value=1,
            max_value=500,
            value=50,
            help="Maximum 500 rows"
        )

    # Apply filters button
    if st.button("🔍 Apply Filters", type="primary"):
        # Build query
        sql = f"SELECT * FROM {selected_table}"
        params = []

        if search_text and search_columns:
            # Build WHERE clause with OR conditions
            conditions = [f"{col} LIKE ?" for col in search_columns]
            sql += f" WHERE ({' OR '.join(conditions)})"
            params = [f"%{search_text}%"] * len(search_columns)

        sql += f" LIMIT ?"
        params.append(limit)

        # Execute query
        try:
            with st.spinner("Querying database..."):
                results_cursor = conn.execute(sql, params)
                results = results_cursor.fetchall()

            st.divider()
            st.subheader(f"📊 Results (showing {len(results)} of {row_count:,})")

            if results:
                # Convert to dataframe
                results_df = pd.DataFrame([dict(row) for row in results])

                # Truncate long columns for display
                for col in results_df.columns:
                    if results_df[col].dtype == 'object':
                        results_df[col] = results_df[col].apply(truncate_long_text)

                # Display dataframe
                st.dataframe(
                    results_df,
                    use_container_width=True,
                    hide_index=False,
                    height=400
                )

                # Export and SQL view
                col1, col2 = st.columns(2)

                with col1:
                    # CSV export (use untruncated data)
                    export_df = pd.DataFrame([dict(row) for row in results])
                    csv = export_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv,
                        file_name=f"{selected_table}_export.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with col2:
                    # View SQL button
                    if st.button("📜 View SQL", use_container_width=True):
                        st.session_state['show_sql'] = True

                # Show SQL query in expander (if button clicked)
                if st.session_state.get('show_sql', False):
                    with st.expander("SQL Query", expanded=True):
                        st.code(sql, language="sql")
                        st.write(f"**Parameters:** `{params}`")
                        if st.button("Hide SQL"):
                            st.session_state['show_sql'] = False
                            st.rerun()

            else:
                st.info("No results found. Try adjusting your filters.")

        except Exception as e:
            st.error(f"Query error: {e}")
            st.code(sql, language="sql")
            st.write(f"Parameters: {params}")

    else:
        # Show instruction when no query yet
        st.info("👆 Configure filters above and click 'Apply Filters' to view data.")

    # Close connection
    conn.close()

st.divider()

# Help section
with st.expander("ℹ️ About Database Explorer"):
    st.markdown("""
    ### Purpose

    The Database Explorer provides read-only access to important tables in the bibliographic database.
    Use it during QA sessions to:

    - **Verify normalization quality** (raw → normalized values)
    - **Understand date parsing** (date_start, date_end, parse_method)
    - **Check record details** (MMS IDs, source files)
    - **Inspect subjects and languages** (controlled vocabularies)

    ### Available Tables

    - **records**: Core MARC records (mms_id, source_file, marc_xml)
    - **imprints**: Place, publisher, date information (raw + normalized)
    - **titles**: Title data (main, uniform, etc.) with language
    - **subjects**: Subject headings and types
    - **languages**: Language codes and names
    - **agents**: Authors, publishers, and other agents with roles

    ### Usage Tips

    1. **Search specific fields**: Select columns, then enter search text
    2. **Export for analysis**: Download CSV of filtered results
    3. **Inspect normalization**: Compare raw vs normalized columns in imprints
    4. **Trace issues**: Use record_id to link across tables

    ### Safety Features

    - **Read-only mode**: No writes possible (database opened with mode=ro)
    - **Row limits**: Maximum 500 rows per query (prevents memory issues)
    - **Text truncation**: Long fields (like marc_xml) truncated in display
    - **Export available**: Full data available via CSV download
    """)
