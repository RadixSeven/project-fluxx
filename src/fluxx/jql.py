"""CLI tool to query Jira using JQL via the REST API.

Reads the Jira base URL from JIRA_API_BASE_URL environment variable
(or --url parameter) and derives the personal access token path from the URL.

For https://example.com:port/path/to/jira, looks in:
    ~/.local/share/secrets/example.com.port/path/to/jira/personal_access_token.txt

For https://example.com/path/to/jira (no port), looks in:
    ~/.local/share/secrets/example.com/path/to/jira/personal_access_token.txt
"""

import argparse
import json
import os
import sys

import requests

# Import auth functions from the jira module (re-export for backward compatibility)
from fluxx.jira.auth import TokenNotFoundError, get_token_path, read_token

# Re-export for tests that import from fluxx.jql
__all__ = [
    "get_token_path",
    "read_token",
    "build_query_params",
    "execute_search",
    "main",
]


def build_query_params(
    jql: str,
    expand: str | None,
    max_results: int | None,
    validate_query: bool | None,
    fields: str,
    start_at: int | None,
) -> dict[str, str | int | bool]:
    """Build the query parameters for the search API call.

    Args:
        jql: The JQL query string
        expand: Optional expand parameter
        max_results: Optional maxResults parameter
        validate_query: Optional validateQuery parameter
        fields: Fields to return (default: '*all')
        start_at: Optional startAt parameter

    Returns:
        Dictionary of query parameters
    """
    params: dict[str, str | int | bool] = {"jql": jql, "fields": fields}

    if expand is not None:
        params["expand"] = expand
    if max_results is not None:
        params["maxResults"] = max_results
    if validate_query is not None:
        params["validateQuery"] = validate_query
    if start_at is not None:
        params["startAt"] = start_at

    return params


def execute_search(
    base_url: str,
    token: str,
    params: dict[str, str | int | bool],
) -> requests.Response:
    """Execute the Jira search API call.

    Args:
        base_url: The Jira base URL
        token: The personal access token
        params: Query parameters

    Returns:
        The response object
    """
    search_url = f"{base_url.rstrip('/')}/rest/api/2/search"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    return requests.get(
        search_url,
        headers=headers,
        params=params,
        allow_redirects=True,
        timeout=30,
    )


def main() -> int:
    """Entry point for jql CLI tool.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        prog="jql",
        description="Query Jira using JQL via the REST API",
    )
    parser.add_argument(
        "query",
        help="The JQL query string",
    )
    parser.add_argument(
        "--url",
        help="Jira base URL (overrides JIRA_API_BASE_URL environment variable)",
    )
    parser.add_argument(
        "--expand",
        help="Expand parameter for the search API",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        help="Maximum number of results to return",
    )
    parser.add_argument(
        "--validate-query",
        type=lambda x: x.lower() in ("true", "1", "yes"),
        metavar="BOOL",
        help="Whether to validate the JQL query (true/false)",
    )
    parser.add_argument(
        "--fields",
        default="*all",
        help="Fields to return (default: '*all')",
    )
    parser.add_argument(
        "--start-at",
        type=int,
        help="Index of the first result to return",
    )

    args = parser.parse_args()

    # Get base URL from --url or environment variable
    base_url: str | None = args.url or os.environ.get("JIRA_API_BASE_URL")
    if not base_url:
        print(
            "Error: No Jira URL specified. "
            "Use --url or set JIRA_API_BASE_URL environment variable.",
            file=sys.stderr,
        )
        return 1

    # Get token path and read token
    token_path = get_token_path(base_url)
    try:
        token = read_token(token_path)
    except TokenNotFoundError as e:
        print(
            f"Error: {e}",
            file=sys.stderr,
        )
        return 1
    except PermissionError:
        print(
            f"Error: Cannot read personal access token at {token_path}",
            file=sys.stderr,
        )
        return 1

    # Build query parameters
    params = build_query_params(
        jql=args.query,
        expand=args.expand,
        max_results=args.max_results,
        validate_query=args.validate_query,
        fields=args.fields,
        start_at=args.start_at,
    )

    # Execute the search
    try:
        response = execute_search(base_url, token, params)
    except requests.RequestException as e:
        print(f"Error: Request failed: {e}", file=sys.stderr)
        return 1

    # Handle response
    if response.ok:
        try:
            data = response.json()
            print(json.dumps(data, indent=2))
            return 0
        except json.JSONDecodeError:
            print("Error: Response is not valid JSON", file=sys.stderr)
            print(response.text, file=sys.stderr)
            return 1
    else:
        print(
            f"Error: HTTP {response.status_code} {response.reason}",
            file=sys.stderr,
        )
        print(response.text, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
