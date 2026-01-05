"""Jira HTTP client with rate limiting and retry logic."""

import time
from collections.abc import Iterator
from threading import Lock

import requests
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from fluxx.data.json_types import JsonObject, JsonValue


class JiraClientError(Exception):
    """Error communicating with Jira API."""

    pass


class JiraClient:
    """HTTP client for Jira REST API.

    Features:
    - Rate limiting to avoid overwhelming Jira server
    - Automatic retries with exponential backoff for transient errors
    - Bearer token authentication
    - Pagination handling for search results

    Attributes:
        server_url: Base URL of the Jira server (without trailing slash)
    """

    def __init__(
        self,
        server_url: str,
        token: str,
        rate_limit: float = 1.0,
        page_size: int = 50,
        max_retries: int = 5,
        min_retry_wait: float = 1.0,
        max_retry_wait: float = 600.0,
    ) -> None:
        """Initialize the Jira client.

        Args:
            server_url: Base URL of the Jira server (e.g., 'https://jira.example.com')
            token: Personal Access Token for authentication
            rate_limit: Maximum requests per second (default: 1.0)
            page_size: Number of results per page for search (default: 50)
            max_retries: Maximum number of retry attempts (default: 5)
            min_retry_wait: Minimum wait between retries in seconds (default: 1.0)
            max_retry_wait: Maximum wait between retries in seconds (default: 600.0)
        """
        self.server_url = server_url.rstrip("/")
        self._token = token
        self._page_size = page_size
        self._max_retries = max_retries
        self._min_retry_wait = min_retry_wait
        self._max_retry_wait = max_retry_wait

        # Set up rate limiter (simple token bucket)
        self._rate_limit = rate_limit
        self._min_interval = 1.0 / rate_limit if rate_limit > 0 else 0
        self._last_request_time = 0.0
        self._rate_lock = Lock()

        # Set up session with default headers
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limit."""
        with self._rate_lock:
            if self._min_interval > 0:
                now = time.time()
                elapsed = now - self._last_request_time
                if elapsed < self._min_interval:
                    time.sleep(self._min_interval - elapsed)
                self._last_request_time = time.time()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, str] | None = None,
        json_data: JsonObject | None = None,
    ) -> JsonObject:
        """Make an HTTP request with rate limiting and retries.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., '/rest/api/2/issue/TEST-1')
            params: Query parameters
            json_data: JSON body for POST requests

        Returns:
            JSON response as a dictionary

        Raises:
            JiraClientError: If the request fails after all retries
        """

        @retry(
            retry=retry_if_exception_type(
                (requests.exceptions.ConnectionError, _RetryableHTTPError)
            ),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(
                min=self._min_retry_wait, max=self._max_retry_wait, multiplier=2
            ),
            reraise=True,
        )
        def _do_request() -> requests.Response:
            # Apply rate limiting
            self._wait_for_rate_limit()

            url = f"{self.server_url}{endpoint}"
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
            )

            # Check for retryable errors
            if response.status_code in (429, 500, 502, 503, 504):
                raise _RetryableHTTPError(
                    f"HTTP {response.status_code}: {response.text}"
                )

            return response

        try:
            response = _do_request()
        except (RetryError, _RetryableHTTPError) as e:
            raise JiraClientError(
                f"Request failed after {self._max_retries} retries"
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise JiraClientError(f"Connection error: {e}") from e

        # Check for non-retryable errors
        if response.status_code >= 400:
            raise JiraClientError(f"HTTP {response.status_code}: {response.text}")

        result: JsonObject = response.json()
        return result

    def get_issue(
        self,
        key: str,
        fields: list[str],
        expand: list[str] | None = None,
    ) -> JsonObject:
        """Get a single issue by key.

        Args:
            key: Issue key (e.g., 'FHIR-1234')
            fields: List of field names to retrieve
            expand: Optional list of expansions (e.g., ['changelog', 'worklog'])

        Returns:
            Issue data as a dictionary

        Raises:
            JiraClientError: If the request fails
        """
        params: dict[str, str] = {"fields": ",".join(fields)}
        if expand:
            params["expand"] = ",".join(expand)

        return self._make_request(
            method="GET",
            endpoint=f"/rest/api/2/issue/{key}",
            params=params,
        )

    def search(
        self,
        jql: str,
        fields: list[str],
        expand: list[str] | None = None,
    ) -> Iterator[JsonObject]:
        """Search for issues using JQL.

        This method handles pagination automatically, yielding issues
        one at a time as they are retrieved.

        Args:
            jql: JQL query string
            fields: List of field names to retrieve
            expand: Optional list of expansions

        Yields:
            Issue data dictionaries

        Raises:
            JiraClientError: If any request fails
        """
        start_at = 0

        while True:
            # Build request body - list() creates a copy with type list[JsonValue]
            fields_json: list[JsonValue] = list(fields)
            body: JsonObject = {
                "jql": jql,
                "fields": fields_json,
                "startAt": start_at,
                "maxResults": self._page_size,
            }
            if expand:
                expand_json: list[JsonValue] = list(expand)
                body["expand"] = expand_json

            response = self._make_request(
                method="POST",
                endpoint="/rest/api/2/search",
                json_data=body,
            )

            issues_raw = response.get("issues", [])
            # Yield each issue - we trust the API returns objects
            issues_count = 0
            if isinstance(issues_raw, list):
                for issue in issues_raw:
                    if isinstance(issue, dict):
                        yield issue
                        issues_count += 1

            # Check if we've retrieved all issues
            total_raw = response.get("total", 0)
            total = total_raw if isinstance(total_raw, int) else 0
            start_at += issues_count
            if start_at >= total or issues_count == 0:
                break


class _RetryableHTTPError(Exception):
    """Internal exception for HTTP errors that should trigger a retry."""

    pass
