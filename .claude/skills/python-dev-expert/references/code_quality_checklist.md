# Code Quality Checklist

Use this checklist before committing code to ensure quality standards.

## Pre-Commit Checklist

### 1. Function Quality

- [ ] All functions under 50 lines
- [ ] Each function has single, clear purpose
- [ ] No deeply nested conditionals (>3 levels)
- [ ] Early returns used for error cases (guard clauses)
- [ ] No commented-out code

### 2. Type Hints

- [ ] All function parameters have type hints
- [ ] All function return values have type hints
- [ ] Complex types use proper imports (`from typing import Dict, List, Optional`)
- [ ] Type hints are accurate (not just `Any` everywhere)

**Example**:
```python
# GOOD
def get_user(self, user_id: str) -> Dict[str, Any]:
    pass

def filter_users(self, users: List[Dict[str, Any]], status: str) -> List[Dict[str, Any]]:
    pass

# BAD
def get_user(self, user_id):  # Missing type hints
    pass

def filter_users(self, users, status):  # Missing type hints
    pass
```

### 3. Docstrings

- [ ] All public methods have docstrings
- [ ] Docstrings follow Google/NumPy style
- [ ] Includes: description, Args, Returns, Raises
- [ ] Private methods (`_method`) have brief docstrings

**Template**:
```python
def method_name(self, param1: str, param2: int) -> Dict[str, Any]:
    """Brief description of what method does.

    More detailed explanation if needed (optional).

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        AlmaAPIError: When API call fails
        AlmaValidationError: When validation fails
    """
    pass
```

### 4. Import Organization

- [ ] Imports organized in 3 groups (stdlib, third-party, local)
- [ ] Alphabetically sorted within each group
- [ ] No unused imports
- [ ] No wildcard imports (`from module import *`)

**Correct order**:
```python
# 1. Standard library
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

# 2. Third-party
import requests

# 3. Local
from src.client.AlmaAPIClient import AlmaAPIClient
from src.logging import get_logger
```

### 5. Variable Naming

- [ ] Variables have descriptive names
- [ ] No single-letter variables (except loop counters)
- [ ] No generic names (`data`, `result`, `temp`, `x`)
- [ ] Constants in UPPER_CASE
- [ ] Private variables/methods start with `_`

**Examples**:
```python
# GOOD
user_data = response.json()
active_users = [u for u in users if u['status'] == 'ACTIVE']
MAX_RETRIES = 3

# BAD
d = response.json()
x = [u for u in users if u['status'] == 'ACTIVE']
max_retries = 3  # Should be UPPER_CASE constant
```

### 6. Error Handling

- [ ] Use AlmaAPIError hierarchy (AlmaAPIError, AlmaValidationError, etc.)
- [ ] Include context in error messages
- [ ] Log errors before re-raising
- [ ] Don't catch exceptions silently
- [ ] Use specific exceptions (not bare `except:`)

**Pattern**:
```python
try:
    result = self.client.get(endpoint)
except AlmaAPIError as e:
    self.logger.error("Operation failed",
                     resource_id=resource_id,
                     error_code=e.status_code,
                     error_message=str(e))
    raise  # Re-raise after logging
```

### 7. Logging

- [ ] All API operations are logged (entry and completion)
- [ ] Errors are logged with context
- [ ] Use structured logging (key-value pairs, not string concatenation)
- [ ] Appropriate log levels (DEBUG, INFO, WARNING, ERROR)
- [ ] No API keys or sensitive data in logs

**Pattern**:
```python
self.logger.info("Retrieving user", user_id=user_id)
try:
    user = self.client.get(f"almaws/v1/users/{user_id}").json()
    self.logger.info("User retrieved successfully", user_id=user_id)
    return user
except AlmaAPIError as e:
    self.logger.error("Failed to retrieve user",
                     user_id=user_id,
                     error_code=e.status_code)
    raise
```

### 8. Security

- [ ] No hardcoded API keys or passwords
- [ ] Environment variables used for secrets
- [ ] No sensitive data in logs
- [ ] Input validation for all external input
- [ ] SQL injection prevention (if using SQL)

### 9. Code Organization

- [ ] Related functions grouped together
- [ ] Public methods before private methods
- [ ] No dead code (unused functions, commented code)
- [ ] No TODO comments without tickets/issues
- [ ] Files under 500 lines (split if larger)

### 10. Testing Considerations

- [ ] Functions are testable (not too complex)
- [ ] Side effects are isolated
- [ ] Dependencies are injectable (not hardcoded)
- [ ] Edge cases are handled

## PEP 8 Standards

### Line Length

- Maximum 100 characters per line (project standard, not PEP 8's 79)
- Break long lines logically

```python
# GOOD - Breaking at logical points
result = some_long_function_name(
    first_parameter,
    second_parameter,
    third_parameter
)

# GOOD - Breaking long strings
error_message = (
    "This is a very long error message that needs to be broken "
    "across multiple lines for readability"
)
```

### Indentation

- 4 spaces per indentation level
- No tabs
- Continuation lines should align with opening delimiter

```python
# GOOD
my_list = [
    1, 2, 3,
    4, 5, 6,
]

# GOOD
result = function_name(
    parameter1,
    parameter2,
    parameter3
)
```

### Whitespace

- No trailing whitespace
- Blank line after imports
- Two blank lines between top-level definitions
- One blank line between methods

```python
import os
from typing import Dict

# Two blank lines

class MyClass:
    def method1(self):
        pass

    # One blank line

    def method2(self):
        pass
```

### Naming Conventions

- Classes: `PascalCase`
- Functions/Methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private members: `_leading_underscore`
- Module names: `snake_case.py`

## Project-Specific Standards

### Alma API Naming

Use Alma terminology consistently:
- `mms_id` (not `record_id`, `bib_id`)
- `user_primary_id` (not `user_id`, `username`)
- `pol_id` (not `order_id`, `purchase_order`)
- `set_id` (not `collection_id`)

### Date Formatting

Use ISO 8601 format with timezone:
```python
# GOOD
date_str = "2025-01-07Z"
date_obj = datetime(2025, 1, 7)

# For Alma API dates
def format_alma_date(date: datetime) -> str:
    """Format date for Alma API."""
    return date.strftime("%Y-%m-%dZ")
```

### Environment Handling

```python
# GOOD - Explicit environment check
if client.environment == 'PRODUCTION':
    # Production-only logic
    pass

# GOOD - Safety confirmation
if environment == 'PRODUCTION' and not dry_run:
    confirm = input("Execute in PRODUCTION? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Aborted")
        return
```

### CLI Script Standards

All project scripts must include:
- `--environment` choice (SANDBOX/PRODUCTION)
- `--dry-run` default behavior
- `--live` flag to disable dry-run
- `--config` option for JSON config file
- Comprehensive help text

```python
parser = argparse.ArgumentParser(description="Script description")
parser.add_argument("--environment",
                   choices=["SANDBOX", "PRODUCTION"],
                   default="SANDBOX",
                   help="Alma environment")
parser.add_argument("--dry-run",
                   action="store_true",
                   default=True,
                   help="Dry-run mode (default)")
parser.add_argument("--live",
                   action="store_true",
                   help="Disable dry-run mode")
parser.add_argument("--config",
                   help="JSON configuration file")
```

## Quick Reference Card

### Before Committing, Ask:

1. **Is every function under 50 lines?** → Extract methods if not
2. **Does each function do one thing?** → Split if not
3. **Are all type hints present?** → Add them
4. **Are all docstrings present?** → Write them
5. **Are imports organized?** → Reorder them
6. **Are variable names clear?** → Rename if not
7. **Is error handling proper?** → Use AlmaAPIError hierarchy
8. **Is logging comprehensive?** → Add structured logging
9. **Are there hardcoded values?** → Extract to constants/config
10. **Is there dead code?** → Remove it

### Red Flags

❌ Function >50 lines
❌ Missing type hints
❌ Missing docstrings
❌ Generic variable names (`data`, `result`, `x`)
❌ Commented-out code
❌ Hardcoded API keys
❌ Bare `except:` clauses
❌ No logging for API operations
❌ Code duplication (3+ times)
❌ Deep nesting (>3 levels)
