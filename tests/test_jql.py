"""Tests for jql CLI tool."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from fluxx.jql import (
    build_query_params,
    execute_search,
    get_token_path,
    main,
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

    def test_read_token_file_not_found(self, tmp_path: Path) -> None:
        """Test FileNotFoundError for missing token file."""
        token_file = tmp_path / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            read_token(token_file)

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


class TestBuildQueryParams:
    """Tests for build_query_params function."""

    def test_minimal_params(self) -> None:
        """Test with only required parameters."""
        params = build_query_params(
            jql="project = TEST",
            expand=None,
            max_results=None,
            validate_query=None,
            fields="*all",
            start_at=None,
        )

        assert params == {"jql": "project = TEST", "fields": "*all"}

    def test_all_params(self) -> None:
        """Test with all parameters specified."""
        params = build_query_params(
            jql="project = TEST",
            expand="changelog,renderedFields",
            max_results=50,
            validate_query=False,
            fields="summary,status",
            start_at=100,
        )

        assert params == {
            "jql": "project = TEST",
            "expand": "changelog,renderedFields",
            "maxResults": 50,
            "validateQuery": False,
            "fields": "summary,status",
            "startAt": 100,
        }

    def test_validate_query_true(self) -> None:
        """Test validateQuery with True value."""
        params = build_query_params(
            jql="project = TEST",
            expand=None,
            max_results=None,
            validate_query=True,
            fields="*all",
            start_at=None,
        )

        assert params["validateQuery"] is True


class TestExecuteSearch:
    """Tests for execute_search function."""

    def test_request_construction(self) -> None:
        """Test that the request is constructed correctly."""
        with patch("fluxx.jql.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_get.return_value = mock_response

            execute_search(
                base_url="https://jira.example.com/jira",
                token="my-token",
                params={"jql": "project = TEST", "fields": "*all"},
            )

            mock_get.assert_called_once_with(
                "https://jira.example.com/jira/rest/api/2/search",
                headers={
                    "Accept": "application/json",
                    "Authorization": "Bearer my-token",
                },
                params={"jql": "project = TEST", "fields": "*all"},
                allow_redirects=True,
                timeout=30,
            )

    def test_trailing_slash_in_base_url(self) -> None:
        """Test that trailing slash in base URL is handled."""
        with patch("fluxx.jql.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_get.return_value = mock_response

            execute_search(
                base_url="https://jira.example.com/jira/",
                token="token",
                params={"jql": "test"},
            )

            call_args = mock_get.call_args
            assert call_args[0][0] == "https://jira.example.com/jira/rest/api/2/search"


class TestMain:
    """Tests for main CLI function."""

    def test_no_url_provided(self) -> None:
        """Test error when no URL is provided."""
        with (
            patch.object(sys, "argv", ["jql", "project = TEST"]),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = main()

        assert result == 1

    def test_url_from_environment(self, tmp_path: Path) -> None:
        """Test reading URL from environment variable."""
        token_path = (
            tmp_path
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "jira"
            / "personal_access_token.txt"
        )
        token_path.parent.mkdir(parents=True)
        token_path.write_text("my-token")

        with (
            patch.object(sys, "argv", ["jql", "project = TEST"]),
            patch.dict(
                "os.environ",
                {"JIRA_API_BASE_URL": "https://jira.example.com/jira"},
                clear=True,
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("fluxx.jql.requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.json.return_value = {"issues": []}
            mock_get.return_value = mock_response

            result = main()

        assert result == 0

    def test_url_from_argument_overrides_env(self, tmp_path: Path) -> None:
        """Test --url argument overrides environment variable."""
        token_path = (
            tmp_path
            / ".local"
            / "share"
            / "secrets"
            / "other.example.com"
            / "personal_access_token.txt"
        )
        token_path.parent.mkdir(parents=True)
        token_path.write_text("my-token")

        with (
            patch.object(
                sys, "argv", ["jql", "--url", "https://other.example.com", "test"]
            ),
            patch.dict(
                "os.environ",
                {"JIRA_API_BASE_URL": "https://jira.example.com/jira"},
                clear=True,
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("fluxx.jql.requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.json.return_value = {"issues": []}
            mock_get.return_value = mock_response

            result = main()

        assert result == 0
        call_args = mock_get.call_args
        assert "other.example.com" in call_args[0][0]

    def test_token_not_found(self, tmp_path: Path) -> None:
        """Test error when token file doesn't exist."""
        with (
            patch.object(
                sys, "argv", ["jql", "--url", "https://jira.example.com", "test"]
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
        ):
            result = main()

        assert result == 1

    def test_token_permission_denied(self, tmp_path: Path) -> None:
        """Test error when token file is not readable."""
        token_path = (
            tmp_path
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "personal_access_token.txt"
        )
        token_path.parent.mkdir(parents=True)
        token_path.write_text("secret")
        token_path.chmod(0o000)

        try:
            with (
                patch.object(
                    sys, "argv", ["jql", "--url", "https://jira.example.com", "test"]
                ),
                patch("pathlib.Path.home", return_value=tmp_path),
            ):
                result = main()

            assert result == 1
        finally:
            token_path.chmod(0o644)

    def test_successful_request(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test successful request outputs JSON to stdout."""
        token_path = (
            tmp_path
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "personal_access_token.txt"
        )
        token_path.parent.mkdir(parents=True)
        token_path.write_text("my-token")

        response_data = {
            "issues": [{"key": "TEST-1", "fields": {"summary": "Test issue"}}],
            "total": 1,
        }

        with (
            patch.object(
                sys, "argv", ["jql", "--url", "https://jira.example.com", "test"]
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("fluxx.jql.requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.json.return_value = response_data
            mock_get.return_value = mock_response

            result = main()

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == response_data

    def test_http_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test HTTP error handling."""
        token_path = (
            tmp_path
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "personal_access_token.txt"
        )
        token_path.parent.mkdir(parents=True)
        token_path.write_text("my-token")

        with (
            patch.object(
                sys, "argv", ["jql", "--url", "https://jira.example.com", "bad query"]
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("fluxx.jql.requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.ok = False
            mock_response.status_code = 400
            mock_response.reason = "Bad Request"
            mock_response.text = '{"errorMessages": ["Invalid JQL"]}'
            mock_get.return_value = mock_response

            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "400" in captured.err
        assert "Invalid JQL" in captured.err

    def test_request_exception(self, tmp_path: Path) -> None:
        """Test handling of request exceptions."""
        token_path = (
            tmp_path
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "personal_access_token.txt"
        )
        token_path.parent.mkdir(parents=True)
        token_path.write_text("my-token")

        with (
            patch.object(
                sys, "argv", ["jql", "--url", "https://jira.example.com", "test"]
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("fluxx.jql.requests.get") as mock_get,
        ):
            mock_get.side_effect = requests.ConnectionError("Connection refused")

            result = main()

        assert result == 1

    def test_invalid_json_response(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test handling of invalid JSON in response."""
        token_path = (
            tmp_path
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "personal_access_token.txt"
        )
        token_path.parent.mkdir(parents=True)
        token_path.write_text("my-token")

        with (
            patch.object(
                sys, "argv", ["jql", "--url", "https://jira.example.com", "test"]
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("fluxx.jql.requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
            mock_response.text = "not json"
            mock_get.return_value = mock_response

            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "not valid JSON" in captured.err

    def test_all_options(self, tmp_path: Path) -> None:
        """Test all command-line options are passed correctly."""
        token_path = (
            tmp_path
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "personal_access_token.txt"
        )
        token_path.parent.mkdir(parents=True)
        token_path.write_text("my-token")

        with (
            patch.object(
                sys,
                "argv",
                [
                    "jql",
                    "--url",
                    "https://jira.example.com",
                    "--expand",
                    "changelog",
                    "--max-results",
                    "50",
                    "--validate-query",
                    "false",
                    "--fields",
                    "summary,status",
                    "--start-at",
                    "10",
                    "project = TEST",
                ],
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("fluxx.jql.requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.json.return_value = {"issues": []}
            mock_get.return_value = mock_response

            result = main()

        assert result == 0
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        assert params["jql"] == "project = TEST"
        assert params["expand"] == "changelog"
        assert params["maxResults"] == 50
        assert params["validateQuery"] is False
        assert params["fields"] == "summary,status"
        assert params["startAt"] == 10

    def test_validate_query_true_option(self, tmp_path: Path) -> None:
        """Test --validate-query with true value."""
        token_path = (
            tmp_path
            / ".local"
            / "share"
            / "secrets"
            / "jira.example.com"
            / "personal_access_token.txt"
        )
        token_path.parent.mkdir(parents=True)
        token_path.write_text("my-token")

        with (
            patch.object(
                sys,
                "argv",
                [
                    "jql",
                    "--url",
                    "https://jira.example.com",
                    "--validate-query",
                    "true",
                    "test",
                ],
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("fluxx.jql.requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.json.return_value = {"issues": []}
            mock_get.return_value = mock_response

            result = main()

        assert result == 0
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        assert params["validateQuery"] is True
