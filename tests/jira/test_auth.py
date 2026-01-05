"""Tests for fluxx.jira.auth module."""

from pathlib import Path

import pytest

from fluxx.jira.auth import (
    TokenNotFoundError,
    get_token_path,
    read_token,
)


class TestGetTokenPath:
    """Tests for get_token_path function."""

    def test_url_with_port(self) -> None:
        """Test token path derivation with port in URL."""
        url = "https://jira.example.com:8080/path/to/jira"
        expected = (
            Path.home()
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com.8080"
            / "path"
            / "to"
            / "jira"
            / "personal_access_token.txt"
        )
        assert get_token_path(url) == expected

    def test_url_without_port(self) -> None:
        """Test token path derivation without port in URL."""
        url = "https://jira.example.com/path/to/jira"
        expected = (
            Path.home()
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "path"
            / "to"
            / "jira"
            / "personal_access_token.txt"
        )
        assert get_token_path(url) == expected

    def test_url_with_trailing_slash(self) -> None:
        """Test that trailing slashes are stripped from path."""
        url = "https://jira.example.com/jira/"
        expected = (
            Path.home()
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "jira"
            / "personal_access_token.txt"
        )
        assert get_token_path(url) == expected

    def test_url_no_path(self) -> None:
        """Test URL with no path component."""
        url = "https://jira.example.com"
        expected = (
            Path.home()
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "personal_access_token.txt"
        )
        assert get_token_path(url) == expected

    def test_url_with_default_https_port(self) -> None:
        """Test URL with explicit port 443."""
        url = "https://jira.example.com:443/jira"
        expected = (
            Path.home()
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com.443"
            / "jira"
            / "personal_access_token.txt"
        )
        assert get_token_path(url) == expected


class TestReadToken:
    """Tests for read_token function."""

    def test_read_token_success(self, tmp_path: Path) -> None:
        """Test successful token read."""
        token_file = tmp_path / "token.txt"
        token_file.write_text("my-secret-token\n")

        assert read_token(token_file) == "my-secret-token"

    def test_read_token_strips_whitespace(self, tmp_path: Path) -> None:
        """Test that whitespace is stripped from token."""
        token_file = tmp_path / "token.txt"
        token_file.write_text("  my-token  \n\n")

        assert read_token(token_file) == "my-token"

    def test_read_token_file_not_found_raises_token_not_found_error(
        self, tmp_path: Path
    ) -> None:
        """Test TokenNotFoundError for missing token file."""
        token_file = tmp_path / "nonexistent.txt"

        with pytest.raises(TokenNotFoundError) as exc_info:
            read_token(token_file)

        assert exc_info.value.token_path == token_file
        assert "not found" in str(exc_info.value).lower()

    def test_read_token_permission_denied(self, tmp_path: Path) -> None:
        """Test PermissionError for unreadable token file."""
        token_file = tmp_path / "token.txt"
        token_file.write_text("secret")
        token_file.chmod(0o000)

        try:
            with pytest.raises(PermissionError):
                read_token(token_file)
        finally:
            token_file.chmod(0o644)


class TestTokenNotFoundError:
    """Tests for TokenNotFoundError exception."""

    def test_token_not_found_error_has_path(self, tmp_path: Path) -> None:
        """Test that TokenNotFoundError stores the token path."""
        token_path = tmp_path / "missing_token.txt"
        error = TokenNotFoundError(token_path)

        assert error.token_path == token_path
        assert str(token_path) in str(error)

    def test_token_not_found_error_is_exception(self) -> None:
        """Test that TokenNotFoundError is an Exception."""
        error = TokenNotFoundError(Path("/some/path"))
        assert isinstance(error, Exception)
