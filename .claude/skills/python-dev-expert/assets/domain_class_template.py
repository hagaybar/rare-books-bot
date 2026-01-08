"""
[DOMAIN_NAME] domain operations for Alma API.

This module provides methods for interacting with Alma [DOMAIN_NAME] API endpoints.
"""

from typing import Dict, Any, List, Optional
from src.client.AlmaAPIClient import AlmaAPIClient, AlmaAPIError, AlmaValidationError
from src.logging import get_logger


class [ClassName]:
    """Alma [DOMAIN_NAME] API operations.

    Provides methods for:
    - [Operation 1 description]
    - [Operation 2 description]
    - [Operation 3 description]

    Example:
        >>> client = AlmaAPIClient('SANDBOX')
        >>> domain = [ClassName](client)
        >>> result = domain.get_[resource]('[resource_id]')
    """

    def __init__(self, client: AlmaAPIClient):
        """Initialize [DOMAIN_NAME] domain with API client.

        Args:
            client: Configured AlmaAPIClient instance
        """
        self.client = client
        self.logger = get_logger('[domain_name_lowercase]', client.environment)

    def get_[resource](self, resource_id: str) -> Dict[str, Any]:
        """Retrieve [resource] by ID.

        Args:
            resource_id: [Resource] identifier

        Returns:
            [Resource] data dictionary containing:
                - id: Resource identifier
                - [other_fields]: Description

        Raises:
            AlmaValidationError: If resource_id is invalid
            AlmaAPIError: If API error occurs

        Example:
            >>> result = domain.get_[resource]('[EXAMPLE_ID]')
            >>> print(result['id'])
        """
        # Validate input
        if not resource_id:
            raise AlmaValidationError("resource_id is required")

        # Log operation start
        self.logger.info("Retrieving [resource]", resource_id=resource_id)

        # Make API call
        endpoint = f"almaws/v1/[domain]/[resources]/{resource_id}"

        try:
            response = self.client.get(endpoint)
            result = response.json()

            # Log success
            self.logger.info("[Resource] retrieved successfully",
                           resource_id=resource_id)

            return result

        except AlmaAPIError as e:
            # Log error with context
            self.logger.error("Failed to retrieve [resource]",
                            resource_id=resource_id,
                            error_code=e.status_code,
                            error_message=str(e))
            raise

    def create_[resource](self, [resource]_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new [resource].

        Args:
            [resource]_data: [Resource] data dictionary with required fields:
                - [field1]: Description (required)
                - [field2]: Description (required)
                - [field3]: Description (optional)

        Returns:
            Created [resource] data with generated ID

        Raises:
            AlmaValidationError: If required fields missing
            AlmaAPIError: If API error occurs

        Example:
            >>> data = {
            ...     '[field1]': 'value1',
            ...     '[field2]': 'value2'
            ... }
            >>> result = domain.create_[resource](data)
        """
        # Validate required fields
        self._validate_[resource]_data([resource]_data)

        # Log operation start
        self.logger.info("Creating [resource]")

        # Make API call
        endpoint = "almaws/v1/[domain]/[resources]"

        try:
            response = self.client.post(endpoint, data=[resource]_data)
            result = response.json()

            # Log success
            self.logger.info("[Resource] created successfully",
                           resource_id=result.get('id'))

            return result

        except AlmaAPIError as e:
            # Log error
            self.logger.error("Failed to create [resource]",
                            error_code=e.status_code,
                            error_message=str(e))
            raise

    def update_[resource](self, resource_id: str,
                         [resource]_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing [resource].

        Args:
            resource_id: [Resource] identifier
            [resource]_data: Updated [resource] data

        Returns:
            Updated [resource] data

        Raises:
            AlmaValidationError: If resource_id invalid or data invalid
            AlmaAPIError: If API error occurs

        Example:
            >>> updated = domain.update_[resource]('[ID]', {'field': 'new_value'})
        """
        # Validate inputs
        if not resource_id:
            raise AlmaValidationError("resource_id is required")

        # Log operation start
        self.logger.info("Updating [resource]", resource_id=resource_id)

        # Make API call
        endpoint = f"almaws/v1/[domain]/[resources]/{resource_id}"

        try:
            response = self.client.put(endpoint, data=[resource]_data)
            result = response.json()

            # Log success
            self.logger.info("[Resource] updated successfully",
                           resource_id=resource_id)

            return result

        except AlmaAPIError as e:
            # Log error
            self.logger.error("Failed to update [resource]",
                            resource_id=resource_id,
                            error_code=e.status_code,
                            error_message=str(e))
            raise

    def delete_[resource](self, resource_id: str) -> None:
        """Delete [resource].

        Args:
            resource_id: [Resource] identifier

        Raises:
            AlmaValidationError: If resource_id invalid
            AlmaAPIError: If API error occurs

        Example:
            >>> domain.delete_[resource]('[ID]')
        """
        # Validate input
        if not resource_id:
            raise AlmaValidationError("resource_id is required")

        # Log operation start
        self.logger.info("Deleting [resource]", resource_id=resource_id)

        # Make API call
        endpoint = f"almaws/v1/[domain]/[resources]/{resource_id}"

        try:
            self.client.delete(endpoint)

            # Log success
            self.logger.info("[Resource] deleted successfully",
                           resource_id=resource_id)

        except AlmaAPIError as e:
            # Log error
            self.logger.error("Failed to delete [resource]",
                            resource_id=resource_id,
                            error_code=e.status_code,
                            error_message=str(e))
            raise

    def _validate_[resource]_data(self, data: Dict[str, Any]) -> None:
        """Validate [resource] data has required fields.

        Args:
            data: [Resource] data to validate

        Raises:
            AlmaValidationError: If required fields missing or invalid
        """
        required_fields = ['[field1]', '[field2]']

        for field in required_fields:
            if field not in data or not data[field]:
                raise AlmaValidationError(f"{field} is required")

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
