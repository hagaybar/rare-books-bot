"""Subject heading hints for query retry mechanism.

Extracts actual subject headings from database to help LLM map user queries
to controlled vocabulary when initial attempt returns zero results.
"""

import sqlite3
from pathlib import Path
from typing import List


def get_top_subjects(db_path: Path, limit: int = 100) -> List[str]:
    """Extract most frequently used subjects from database.
    
    Returns subjects ordered by frequency (most common first). These are used
    as hints to the LLM when retrying queries that had subject filters but
    returned zero results.
    
    Args:
        db_path: Path to SQLite database (bibliographic.db)
        limit: Maximum number of subjects to return (default 100)
        
    Returns:
        List of subject values like ["History", "Philosophy", "Literature", ...]
        
    Example:
        >>> hints = get_top_subjects(Path("data/index/bibliographic.db"))
        >>> print(hints[:5])
        ['History', 'Philosophy', 'Literature', 'Science', 'Biography']
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Get subjects ordered by frequency
    # Note: value is the display string (e.g., "History -- France")
    query = """
        SELECT value, COUNT(*) as count
        FROM subjects
        GROUP BY value
        ORDER BY count DESC
        LIMIT ?
    """
    
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    # Extract just the values (ignore counts)
    subjects = [row[0] for row in rows]
    
    return subjects
