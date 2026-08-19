"""
ArcGIS Authentication Exceptions

This module provides exception classes for ArcGIS authentication errors.
"""


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ServiceUnavailableError(Exception):
    """Raised when the service is unavailable."""

    def __init__(self, message: str, status_code: int = 503):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)
