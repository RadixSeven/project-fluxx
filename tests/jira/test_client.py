"""Tests for Jira HTTP client."""

import time

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError
from responses import matchers

from fluxx.jira.client import JiraClient, JiraClientError


class TestJiraClientBasics:
    """Tests for basic JiraClient functionality."""

    @responses.activate
    def test_client_adds_bearer_token(self) -> None:
        """Verify Authorization header is set correctly."""
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-123",
            json={"key": "TEST-123", "fields": {}},
            status=200,
            match=[
                matchers.header_matcher({"Authorization": "Bearer my-secret-token"})
            ],
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="my-secret-token",
        )
        result = client.get_issue("TEST-123", fields=["summary"])

        assert result["key"] == "TEST-123"

    @responses.activate
    def test_get_issue_returns_json(self) -> None:
        """Test that get_issue returns the JSON response."""
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/FHIR-1234",
            json={
                "key": "FHIR-1234",
                "fields": {
                    "summary": "Test Issue",
                    "description": "A test description",
                },
            },
            status=200,
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
        )
        result = client.get_issue("FHIR-1234", fields=["summary", "description"])

        assert result["key"] == "FHIR-1234"
        fields = result["fields"]
        assert isinstance(fields, dict)
        assert fields["summary"] == "Test Issue"

    @responses.activate
    def test_get_issue_passes_fields_parameter(self) -> None:
        """Test that fields parameter is passed to API."""
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            json={"key": "TEST-1", "fields": {}},
            status=200,
            match=[matchers.query_param_matcher({"fields": "summary,description"})],
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
        )
        client.get_issue("TEST-1", fields=["summary", "description"])

    @responses.activate
    def test_get_issue_with_expand_parameter(self) -> None:
        """Test that expand parameter is passed to API."""
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            json={"key": "TEST-1", "fields": {}},
            status=200,
            match=[
                matchers.query_param_matcher(
                    {"fields": "summary", "expand": "changelog,worklog"}
                )
            ],
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
        )
        client.get_issue("TEST-1", fields=["summary"], expand=["changelog", "worklog"])


class TestJiraClientSearch:
    """Tests for JiraClient.search method."""

    @responses.activate
    def test_search_returns_issues(self) -> None:
        """Test that search returns issues from response."""
        responses.add(
            responses.POST,
            "https://jira.example.com/rest/api/2/search",
            json={
                "startAt": 0,
                "maxResults": 50,
                "total": 2,
                "issues": [
                    {"key": "TEST-1", "fields": {"summary": "Issue 1"}},
                    {"key": "TEST-2", "fields": {"summary": "Issue 2"}},
                ],
            },
            status=200,
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
        )
        results = list(client.search("project = TEST", fields=["summary"]))

        assert len(results) == 2
        assert results[0]["key"] == "TEST-1"
        assert results[1]["key"] == "TEST-2"

    @responses.activate
    def test_search_handles_pagination(self) -> None:
        """Test that search handles pagination correctly."""
        # First page
        responses.add(
            responses.POST,
            "https://jira.example.com/rest/api/2/search",
            json={
                "startAt": 0,
                "maxResults": 2,
                "total": 4,
                "issues": [
                    {"key": "TEST-1", "fields": {}},
                    {"key": "TEST-2", "fields": {}},
                ],
            },
            status=200,
        )
        # Second page
        responses.add(
            responses.POST,
            "https://jira.example.com/rest/api/2/search",
            json={
                "startAt": 2,
                "maxResults": 2,
                "total": 4,
                "issues": [
                    {"key": "TEST-3", "fields": {}},
                    {"key": "TEST-4", "fields": {}},
                ],
            },
            status=200,
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
            page_size=2,
        )
        results = list(client.search("project = TEST", fields=["summary"]))

        assert len(results) == 4
        assert [r["key"] for r in results] == ["TEST-1", "TEST-2", "TEST-3", "TEST-4"]

    @responses.activate
    def test_search_passes_jql_and_fields(self) -> None:
        """Test that search passes JQL and fields in request body."""
        responses.add(
            responses.POST,
            "https://jira.example.com/rest/api/2/search",
            json={"startAt": 0, "maxResults": 50, "total": 0, "issues": []},
            status=200,
            match=[
                matchers.json_params_matcher(
                    {
                        "jql": "project = FHIR",
                        "fields": ["summary", "description"],
                        "startAt": 0,
                        "maxResults": 50,
                    }
                )
            ],
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
        )
        list(client.search("project = FHIR", fields=["summary", "description"]))

    @responses.activate
    def test_search_with_expand(self) -> None:
        """Test that search passes expand parameter."""
        responses.add(
            responses.POST,
            "https://jira.example.com/rest/api/2/search",
            json={"startAt": 0, "maxResults": 50, "total": 0, "issues": []},
            status=200,
            match=[
                matchers.json_params_matcher(
                    {
                        "jql": "project = FHIR",
                        "fields": ["summary"],
                        "expand": ["changelog"],
                        "startAt": 0,
                        "maxResults": 50,
                    }
                )
            ],
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
        )
        list(client.search("project = FHIR", fields=["summary"], expand=["changelog"]))


class TestJiraClientRetries:
    """Tests for retry behavior."""

    @responses.activate
    def test_client_retries_on_5xx(self) -> None:
        """First request returns 503, second succeeds."""
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            json={"error": "Service Unavailable"},
            status=503,
        )
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            json={"key": "TEST-1", "fields": {}},
            status=200,
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
            min_retry_wait=0.01,  # Fast retry for tests
            max_retry_wait=0.02,
        )
        result = client.get_issue("TEST-1", fields=["summary"])

        assert result["key"] == "TEST-1"
        assert len(responses.calls) == 2

    @responses.activate
    def test_client_retries_on_429(self) -> None:
        """Client retries on 429 Too Many Requests."""
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            json={"error": "Too Many Requests"},
            status=429,
        )
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            json={"key": "TEST-1", "fields": {}},
            status=200,
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
            min_retry_wait=0.01,
            max_retry_wait=0.02,
        )
        result = client.get_issue("TEST-1", fields=["summary"])

        assert result["key"] == "TEST-1"
        assert len(responses.calls) == 2

    @responses.activate
    def test_client_gives_up_after_max_retries(self) -> None:
        """Should raise after exhausting retries."""
        for _ in range(5):  # Max retries
            responses.add(
                responses.GET,
                "https://jira.example.com/rest/api/2/issue/TEST-1",
                json={"error": "Service Unavailable"},
                status=503,
            )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
            max_retries=3,
            min_retry_wait=0.01,
            max_retry_wait=0.02,
        )

        with pytest.raises(JiraClientError, match="Request failed"):
            client.get_issue("TEST-1", fields=["summary"])

    @responses.activate
    def test_client_retries_on_connection_error(self) -> None:
        """Client retries on connection errors."""
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            body=RequestsConnectionError("Connection refused"),
        )
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            json={"key": "TEST-1", "fields": {}},
            status=200,
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
            min_retry_wait=0.01,
            max_retry_wait=0.02,
        )
        result = client.get_issue("TEST-1", fields=["summary"])

        assert result["key"] == "TEST-1"

    @responses.activate
    def test_client_gives_up_after_max_connection_errors(self) -> None:
        """Should raise after exhausting retries with connection errors."""
        for _ in range(5):
            responses.add(
                responses.GET,
                "https://jira.example.com/rest/api/2/issue/TEST-1",
                body=RequestsConnectionError("Connection refused"),
            )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
            max_retries=3,
            min_retry_wait=0.01,
            max_retry_wait=0.02,
        )

        with pytest.raises(JiraClientError, match="Connection error"):
            client.get_issue("TEST-1", fields=["summary"])


class TestJiraClientRateLimiting:
    """Tests for rate limiting behavior."""

    @responses.activate
    def test_client_rate_limits_requests(self) -> None:
        """Verify requests are spaced by rate limit interval."""
        for _ in range(3):
            responses.add(
                responses.GET,
                "https://jira.example.com/rest/api/2/issue/TEST-1",
                json={"key": "TEST-1", "fields": {}},
                status=200,
            )

        # 10 requests per second = 0.1 second interval
        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
            rate_limit=10.0,
        )

        start = time.time()
        client.get_issue("TEST-1", fields=["summary"])
        client.get_issue("TEST-1", fields=["summary"])
        client.get_issue("TEST-1", fields=["summary"])
        elapsed = time.time() - start

        # With rate limit of 10/sec, 3 requests should take at least 0.2 seconds
        # (first request immediate, then 0.1s wait, then 0.1s wait)
        assert elapsed >= 0.15  # Allow some tolerance


class TestJiraClientErrors:
    """Tests for error handling."""

    @responses.activate
    def test_client_raises_on_4xx(self) -> None:
        """Client raises error on 4xx responses (except 429)."""
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            json={"errorMessages": ["Issue does not exist"]},
            status=404,
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="token",
        )

        with pytest.raises(JiraClientError, match="404"):
            client.get_issue("TEST-1", fields=["summary"])

    @responses.activate
    def test_client_raises_on_401(self) -> None:
        """Client raises error on authentication failure."""
        responses.add(
            responses.GET,
            "https://jira.example.com/rest/api/2/issue/TEST-1",
            json={"errorMessages": ["Unauthorized"]},
            status=401,
        )

        client = JiraClient(
            server_url="https://jira.example.com",
            token="invalid-token",
        )

        with pytest.raises(JiraClientError, match="401"):
            client.get_issue("TEST-1", fields=["summary"])

    def test_client_normalizes_server_url(self) -> None:
        """Client strips trailing slash from server URL."""
        client = JiraClient(
            server_url="https://jira.example.com/",
            token="token",
        )
        assert client.server_url == "https://jira.example.com"
