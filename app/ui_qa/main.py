"""M4 Query QA Tool - Streamlit App Entry Point.

Run with: poetry run streamlit run app/ui_qa/main.py
"""
import sys
import pathlib

# Ensure the root directory is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

import streamlit as st
from app.ui_qa.db import init_db

# Page config
st.set_page_config(
    page_title="M4 Query QA Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database on first run
if 'db_initialized' not in st.session_state:
    init_db()
    st.session_state['db_initialized'] = True

# Main page
st.title("🔍 M4 Query QA Tool")
st.markdown("""
Welcome to the M4 Query QA Tool! This tool helps you test queries, label results, and export regression sets.

### Getting Started

Use the sidebar to navigate between pages:

1. **Run + Review** - Execute queries and label candidates (TP/FP/FN)
2. **Find Missing** - Search for false negatives (records that should have matched)
3. **Dashboard** - Analyze issues across all queries
4. **Gold Set** - Export gold.json for regression testing

### Quick Reference

**Label Types:**
- **TP** (True Positive) - Correctly returned result
- **FP** (False Positive) - Incorrectly returned result
- **FN** (False Negative) - Should have been returned but wasn't
- **UNK** (Unknown) - Not yet labeled

**Common Workflow:**
1. Run a query on Page 1
2. Label all results as TP/FP
3. Search for missing results on Page 2 and mark as FN
4. Export gold set on Page 4
5. Run regression tests
""")

st.info("👈 Select a page from the sidebar to get started!")
