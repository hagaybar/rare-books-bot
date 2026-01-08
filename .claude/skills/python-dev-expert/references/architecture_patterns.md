# Architecture Patterns for AlmaAPITK

## Client-Domain Pattern

The core architectural pattern in AlmaAPITK separates API client logic from domain-specific operations.

### Pattern Structure

```
AlmaAPIClient (Base Client)
    ↓
Domain Classes (Users, Bibs, Acquisitions, etc.)
    ↓
Project Scripts (Operational automation)
```

### AlmaAPIClient Responsibilities

- HTTP methods (GET, POST, PUT, DELETE)
- Authentication and environment management
- Base URL construction
- Connection testing
- Rate limiting protection

### Domain Class Responsibilities

- Domain-specific API operations
- Response parsing and validation
- Business logic for domain
- Error handling with domain context
- Logging domain operations

### Example: Users Domain

```python
from src.client.AlmaAPIClient import AlmaAPIClient
from src.logging import get_logger
from typing import Dict, Any, List, Optional

class Users:
    """Alma Users API operations."""

    def __init__(self, client: AlmaAPIClient):
        """Initialize Users domain with API client.

        Args:
            client: Configured AlmaAPIClient instance
        """
        self.client = client
        self.logger = get_logger('users', client.environment)

    def get_user(self, user_id: str) -> Dict[str, Any]:
        """Retrieve user by primary ID.

        Args:
            user_id: User primary identifier

        Returns:
            User data dictionary

        Raises:
            AlmaAPIError: If user not found or API error
        """
        self.logger.info("Retrieving user", user_id=user_id)
        endpoint = f"almaws/v1/users/{user_id}"
        response = self.client.get(endpoint)
        self.logger.info("User retrieved successfully", user_id=user_id)
        return response.json()
```

## Error Hierarchy

Use Alma-specific exceptions for clear error handling:

```python
AlmaAPIError (Base exception)
    ├── AlmaValidationError (Invalid input)
    ├── AlmaRateLimitError (Rate limit exceeded)
    └── AlmaAuthenticationError (Auth failure)
```

### Error Handling Pattern

```python
from src.client.AlmaAPIClient import AlmaAPIError, AlmaValidationError

def update_user(self, user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Update user with validation."""
    try:
        # Validate before API call
        if not user_id:
            raise AlmaValidationError("user_id is required")

        # Make API call
        endpoint = f"almaws/v1/users/{user_id}"
        response = self.client.put(endpoint, data=user_data)
        return response.json()

    except AlmaValidationError as e:
        self.logger.error("Validation failed", user_id=user_id, error=str(e))
        raise
    except AlmaAPIError as e:
        self.logger.error("API error updating user",
                         user_id=user_id,
                         error_code=e.status_code,
                         error_message=str(e))
        raise
```

## Response Wrapping Pattern

The AlmaResponse wrapper provides consistent response handling:

```python
# In AlmaAPIClient
response = self.client.get(endpoint)
# Returns AlmaResponse object with:
# - response.json()
# - response.status_code
# - response.text
```

### When to Parse Responses

**Immediate parsing** (in domain method):
```python
def get_user_email(self, user_id: str) -> Optional[str]:
    """Get user's primary email."""
    user = self.get_user(user_id)  # Returns dict
    return user.get('contact_info', {}).get('email', [{}])[0].get('email_address')
```

**Deferred parsing** (return raw response):
```python
def get_user(self, user_id: str) -> Dict[str, Any]:
    """Get full user data - let caller parse."""
    response = self.client.get(f"almaws/v1/users/{user_id}")
    return response.json()  # Return full data
```

## Domain Class Structure Template

```python
"""
Domain class for [DOMAIN] operations.

This module provides methods for interacting with Alma [DOMAIN] API endpoints.
"""

from typing import Dict, Any, List, Optional
from src.client.AlmaAPIClient import AlmaAPIClient, AlmaAPIError, AlmaValidationError
from src.logging import get_logger


class [DomainName]:
    """Alma [DOMAIN] API operations.

    Provides methods for:
    - [Operation 1]
    - [Operation 2]
    - [Operation 3]
    """

    def __init__(self, client: AlmaAPIClient):
        """Initialize [DOMAIN] domain with API client.

        Args:
            client: Configured AlmaAPIClient instance
        """
        self.client = client
        self.logger = get_logger('[domain_name]', client.environment)

    def get_[resource](self, resource_id: str) -> Dict[str, Any]:
        """Retrieve [resource] by ID.

        Args:
            resource_id: [Resource] identifier

        Returns:
            [Resource] data dictionary

        Raises:
            AlmaValidationError: If resource_id invalid
            AlmaAPIError: If API error occurs
        """
        if not resource_id:
            raise AlmaValidationError("resource_id is required")

        self.logger.info("Retrieving [resource]", resource_id=resource_id)
        endpoint = f"almaws/v1/[domain]/[resources]/{resource_id}"

        try:
            response = self.client.get(endpoint)
            self.logger.info("[Resource] retrieved successfully", resource_id=resource_id)
            return response.json()
        except AlmaAPIError as e:
            self.logger.error("Failed to retrieve [resource]",
                            resource_id=resource_id,
                            error_code=e.status_code,
                            error_message=str(e))
            raise
```

## When to Create New Domain Class

**Create new domain class** when:
1. Adding support for new Alma API domain (Bibs, Users, Holdings, etc.)
2. Grouping 5+ related API operations
3. Domain has specialized business logic
4. Operations need shared state or configuration

**Extend existing domain class** when:
1. Adding operations to existing domain
2. Operations are closely related to existing methods
3. Reusing existing domain setup (logger, client, etc.)

**Create utility function** when:
1. Logic is used across multiple domains
2. Function is domain-agnostic (date formatting, parsing, etc.)
3. Operation is simple and stateless

## Composition Over Inheritance

Prefer composition for code reuse:

```python
# GOOD - Composition
class Acquisitions:
    def __init__(self, client: AlmaAPIClient):
        self.client = client
        self.bibs = Bibs(client)  # Compose Bibs domain

    def get_pol_with_bib_data(self, pol_id: str) -> Dict[str, Any]:
        """Get POL with enriched bibliographic data."""
        pol = self.get_pol(pol_id)
        mms_id = pol.get('resource_metadata', {}).get('mms_id', {}).get('value')
        if mms_id:
            pol['bib_data'] = self.bibs.get_bib(mms_id)
        return pol

# BAD - Inheritance
class Acquisitions(Bibs):  # Don't inherit domain classes
    def __init__(self, client: AlmaAPIClient):
        super().__init__(client)
```

## Module Organization

```
src/
├── client/
│   └── AlmaAPIClient.py       # Base API client
├── domains/
│   ├── users.py               # Users domain
│   ├── bibs.py                # Bibs domain
│   ├── acquisition.py         # Acquisitions domain
│   └── resource_sharing.py    # Resource sharing domain
├── projects/
│   └── [script_name].py       # Standalone operational scripts
├── utils/
│   └── [utility_name].py      # Shared utilities
└── logging/
    └── __init__.py            # Logging infrastructure
```

## Import Organization

Follow PEP 8 import order:

```python
# 1. Standard library imports
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

# 2. Third-party imports
import requests
from requests.exceptions import RequestException

# 3. Local application imports
from src.client.AlmaAPIClient import AlmaAPIClient, AlmaAPIError
from src.logging import get_logger
from src.utils.date_utils import format_date
```

Organize alphabetically within each group.
