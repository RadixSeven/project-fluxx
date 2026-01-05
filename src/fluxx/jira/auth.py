"""Authentication utilities for Jira API access.

This module handles personal access token (PAT) management for Jira Data Center.
Tokens are stored at paths derived from the Jira server URL.

For https://example.com:port/path/to/jira, looks in:
    ~/.local/share/secrets/example.com.port/path/to/jira/personal_access_token.txt

For https://example.com/path/to/jira (no port), looks in:
    ~/.local/share/secrets/example.com/path/to/jira/personal_access_token.txt
"""

from pathlib import Path
from urllib.parse import urlparse


class TokenNotFoundError(Exception):
    """Raised when the personal access token file cannot be found.

    Attributes:
        token_path: The path where the token was expected.
    """

    def __init__(self, token_path: Path) -> None:
        self.token_path = token_path
        super().__init__(f"Personal access token not found at {token_path}")


def get_token_path(base_url: str) -> Path:
    """Derive the personal access token file path from the Jira base URL.

    Args:
        base_url: The Jira base URL (e.g., https://example.com:8080/jira)

    Returns:
        Path to the personal_access_token.txt file
    """
    parsed = urlparse(base_url)
    hostname = parsed.hostname or ""
    port = parsed.port
    url_path = parsed.path.rstrip("/")

    host_part = hostname if port is None else f"{hostname}.{port}"

    secrets_base = Path.home() / ".local" / "share" / "secrets"
    return secrets_base / host_part / url_path.lstrip("/") / "personal_access_token.txt"


def read_token(token_path: Path) -> str:
    """Read the personal access token from the file.

    Args:
        token_path: Path to the token file

    Returns:
        The token string (whitespace stripped)

    Raises:
        TokenNotFoundError: If the token file doesn't exist
        PermissionError: If the token file can't be read
    """
    try:
        return token_path.read_text().strip()
    except FileNotFoundError as e:
        raise TokenNotFoundError(token_path) from e
