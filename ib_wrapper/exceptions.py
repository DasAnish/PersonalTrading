"""
Custom exceptions for Interactive Brokers wrapper.

This module defines a hierarchy of custom exceptions for clear error handling
throughout the IB wrapper library.
"""


class IBWrapperException(Exception):
    """Base exception for all IB wrapper errors."""

    pass


class ConnectionException(IBWrapperException):
    """Raised when connection to IB fails or is lost."""

    pass


class AuthenticationException(IBWrapperException):
    """Raised when authentication with IB fails."""

    pass


class DataRequestException(IBWrapperException):
    """Raised when a data request fails."""

    pass


class RateLimitException(IBWrapperException):
    """Raised when IB API rate limit is exceeded."""

    pass


class InvalidContractException(IBWrapperException):
    """Raised when contract specification is invalid."""

    pass


class PortfolioException(IBWrapperException):
    """Raised when portfolio operations fail."""

    pass


class ConfigurationException(IBWrapperException):
    """Raised when configuration is invalid or missing."""

    pass
