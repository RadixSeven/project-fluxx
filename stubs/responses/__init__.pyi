"""Type stubs for responses mock library."""

from collections.abc import Callable, Sequence

GET: str
POST: str
PUT: str
DELETE: str
PATCH: str
HEAD: str
OPTIONS: str

class CallList(list["Call"]):
    """List of recorded calls."""

    pass

class Call:
    """A recorded request call."""

    request: object
    response: object

calls: CallList

def activate[F: Callable[..., object]](func: F) -> F:
    """Decorator to activate responses mocking."""
    ...

def add(
    method: str | object = ...,
    url: str = ...,
    body: str | bytes | BaseException = ...,
    json: object = ...,
    status: int = ...,
    headers: dict[str, str] | None = ...,
    match: Sequence[object] | None = ...,
    content_type: str | None = ...,
) -> None:
    """Add a mock response."""
    ...

def reset() -> None:
    """Reset all mock responses."""
    ...
