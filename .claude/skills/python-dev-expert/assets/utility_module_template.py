"""
[Utility Module Name] - [Brief description]

This module provides utility functions for [purpose].

Common use cases:
- [Use case 1]
- [Use case 2]
- [Use case 3]
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime


def [function_name](param1: str, param2: Optional[int] = None) -> Any:
    """[Brief description of what function does].

    Args:
        param1: Description of param1
        param2: Description of param2 (optional)

    Returns:
        Description of return value

    Raises:
        ValueError: If parameters are invalid
        TypeError: If parameter types are incorrect

    Example:
        >>> result = [function_name]('value', 123)
        >>> print(result)
        expected_output
    """
    # Validate inputs
    if not param1:
        raise ValueError("param1 is required")

    # Implementation
    result = None  # Your logic here

    return result


def extract_field(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """Safely extract nested field from dictionary using dot notation.

    Supports both dictionary and list navigation.

    Args:
        data: Source dictionary
        path: Dot-separated path (e.g., 'user.contact.email.0.address')
        default: Default value if path not found

    Returns:
        Extracted value or default

    Example:
        >>> data = {'user': {'contact': {'email': [{'address': 'test@example.com'}]}}}
        >>> extract_field(data, 'user.contact.email.0.address')
        'test@example.com'
        >>> extract_field(data, 'user.contact.phone', default='N/A')
        'N/A'
    """
    keys = path.split('.')
    current = data

    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        elif isinstance(current, list) and key.isdigit():
            idx = int(key)
            current = current[idx] if idx < len(current) else default
        else:
            return default

        if current is None:
            return default

    return current


def format_alma_date(date: Union[datetime, str], include_time: bool = False) -> str:
    """Format date for Alma API consumption.

    Alma API expects dates in ISO 8601 format with timezone.

    Args:
        date: datetime object or ISO string
        include_time: Whether to include time component

    Returns:
        Formatted date string (YYYY-MM-DDZ or YYYY-MM-DDTHH:MM:SSZ)

    Example:
        >>> format_alma_date(datetime(2025, 1, 7))
        '2025-01-07Z'
        >>> format_alma_date(datetime(2025, 1, 7, 14, 30), include_time=True)
        '2025-01-07T14:30:00Z'
    """
    if isinstance(date, str):
        # Parse if string
        date = datetime.fromisoformat(date.replace('Z', ''))

    if include_time:
        return date.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        return date.strftime("%Y-%m-%dZ")


def parse_alma_date(date_str: str) -> Optional[datetime]:
    """Parse Alma API date string to datetime object.

    Handles both date-only and date-time formats.

    Args:
        date_str: Date string from Alma API

    Returns:
        datetime object or None if invalid

    Example:
        >>> parse_alma_date('2025-01-07Z')
        datetime(2025, 1, 7, 0, 0)
        >>> parse_alma_date('2025-01-07T14:30:00Z')
        datetime(2025, 1, 7, 14, 30)
    """
    if not date_str:
        return None

    try:
        # Remove timezone indicator
        date_str = date_str.replace('Z', '')

        # Try datetime format first
        if 'T' in date_str:
            return datetime.fromisoformat(date_str)
        else:
            # Date only
            return datetime.strptime(date_str, "%Y-%m-%d")

    except ValueError:
        return None


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split list into chunks of specified size.

    Args:
        items: List to chunk
        chunk_size: Size of each chunk

    Returns:
        List of chunks

    Example:
        >>> chunk_list([1, 2, 3, 4, 5], 2)
        [[1, 2], [3, 4], [5]]
    """
    chunks = []
    for i in range(0, len(items), chunk_size):
        chunks.append(items[i:i + chunk_size])
    return chunks


def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """Sanitize filename by removing/replacing invalid characters.

    Args:
        filename: Original filename
        replacement: Character to replace invalid chars with

    Returns:
        Sanitized filename

    Example:
        >>> sanitize_filename('report: 2025-01-07.csv')
        'report_ 2025-01-07.csv'
    """
    import re
    # Remove invalid filename characters
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, replacement, filename)
    return sanitized


def truncate_string(text: str, max_length: int, suffix: str = '...') -> str:
    """Truncate string to maximum length with suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add if truncated

    Returns:
        Truncated string

    Example:
        >>> truncate_string('This is a very long string', 15)
        'This is a ve...'
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def merge_dicts(*dicts: Dict[str, Any], deep: bool = False) -> Dict[str, Any]:
    """Merge multiple dictionaries into one.

    Args:
        *dicts: Dictionaries to merge (later dicts override earlier)
        deep: Whether to perform deep merge

    Returns:
        Merged dictionary

    Example:
        >>> merge_dicts({'a': 1}, {'b': 2}, {'a': 3})
        {'a': 3, 'b': 2}
    """
    if not deep:
        # Shallow merge
        result = {}
        for d in dicts:
            result.update(d)
        return result
    else:
        # Deep merge
        from copy import deepcopy
        result = deepcopy(dicts[0]) if dicts else {}

        for d in dicts[1:]:
            for key, value in d.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = merge_dicts(result[key], value, deep=True)
                else:
                    result[key] = deepcopy(value)

        return result
