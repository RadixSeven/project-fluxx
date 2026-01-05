"""Type stubs for responses.matchers module."""

def header_matcher(headers: dict[str, str]) -> object:
    """Match request headers."""
    ...

def query_param_matcher(params: dict[str, str]) -> object:
    """Match query parameters."""
    ...

def json_params_matcher(params: object) -> object:
    """Match JSON body parameters."""
    ...

def urlencoded_params_matcher(params: dict[str, str]) -> object:
    """Match URL-encoded body parameters."""
    ...
