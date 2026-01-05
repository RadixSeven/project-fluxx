"""Type stubs for tenacity retry library.

Names match the actual library's snake_case conventions.
"""
# ruff: noqa: N801

from collections.abc import Callable
from typing import TypeVar

_F = TypeVar("_F", bound=Callable[..., object])

class RetryError(Exception):
    """Exception raised when all retries are exhausted."""

    pass

class retry_base:
    """Base class for retry conditions."""

    pass

class retry_if_exception_type(retry_base):
    """Retry if the exception is of the given type(s)."""

    def __init__(self, exception_types: type | tuple[type, ...]) -> None: ...

class stop_base:
    """Base class for stop conditions."""

    pass

class stop_after_attempt(stop_base):
    """Stop after the given number of attempts."""

    def __init__(self, max_attempt_number: int) -> None: ...

class wait_base:
    """Base class for wait strategies."""

    pass

class wait_exponential(wait_base):
    """Wait with exponential backoff."""

    def __init__(
        self,
        multiplier: float = ...,
        max: float = ...,
        min: float = ...,
    ) -> None: ...

def retry(
    retry: retry_base | None = ...,
    stop: stop_base | None = ...,
    wait: wait_base | None = ...,
    reraise: bool = ...,
) -> Callable[[_F], _F]: ...
