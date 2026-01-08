# Refactoring Workflows

## Code Smells and Solutions

### 1. Long Function (>50 lines)

**Smell**: Function exceeds 50 lines

**Refactoring**: Extract Method

**Before**:
```python
def process_users(self, set_id: str, pattern: str) -> List[Dict]:
    """Process users from set with email updates."""
    users = []
    # Lines 1-20: Fetch users from set
    endpoint = f"almaws/v1/conf/sets/{set_id}/members"
    # ... pagination logic
    # ... user fetching

    # Lines 21-35: Validate emails
    valid_users = []
    for user in users:
        email = user.get('contact_info', {}).get('email', [{}])[0]
        # ... validation logic

    # Lines 36-55: Update emails
    updated = []
    for user in valid_users:
        new_email = pattern.format(user_id=user['primary_id'])
        # ... update logic
    return updated
```

**After**:
```python
def process_users(self, set_id: str, pattern: str) -> List[Dict]:
    """Process users from set with email updates."""
    users = self._fetch_users_from_set(set_id)
    valid_users = self._validate_user_emails(users)
    return self._update_user_emails(valid_users, pattern)

def _fetch_users_from_set(self, set_id: str) -> List[Dict]:
    """Fetch all users from a set."""
    # 15 lines of fetching logic
    pass

def _validate_user_emails(self, users: List[Dict]) -> List[Dict]:
    """Filter users with valid emails."""
    # 10 lines of validation logic
    pass

def _update_user_emails(self, users: List[Dict], pattern: str) -> List[Dict]:
    """Update emails for users."""
    # 15 lines of update logic
    pass
```

### 2. Duplicated Code (3+ occurrences)

**Smell**: Same logic appears in multiple places

**Refactoring**: Extract Utility Function

**Before**:
```python
# In users.py
def get_user_email(self, user_id: str) -> str:
    user = self.get_user(user_id)
    return user.get('contact_info', {}).get('email', [{}])[0].get('email_address', '')

# In admin.py
def check_user_email(self, user_id: str) -> bool:
    user = self.get_user(user_id)
    email = user.get('contact_info', {}).get('email', [{}])[0].get('email_address', '')
    return '@' in email

# In projects/email_script.py
def extract_email(user_data: Dict) -> str:
    return user_data.get('contact_info', {}).get('email', [{}])[0].get('email_address', '')
```

**After**:
```python
# In src/utils/user_utils.py
def extract_user_email(user_data: Dict[str, Any]) -> Optional[str]:
    """Extract primary email from user data.

    Args:
        user_data: User dictionary from Alma API

    Returns:
        Email address or None if not found
    """
    return user_data.get('contact_info', {}).get('email', [{}])[0].get('email_address')

# In users.py
from src.utils.user_utils import extract_user_email

def get_user_email(self, user_id: str) -> Optional[str]:
    user = self.get_user(user_id)
    return extract_user_email(user)
```

### 3. Complex Conditionals (>3 levels)

**Smell**: Deeply nested if/else statements

**Refactoring**: Extract Guard Clauses / Early Returns

**Before**:
```python
def process_invoice(self, invoice_id: str) -> Dict[str, Any]:
    """Process invoice with validation."""
    invoice = self.get_invoice(invoice_id)
    if invoice:
        if invoice.get('status') == 'ACTIVE':
            if invoice.get('total_amount', 0) > 0:
                if len(invoice.get('lines', [])) > 0:
                    return self.approve_invoice(invoice_id)
                else:
                    raise ValueError("No invoice lines")
            else:
                raise ValueError("Invalid amount")
        else:
            raise ValueError("Invalid status")
    else:
        raise ValueError("Invoice not found")
```

**After**:
```python
def process_invoice(self, invoice_id: str) -> Dict[str, Any]:
    """Process invoice with validation."""
    invoice = self.get_invoice(invoice_id)

    # Guard clauses - fail fast
    if not invoice:
        raise ValueError("Invoice not found")

    if invoice.get('status') != 'ACTIVE':
        raise ValueError(f"Invalid status: {invoice.get('status')}")

    if invoice.get('total_amount', 0) <= 0:
        raise ValueError("Invalid amount")

    if not invoice.get('lines', []):
        raise ValueError("No invoice lines")

    # Happy path
    return self.approve_invoice(invoice_id)
```

### 4. Magic Numbers and Hardcoded Values

**Smell**: Unexplained constants in code

**Refactoring**: Extract Constants

**Before**:
```python
def fetch_users(self, set_id: str) -> List[Dict]:
    """Fetch users from set."""
    all_users = []
    offset = 0
    while True:
        params = {"limit": 100, "offset": offset}  # Magic numbers
        response = self.client.get(endpoint, params=params)
        users = response.json().get('member', [])
        if not users:
            break
        all_users.extend(users)
        offset += 100  # Magic number
    return all_users
```

**After**:
```python
# At module level or class level
DEFAULT_PAGE_SIZE = 100
MAX_USERS_PER_REQUEST = 100

def fetch_users(self, set_id: str) -> List[Dict]:
    """Fetch users from set."""
    all_users = []
    offset = 0
    while True:
        params = {"limit": DEFAULT_PAGE_SIZE, "offset": offset}
        response = self.client.get(endpoint, params=params)
        users = response.json().get('member', [])
        if not users:
            break
        all_users.extend(users)
        offset += DEFAULT_PAGE_SIZE
    return all_users
```

### 5. Unclear Variable Names

**Smell**: Variables named `x`, `temp`, `data`, `result`

**Refactoring**: Rename Variables

**Before**:
```python
def process(self, id: str) -> Dict:
    r = self.client.get(f"endpoint/{id}")
    d = r.json()
    x = d.get('items', [])
    y = [i for i in x if i.get('status') == 'ACTIVE']
    return {'data': y, 'count': len(y)}
```

**After**:
```python
def get_active_items(self, resource_id: str) -> Dict[str, Any]:
    """Retrieve active items for resource.

    Args:
        resource_id: Resource identifier

    Returns:
        Dict with 'items' list and 'count'
    """
    response = self.client.get(f"endpoint/{resource_id}")
    resource_data = response.json()
    all_items = resource_data.get('items', [])
    active_items = [item for item in all_items if item.get('status') == 'ACTIVE']
    return {'items': active_items, 'count': len(active_items)}
```

### 6. Multiple Responsibilities

**Smell**: Function does multiple unrelated things

**Refactoring**: Split into Single-Purpose Functions

**Before**:
```python
def process_and_report(self, set_id: str, output_file: str) -> None:
    """Process users and generate report."""
    # Fetch users
    users = self.fetch_users(set_id)

    # Process users
    results = []
    for user in users:
        # ... processing logic
        results.append(processed)

    # Write CSV report
    with open(output_file, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'status'])
        writer.writeheader()
        writer.writerows(results)

    # Send email notification
    subject = "Processing complete"
    body = f"Processed {len(results)} users"
    self.send_email(subject, body)
```

**After**:
```python
def process_users_from_set(self, set_id: str) -> List[Dict[str, Any]]:
    """Process users from set.

    Args:
        set_id: Alma set identifier

    Returns:
        List of processed user results
    """
    users = self._fetch_users(set_id)
    return self._process_users(users)

def generate_report(self, results: List[Dict], output_file: str) -> None:
    """Generate CSV report from results.

    Args:
        results: Processing results
        output_file: Output CSV file path
    """
    with open(output_file, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'status'])
        writer.writeheader()
        writer.writerows(results)

def send_completion_notification(self, result_count: int) -> None:
    """Send email notification of completion.

    Args:
        result_count: Number of processed items
    """
    subject = "Processing complete"
    body = f"Processed {result_count} users"
    self._send_email(subject, body)
```

## Refactoring Workflow

### Step 1: Identify the Smell

Run through checklist:
- [ ] Function >50 lines?
- [ ] Code duplicated 3+ times?
- [ ] Nesting >3 levels deep?
- [ ] Magic numbers or hardcoded values?
- [ ] Unclear variable names?
- [ ] Function does >1 thing?

### Step 2: Choose Refactoring Pattern

Match smell to pattern:
- **Long function** → Extract Method
- **Duplicated code** → Extract Utility
- **Complex conditionals** → Guard Clauses / Early Returns
- **Magic numbers** → Extract Constants
- **Unclear names** → Rename Variables
- **Multiple responsibilities** → Split Functions

### Step 3: Apply Refactoring

1. Write tests first (if not already present)
2. Apply refactoring pattern
3. Run tests to verify no regressions
4. Commit refactoring separately

### Step 4: Verify Quality

Check refactored code:
- [ ] All functions <50 lines?
- [ ] Each function single-purpose?
- [ ] Variable names clear?
- [ ] No duplication?
- [ ] Type hints present?
- [ ] Docstrings added?

## Logic Density Guidelines

### Maximum Function Length: 50 Lines

Count from first line of code to last line (excluding docstring):

```python
def example_function(param1: str, param2: int) -> Dict[str, Any]:
    """Docstring doesn't count toward 50 lines."""
    # Line 1
    result = {}

    # Lines 2-48: implementation

    # Line 49
    return result  # Line 50 - OK!
```

### Single Responsibility Principle

Each function should do **one thing**:

```python
# GOOD - Single purpose
def validate_email_format(email: str) -> bool:
    """Check if email has valid format."""
    return '@' in email and '.' in email.split('@')[1]

def filter_valid_emails(users: List[Dict]) -> List[Dict]:
    """Filter users with valid emails."""
    return [u for u in users if validate_email_format(u.get('email', ''))]

# BAD - Multiple purposes
def validate_and_filter(users: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """Validate emails AND filter users AND collect errors."""
    # Does 3 things!
    pass
```

### Composition Over Inheritance

**Prefer**: Composing objects and delegating
**Avoid**: Inheriting from domain classes

```python
# GOOD - Composition
class ReportGenerator:
    def __init__(self, client: AlmaAPIClient):
        self.users_domain = Users(client)
        self.bibs_domain = Bibs(client)

    def generate_report(self):
        users = self.users_domain.get_all_users()
        # Use composed objects
        pass

# BAD - Inheritance
class ReportGenerator(Users, Bibs):  # Don't inherit domain classes
    pass
```

### Early Extraction

If you think "this could be extracted," extract it immediately:

```python
# If you see this and think "the validation logic could be extracted"
def update_user(self, user_id: str, email: str) -> Dict:
    if not email or '@' not in email or '.' not in email.split('@')[1]:
        raise ValueError("Invalid email")
    # ... rest of function

# DO IT NOW - don't wait
def _validate_email(self, email: str) -> None:
    """Validate email format."""
    if not email or '@' not in email or '.' not in email.split('@')[1]:
        raise ValueError("Invalid email")

def update_user(self, user_id: str, email: str) -> Dict:
    self._validate_email(email)
    # ... rest of function
```

## Common Refactoring Scenarios

### Scenario 1: Pagination Logic Duplication

**Problem**: Same pagination code in multiple methods

**Solution**: Extract to utility method

```python
def _paginate_request(self, endpoint: str, params: Dict = None,
                      page_size: int = 100) -> List[Dict]:
    """Fetch all pages from paginated endpoint.

    Args:
        endpoint: API endpoint
        params: Query parameters
        page_size: Items per page

    Returns:
        All items from all pages
    """
    all_items = []
    offset = 0
    params = params or {}

    while True:
        params.update({"limit": page_size, "offset": offset})
        response = self.client.get(endpoint, params=params)
        items = response.json().get('items', [])

        if not items:
            break

        all_items.extend(items)
        offset += page_size

    return all_items
```

### Scenario 2: Error Handling Boilerplate

**Problem**: Same try/except pattern in many methods

**Solution**: Decorator or context manager

```python
from functools import wraps

def log_api_errors(operation: str):
    """Decorator to log API errors consistently."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except AlmaAPIError as e:
                self.logger.error(f"{operation} failed",
                                error_code=e.status_code,
                                error_message=str(e))
                raise
        return wrapper
    return decorator

# Usage
@log_api_errors("User retrieval")
def get_user(self, user_id: str) -> Dict[str, Any]:
    """Get user by ID."""
    return self.client.get(f"almaws/v1/users/{user_id}").json()
```

### Scenario 3: Complex Data Extraction

**Problem**: Deep dictionary navigation repeated

**Solution**: Extract helper functions

```python
def _extract_primary_email(self, user_data: Dict) -> Optional[str]:
    """Extract primary email from user data."""
    return user_data.get('contact_info', {}).get('email', [{}])[0].get('email_address')

def _extract_user_name(self, user_data: Dict) -> str:
    """Extract full name from user data."""
    first = user_data.get('first_name', '')
    last = user_data.get('last_name', '')
    return f"{first} {last}".strip()
```
