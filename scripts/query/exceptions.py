"""Custom exceptions for query module."""


class QueryCompilationError(Exception):
    """Exception raised when query compilation fails.

    This exception is raised when the LLM-based query compiler cannot
    parse a natural language query into a QueryPlan. Causes include:
    - Missing or invalid OpenAI API key
    - API timeout or network errors
    - Rate limiting
    - Invalid API response
    """

    def __init__(self, message: str, original_error: Exception = None):
        """Initialize QueryCompilationError.

        Args:
            message: Human-readable error message
            original_error: Original exception that caused this error (optional)
        """
        super().__init__(message)
        self.original_error = original_error

    @classmethod
    def from_missing_api_key(cls) -> "QueryCompilationError":
        """Create error for missing API key."""
        message = (
            "OpenAI API key not found. M4 query compilation requires OpenAI API access.\n\n"
            "To fix this issue:\n"
            "1. Set OPENAI_API_KEY environment variable:\n"
            "   export OPENAI_API_KEY='sk-...'\n\n"
            "2. Or pass api_key parameter to compile_query():\n"
            "   compile_query(query_text, api_key='sk-...')\n\n"
            "See CLAUDE.md:198-199 for setup instructions."
        )
        return cls(message)

    @classmethod
    def from_api_error(cls, error: Exception) -> "QueryCompilationError":
        """Create error for API failures (timeout, rate limit, etc.)."""
        error_type = type(error).__name__
        error_message = str(error)

        message = (
            f"OpenAI API error: {error_type}\n\n"
            f"Details: {error_message}\n\n"
            "Possible causes:\n"
            "- Network timeout or connectivity issues\n"
            "- Rate limiting (too many requests)\n"
            "- Invalid or expired API key\n"
            "- OpenAI service disruption\n\n"
            "Solutions:\n"
            "- Check your internet connection\n"
            "- Verify your API key is valid: echo $OPENAI_API_KEY\n"
            "- Check OpenAI status: https://status.openai.com/\n"
            "- Wait a few moments and try again (if rate limited)"
        )
        return cls(message, original_error=error)

    @classmethod
    def from_invalid_response(cls, error: Exception) -> "QueryCompilationError":
        """Create error for invalid LLM responses."""
        message = (
            f"OpenAI returned invalid response: {type(error).__name__}\n\n"
            f"Details: {str(error)}\n\n"
            "This is likely a temporary issue. Please try again.\n"
            "If the problem persists, the query may be too complex or ambiguous."
        )
        return cls(message, original_error=error)
