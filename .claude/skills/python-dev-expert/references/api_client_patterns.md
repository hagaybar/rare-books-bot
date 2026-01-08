# Generic API Client Patterns

**For Alma-specific API usage, endpoints, and quirks → see `alma-api-expert` skill**

Generic patterns for building robust REST API clients in Python.

## Pagination Pattern

Many REST APIs return paginated results. Use consistent pagination logic:

```python
def _fetch_all_pages(self, endpoint: str, params: Dict[str, Any] = None,
                     page_size: int = 100, item_key: str = 'items') -> List[Dict[str, Any]]:
    """Fetch all pages from paginated endpoint.

    Args:
        endpoint: API endpoint path
        params: Query parameters
        page_size: Items per page (default: 100)
        item_key: JSON key containing items (default: 'items')

    Returns:
        List of all items from all pages
    """
    all_items = []
    offset = 0
    params = params or {}

    while True:
        page_params = {**params, "limit": page_size, "offset": offset}
        response = self.client.get(endpoint, params=page_params)
        data = response.json()

        items = data.get(item_key, [])
        if not items:
            break

        all_items.extend(items)
        offset += page_size

        # Log progress for long operations
        if offset % 1000 == 0:
            self.logger.info(f"Fetched {offset} items so far...")

    self.logger.info(f"Fetched total of {len(all_items)} items")
    return all_items
```

### Pagination Usage

```python
def get_all_resources(self, collection_id: str) -> List[Dict[str, Any]]:
    """Get all resources from a collection.

    Args:
        collection_id: Collection identifier

    Returns:
        List of all resource dictionaries
    """
    endpoint = f"api/v1/collections/{collection_id}/items"
    return self._fetch_all_pages(endpoint, item_key='items')
```

## Rate Limiting Pattern

Most APIs have rate limits. Handle them gracefully:

```python
import time
from typing import Callable, Any

def with_rate_limit_retry(max_retries: int = 3, delay: int = 60):
    """Decorator to retry on rate limit errors.

    Args:
        max_retries: Maximum retry attempts
        delay: Seconds to wait on rate limit (default: 60)
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:  # Use your API's rate limit exception
                    if attempt == max_retries - 1:
                        raise
                    self.logger.warning(
                        f"Rate limit hit, retrying in {delay}s",
                        attempt=attempt + 1,
                        max_retries=max_retries
                    )
                    time.sleep(delay)
            return None
        return wrapper
    return decorator
```

**Note**: Replace `RateLimitError` with your API's specific exception (e.g., `AlmaRateLimitError` in this project).

## Error Handling Pattern

Handle API errors consistently with a hierarchy of exceptions:

```python
def safe_api_call(self, operation: str, func: Callable, *args, **kwargs) -> Optional[Any]:
    """Execute API call with standardized error handling.

    Args:
        operation: Description of operation for logging
        func: Function to call
        *args, **kwargs: Arguments to pass to function

    Returns:
        Function result or None on error

    Raises:
        APIError: On unrecoverable API error
    """
    self.logger.info(f"Starting {operation}")

    try:
        result = func(*args, **kwargs)
        self.logger.info(f"{operation} completed successfully")
        return result

    except ValidationError as e:
        self.logger.error(f"{operation} validation failed", error=str(e))
        raise

    except RateLimitError as e:
        self.logger.warning(f"{operation} hit rate limit", error=str(e))
        raise

    except APIError as e:
        self.logger.error(
            f"{operation} failed",
            error_code=e.status_code,
            error_message=str(e),
            tracking_id=getattr(e, 'tracking_id', None)
        )
        raise
```

**Project-specific error hierarchy example**:
- `APIError` (base)
  - `ValidationError` (input validation)
  - `RateLimitError` (rate limit exceeded)
  - `AuthenticationError` (auth failure)

In this project: `AlmaAPIError`, `AlmaValidationError`, `AlmaRateLimitError`

## Logging Pattern

Use structured logging for all API operations:

```python
from src.logging import get_logger

class DomainClass:
    def __init__(self, client):
        self.client = client
        self.logger = get_logger('domain_name', client.environment)

    def api_operation(self, resource_id: str) -> Dict[str, Any]:
        """Perform API operation."""
        # Log entry with parameters
        self.logger.info("Starting operation", resource_id=resource_id)

        try:
            # Make API call
            result = self.client.get(f"api/v1/resources/{resource_id}")

            # Log success
            self.logger.info("Operation successful",
                           resource_id=resource_id,
                           result_count=len(result.json()))

            return result.json()

        except APIError as e:
            # Log failure with context
            self.logger.error("Operation failed",
                            resource_id=resource_id,
                            error_code=e.status_code,
                            error_message=str(e))
            raise
```

### Logging Best Practices

**DO**:
- Use key-value pairs: `self.logger.info("Message", key=value)`
- Log operation entry and completion
- Include resource identifiers
- Log errors before re-raising
- Use appropriate levels (INFO, ERROR, WARNING, DEBUG)

**DON'T**:
- Log API keys or secrets
- Use string concatenation: `f"User {user_id}"` (use key=value)
- Log entire API responses (use summaries)
- Log in loops without throttling

## Request/Response Logging

Generic pattern for logging all API requests and responses:

```python
# In API Client base class
def get(self, endpoint: str, params: Dict = None):
    """Make GET request with automatic logging."""
    self.logger.log_request('GET', endpoint, params=params)

    start_time = time.time()
    response = requests.get(url, headers=headers, params=params)
    duration_ms = (time.time() - start_time) * 1000

    self.logger.log_response(response, duration_ms=duration_ms)

    return response
```

## Data Extraction Pattern

Safely extract nested data from API responses:

```python
from typing import Optional

def extract_field(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """Safely extract nested field from dictionary using dot notation.

    Args:
        data: Source dictionary
        path: Dot-separated path (e.g., 'user.profile.email.0.address')
        default: Default value if path not found

    Returns:
        Extracted value or default

    Example:
        >>> data = {'user': {'profile': {'email': [{'address': 'test@example.com'}]}}}
        >>> extract_field(data, 'user.profile.email.0.address')
        'test@example.com'
        >>> extract_field(data, 'user.phone', default='N/A')
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
```

### Usage

```python
# Instead of:
email = response.get('user', {}).get('profile', {}).get('email', [{}])[0].get('address')

# Use:
email = extract_field(response, 'user.profile.email.0.address', default='')
```

## Batch Processing Pattern

Process items in batches with progress tracking:

```python
def process_in_batches(self, items: List[Any], batch_size: int = 10,
                       processor: Callable = None) -> List[Dict[str, Any]]:
    """Process items in batches with progress logging.

    Args:
        items: Items to process
        batch_size: Items per batch
        processor: Function to process each item

    Returns:
        List of processing results
    """
    results = []
    total = len(items)

    for i in range(0, total, batch_size):
        batch = items[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        self.logger.info(f"Processing batch {batch_num}/{total_batches}",
                        items_in_batch=len(batch))

        for item in batch:
            try:
                result = processor(item) if processor else item
                results.append({
                    'item': item,
                    'status': 'SUCCESS',
                    'result': result
                })
            except Exception as e:
                self.logger.error("Item processing failed",
                                item=item,
                                error=str(e))
                results.append({
                    'item': item,
                    'status': 'FAILED',
                    'error': str(e)
                })

    success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
    self.logger.info(f"Batch processing complete: {success_count}/{total} succeeded")

    return results
```

## Validation Pattern

Validate inputs before making API calls:

```python
from typing import List

class InputValidator:
    """Validation utilities for API inputs."""

    @staticmethod
    def validate_required(value: Any, field_name: str) -> None:
        """Validate required field is present.

        Args:
            value: Value to check
            field_name: Field name for error message

        Raises:
            ValidationError: If value is None or empty
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError(f"{field_name} is required")

    @staticmethod
    def validate_one_of(value: Any, allowed: List[Any], field_name: str) -> None:
        """Validate value is in allowed list.

        Args:
            value: Value to check
            allowed: List of allowed values
            field_name: Field name for error message

        Raises:
            ValidationError: If value not in allowed list
        """
        if value not in allowed:
            raise ValidationError(
                f"{field_name} must be one of {allowed}, got: {value}"
            )

    @staticmethod
    def validate_format(value: str, pattern: str, field_name: str) -> None:
        """Validate value matches regex pattern.

        Args:
            value: Value to check
            pattern: Regex pattern
            field_name: Field name for error message

        Raises:
            ValidationError: If value doesn't match pattern
        """
        import re
        if not re.match(pattern, value):
            raise ValidationError(
                f"{field_name} format invalid: {value}"
            )
```

### Usage

```python
def create_resource(self, name: str, resource_type: str,
                   status: str, **kwargs) -> Dict[str, Any]:
    """Create resource with validation."""
    # Validate inputs
    InputValidator.validate_required(name, "name")
    InputValidator.validate_required(resource_type, "resource_type")
    InputValidator.validate_one_of(status, ["active", "inactive"], "status")

    # Proceed with API call
    resource_data = self._build_resource_data(name, resource_type, status, **kwargs)
    return self._create_resource(resource_data)
```

## Testing Pattern

Write testable code with dependency injection:

```python
# Good - Testable
class ResourcesAPI:
    def __init__(self, client):
        self.client = client  # Injected dependency

    def get_resource(self, resource_id: str) -> Dict:
        return self.client.get(f"api/v1/resources/{resource_id}").json()

# Test with mock client
def test_get_resource():
    mock_client = MagicMock()
    mock_client.get.return_value.json.return_value = {'id': '123', 'name': 'Test'}

    api = ResourcesAPI(mock_client)
    result = api.get_resource('123')

    assert result['id'] == '123'
    mock_client.get.assert_called_once_with('api/v1/resources/123')
```

## Configuration Pattern

Externalize configuration for flexibility:

```python
from typing import Dict, Any
import json

class DomainConfig:
    """Configuration for domain operations."""

    def __init__(self, config_file: str = None):
        """Load configuration from file or use defaults.

        Args:
            config_file: Path to JSON config file (optional)
        """
        self.config = self._load_config(config_file)

    def _load_config(self, config_file: str = None) -> Dict[str, Any]:
        """Load configuration from file or return defaults."""
        if config_file:
            with open(config_file, 'r') as f:
                return json.load(f)
        return self._get_defaults()

    def _get_defaults(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'page_size': 100,
            'max_retries': 3,
            'retry_delay': 60,
            'timeout': 30
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)
```

## Response Caching Pattern

Cache responses for expensive operations:

```python
from functools import lru_cache
from typing import Dict, Any

class CachedAPI:
    """API client with response caching."""

    @lru_cache(maxsize=100)
    def get_config(self, config_key: str) -> Dict[str, Any]:
        """Get configuration data with caching.

        Args:
            config_key: Configuration identifier

        Returns:
            Configuration data (cached)
        """
        endpoint = f"api/v1/config/{config_key}"
        return self.client.get(endpoint).json()

    def clear_cache(self) -> None:
        """Clear all cached responses."""
        self.get_config.cache_clear()
```

**Note**: For API-specific caching strategies and TTL considerations, consult your API's documentation.

## Retry with Exponential Backoff

Implement retry logic for transient failures:

```python
import time
from typing import Callable, TypeVar

T = TypeVar('T')

def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retry_on: tuple = (ConnectionError, TimeoutError)
) -> T:
    """Retry function with exponential backoff.

    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
        retry_on: Tuple of exceptions to retry on

    Returns:
        Function result

    Raises:
        Last exception if all retries exhausted
    """
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            return func()
        except retry_on as e:
            if attempt == max_retries:
                raise

            time.sleep(delay)
            delay *= backoff_factor

            print(f"Retry {attempt + 1}/{max_retries} after {delay}s delay")
```

## Circuit Breaker Pattern

Prevent cascading failures with circuit breaker:

```python
from datetime import datetime, timedelta
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """Circuit breaker for API calls."""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    def call(self, func: Callable, *args, **kwargs):
        """Execute function through circuit breaker."""
        if self.state == CircuitState.OPEN:
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout):
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
```
