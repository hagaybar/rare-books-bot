---
name: python-dev-expert
description: General Python development best practices and patterns. Use this skill when (1) Writing new Python code with emphasis on clean architecture, (2) Refactoring existing code to improve maintainability or reduce duplication, (3) Making architectural decisions about file organization, class structure, or module design, (4) Reviewing code quality for PEP 8 compliance, type hints, or documentation, (5) Ensuring functions are single-purpose and under 50 lines with emphasis on logic density and composition over inheritance, (6) Writing testable, deterministic code.
---

# Python Development Expert

Expert guidance for Python coding, refactoring, and architectural decisions following industry best practices.

## Core Principles

### Code Quality Standards

**Readability First**:
- Code is read 10x more than written
- Clear names > clever tricks
- Explicit > implicit
- Simple > complex

**Testability**:
- Write deterministic code (same input → same output)
- Avoid side effects where possible
- Separate I/O from logic
- Pure functions are easier to test

**Maintainability**:
- Functions should do one thing well
- Maximum 50 lines per function
- DRY (Don't Repeat Yourself) - extract after 3rd duplication
- Composition over inheritance

## Research & Documentation Skill
- When asked about Python libraries (e.g., pymarc, pandas, rdflib), always trigger `context7` to fetch current documentation.
- Prioritize memory-efficient streaming patterns for MARC record processing.
- Verify all Angular component syntax against latest documentation before writing code.

## Quick Decision Trees

### Should I Create a New File?

**New Module** → Create when:
- Grouping related functionality (e.g., date utilities, file operations)
- Code is reused across 3+ places
- Module has clear, single responsibility
- Creating a new domain concept or abstraction

**New Package** → Create when:
- Multiple related modules form a cohesive unit
- Clear hierarchy emerges (e.g., parsers, validators, formatters)
- Need to organize growing codebase

**DO NOT create new file** when:
- Function belongs in existing module
- Code is used in only 1-2 places (inline it or extract to method)
- Creating file just to "organize" without clear responsibility

### Should I Refactor This Code?

**YES - Refactor immediately** when:
- Function exceeds 50 lines
- Same logic appears in 3+ places
- Function does multiple unrelated things
- Complex nested conditions (>3 levels deep)
- Variable names are cryptic (x, data, temp, etc.)

**MAYBE - Consider refactoring** when:
- Missing type hints or docstrings
- Magic numbers or hardcoded values
- Function has >5 parameters
- Deep inheritance hierarchy (>3 levels)

**NO - Leave as-is** when:
- Code is clear and works correctly
- Refactoring would not improve readability
- One-time use code (scripts, migrations)
- Optimization would be premature

## Logic Density Principles

### Keep Functions Focused and Concise

**Core Rules**:
- **Maximum 50 lines** per function
- **Single purpose** - One function = One clear responsibility
- **Composition over inheritance** - Prefer composing objects over deep inheritance
- **Extract early** - If you think "this could be extracted," do it now

**Example of good logic density**:

```python
# GOOD - Single purpose, under 50 lines, clear responsibility
def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email or '@' not in email:
        return False
    local, domain = email.rsplit('@', 1)
    return bool(local) and '.' in domain

def filter_valid_emails(emails: list[str]) -> list[str]:
    """Filter list to only valid email addresses."""
    return [email for email in emails if validate_email(email)]

def send_notifications(emails: list[str], message: str) -> dict[str, bool]:
    """Send email notifications and return success status."""
    valid_emails = filter_valid_emails(emails)
    results = {}
    for email in valid_emails:
        results[email] = _send_email(email, message)
    return results

# BAD - Multiple purposes, >50 lines, does everything
def process_and_send_emails(emails: list[str], message: str) -> dict[str, bool]:
    """Validate, filter, and send emails."""  # Too many responsibilities!
    results = {}
    for email in emails:
        # 10 lines of email validation
        # 15 lines of filtering logic
        # 20 lines of sending logic
        # Total: 45+ lines doing multiple things
    return results
```

## Code Organization Patterns

### Module Structure

```python
"""Module docstring explaining purpose.

This module provides utilities for [specific functionality].
Common use cases include [examples].
"""

# Standard library imports
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

# Third-party imports
import requests
from pydantic import BaseModel

# Local imports
from .models import User
from .utils import logger

# Module-level constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

# Public API (optional - what should be imported with `from module import *`)
__all__ = ['function_name', 'ClassName']


class ClassName:
    """Class for [purpose]."""

    def __init__(self, param: str):
        """Initialize with parameters."""
        self.param = param

    def public_method(self) -> str:
        """Public API method."""
        return self._private_method()

    def _private_method(self) -> str:
        """Internal helper (underscore prefix)."""
        return self.param


def public_function(arg: str) -> str:
    """Public function with clear docstring."""
    return _helper_function(arg)


def _helper_function(arg: str) -> str:
    """Private helper function (underscore prefix)."""
    return arg.upper()
```

### Type Hints Best Practices

```python
from typing import Dict, List, Optional, Union, Tuple, Any
from pathlib import Path

# Basic types
def process_text(text: str, count: int = 10) -> str:
    """Process text with type hints."""
    pass

# Optional parameters
def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load config file, path is optional."""
    pass

# Union types
def parse_input(value: Union[str, int, float]) -> float:
    """Accept multiple input types."""
    return float(value)

# Complex return types
def get_user_data(user_id: str) -> Tuple[str, int, List[str]]:
    """Return tuple of (name, age, tags)."""
    return ("Alice", 30, ["admin", "user"])

# Accepting callables
from typing import Callable

def apply_transform(data: List[int], func: Callable[[int], int]) -> List[int]:
    """Apply transformation function to each element."""
    return [func(x) for x in data]
```

### Dataclasses and Models

```python
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

# Simple dataclass
@dataclass
class User:
    """User data model."""
    id: str
    name: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)
    metadata: Optional[dict] = None

# With validation (using Pydantic)
from pydantic import BaseModel, validator

class UserModel(BaseModel):
    """User model with validation."""
    id: str
    name: str
    email: str
    age: int

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email')
        return v

    @validator('age')
    def validate_age(cls, v):
        if v < 0 or v > 150:
            raise ValueError('Invalid age')
        return v
```

## Common Refactoring Patterns

### Extract Method

**Before**:
```python
def process_order(order: dict) -> dict:
    # Calculate total
    total = 0
    for item in order['items']:
        price = item['price']
        quantity = item['quantity']
        discount = item.get('discount', 0)
        total += (price * quantity) * (1 - discount)

    # Apply shipping
    if total > 100:
        shipping = 0
    elif total > 50:
        shipping = 5
    else:
        shipping = 10

    return {'total': total, 'shipping': shipping, 'final': total + shipping}
```

**After**:
```python
def calculate_item_price(item: dict) -> float:
    """Calculate price for single item with discount."""
    price = item['price']
    quantity = item['quantity']
    discount = item.get('discount', 0)
    return (price * quantity) * (1 - discount)

def calculate_shipping(total: float) -> float:
    """Calculate shipping cost based on order total."""
    if total > 100:
        return 0
    elif total > 50:
        return 5
    return 10

def process_order(order: dict) -> dict:
    """Process order and calculate final price."""
    total = sum(calculate_item_price(item) for item in order['items'])
    shipping = calculate_shipping(total)
    return {'total': total, 'shipping': shipping, 'final': total + shipping}
```

### Replace Magic Numbers with Constants

**Before**:
```python
def calculate_tax(amount: float) -> float:
    return amount * 0.07  # What is 0.07?

def is_premium(score: int) -> bool:
    return score > 850  # What is 850?
```

**After**:
```python
TAX_RATE = 0.07
PREMIUM_THRESHOLD = 850

def calculate_tax(amount: float) -> float:
    """Calculate sales tax."""
    return amount * TAX_RATE

def is_premium(score: int) -> bool:
    """Check if score qualifies for premium tier."""
    return score > PREMIUM_THRESHOLD
```

### Simplify Conditionals

**Before**:
```python
def get_discount(user: dict) -> float:
    if user.get('is_member'):
        if user.get('years') > 5:
            if user.get('purchases') > 100:
                return 0.25
            else:
                return 0.15
        else:
            return 0.10
    else:
        return 0.0
```

**After**:
```python
def get_discount(user: dict) -> float:
    """Calculate user discount based on membership status."""
    if not user.get('is_member'):
        return 0.0

    years = user.get('years', 0)
    purchases = user.get('purchases', 0)

    if years > 5 and purchases > 100:
        return 0.25
    elif years > 5:
        return 0.15
    else:
        return 0.10
```

## Error Handling Best Practices

### Be Specific with Exceptions

```python
# GOOD - Specific exceptions
def load_file(path: Path) -> str:
    """Load file content."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    try:
        return path.read_text()
    except PermissionError as e:
        raise PermissionError(f"Cannot read file {path}: {e}")

# BAD - Generic exceptions
def load_file(path: Path) -> str:
    try:
        return path.read_text()
    except Exception as e:  # Too broad!
        raise Exception(f"Error: {e}")
```

### Context Managers for Resource Management

```python
from contextlib import contextmanager

@contextmanager
def database_connection(db_url: str):
    """Context manager for database connection."""
    conn = create_connection(db_url)
    try:
        yield conn
    finally:
        conn.close()

# Usage
with database_connection("postgresql://...") as conn:
    result = conn.execute("SELECT * FROM users")
```

## Testing Best Practices

### Write Testable Code

```python
# HARD TO TEST - Embedded dependencies
def send_report():
    db = DatabaseConnection()  # Hard to mock
    users = db.get_users()
    email = EmailService()  # Hard to mock
    for user in users:
        email.send(user.email, "Report")

# EASY TO TEST - Dependency injection
def send_report(users: List[User], email_service: EmailService):
    """Send report to users via email service."""
    for user in users:
        email_service.send(user.email, "Report")

# Test example
def test_send_report():
    users = [User(email="test@example.com")]
    mock_email = MockEmailService()
    send_report(users, mock_email)
    assert mock_email.sent_count == 1
```

### Keep Tests Simple and Focused

```python
import pytest

def test_validate_email_with_valid_email():
    """Test email validation with valid input."""
    assert validate_email("user@example.com") is True

def test_validate_email_with_invalid_email():
    """Test email validation with invalid input."""
    assert validate_email("invalid") is False

def test_validate_email_with_empty_string():
    """Test email validation with empty input."""
    assert validate_email("") is False

@pytest.mark.parametrize("email,expected", [
    ("user@example.com", True),
    ("invalid", False),
    ("", False),
    ("user@", False),
    ("@example.com", False),
])
def test_validate_email_parametrized(email: str, expected: bool):
    """Test email validation with various inputs."""
    assert validate_email(email) == expected
```

## Common Anti-Patterns to Avoid

### ❌ Mutable Default Arguments

```python
# BAD - Mutable default
def add_item(item: str, items: list = []):
    items.append(item)
    return items

# GOOD - None default
def add_item(item: str, items: list = None) -> list:
    if items is None:
        items = []
    items.append(item)
    return items
```

### ❌ Catching and Ignoring Exceptions

```python
# BAD - Silent failures
try:
    result = risky_operation()
except:
    pass  # Error lost!

# GOOD - Handle or re-raise
try:
    result = risky_operation()
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    raise  # Re-raise if caller should know
```

### ❌ Using `isinstance` for Type Checking When Not Needed

```python
# BAD - Explicit type checking
def process(value):
    if isinstance(value, str):
        return value.upper()
    elif isinstance(value, int):
        return str(value)
    else:
        raise TypeError("Unsupported type")

# GOOD - Duck typing
def process(value):
    """Process value - expects str-like object."""
    return str(value).upper()
```

## Code Quality Checklist

Before committing code, verify:

**Function Design**:
- [ ] Functions are <50 lines
- [ ] Each function has single, clear purpose
- [ ] Function names are descriptive verbs (get_, calculate_, validate_)
- [ ] No more than 5 parameters per function

**Type Hints & Documentation**:
- [ ] Type hints on all function signatures
- [ ] Docstrings on all public functions/classes
- [ ] Complex logic has inline comments
- [ ] Module has descriptive docstring

**Code Organization**:
- [ ] Imports organized (stdlib → third-party → local)
- [ ] No commented-out code
- [ ] No debug print statements
- [ ] Constants are UPPERCASE
- [ ] Private functions/methods use underscore prefix

**Error Handling**:
- [ ] Specific exceptions (not bare except)
- [ ] Meaningful error messages
- [ ] Resources properly closed (use context managers)

**Testing**:
- [ ] Functions are deterministic where possible
- [ ] Side effects are isolated
- [ ] Dependencies can be injected/mocked

## Summary

This skill ensures Python code follows best practices:
- Write clear, maintainable code with single-purpose functions
- Use type hints and comprehensive docstrings
- Follow DRY principle and extract duplicated logic
- Handle errors explicitly with specific exceptions
- Write testable, deterministic code
- Organize imports and modules logically
- Avoid common anti-patterns
