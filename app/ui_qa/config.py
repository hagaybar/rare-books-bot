"""Configuration for QA tool."""
from pathlib import Path

# Database paths
QA_DB_PATH = Path("data/qa/qa.db")
BIBLIO_DB_PATH = Path("data/index/bibliographic.db")

# Output paths
GOLD_SET_PATH = Path("data/qa/gold.json")
QA_DATA_DIR = Path("data/qa")

# Issue tags (predefined list for labeling)
ISSUE_TAGS = [
    "PARSER_MISSED_FILTER",
    "PARSER_WRONG_FILTER",
    "NORM_PLACE_BAD",
    "NORM_PUBLISHER_BAD",
    "DATE_PARSE_BAD",
    "SQL_LOGIC_BAD",
    "EVIDENCE_INSUFFICIENT",
    "OTHER"
]

# Label types
LABEL_TYPES = ["TP", "FP", "FN", "UNK"]

# Default limits
DEFAULT_QUERY_LIMIT = 50
DEFAULT_SEARCH_LIMIT = 50

# Canonical queries for guided QA sessions
CANONICAL_QUERIES = [
    {"id": 1, "query_text": "books between 1500 and 1599", "description": "Basic date range (16th century)"},
    {"id": 2, "query_text": "books between 1550 and 1560", "description": "Narrow date range (decade)"},
    {"id": 3, "query_text": "books printed in Venice between 1550 and 1575", "description": "Place + date"},
    {"id": 4, "query_text": "books printed in Paris between 1500 and 1550", "description": "Place + date (early century)"},
    {"id": 5, "query_text": "books published by Oxford between 1500 and 1600", "description": "Publisher + date"},
    {"id": 6, "query_text": "books published by Aldus Manutius", "description": "Specific publisher"},
    {"id": 7, "query_text": "books in Latin between 1500 and 1600", "description": "Language + date"},
    {"id": 8, "query_text": "books from the 16th century", "description": "Century mention"},
    {"id": 9, "query_text": "books printed in Italy between 1500 and 1599", "description": "Country + date"},
    {"id": 10, "query_text": "books before 1500", "description": "Incunabula (pre-1500)"},
    {"id": 11, "query_text": "books between 1600 and 1650", "description": "17th century range"},
    {"id": 12, "query_text": "books published in London", "description": "Place only"},
    {"id": 13, "query_text": "books in Greek", "description": "Language only"},
    {"id": 14, "query_text": "books printed in Basel by Froben", "description": "Place + publisher"},
    {"id": 15, "query_text": "books from 1520", "description": "Single year"},
]
