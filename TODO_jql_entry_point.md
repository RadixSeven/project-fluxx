# JQL Entry Point Implementation Checklist

## Setup
- [x] Add `requests` to dependencies in pyproject.toml
- [x] Add `jql` console script entry point to pyproject.toml

## Implementation (src/fluxx/jql.py)
- [x] Create argument parser with:
  - [x] Positional JQL query argument
  - [x] `--url` to override JIRA_API_BASE_URL
  - [x] `--expand` option
  - [x] `--max-results` option
  - [x] `--validate-query` option
  - [x] `--fields` option (default: '*all')
  - [x] `--start-at` option
- [x] URL/token path logic:
  - [x] Read JIRA_API_BASE_URL from environment (or --url)
  - [x] Parse URL to extract host, port, path
  - [x] Build token path: ~/.local/share/secrets/{host}.{port}{path}/personal_access_token.txt (with port)
  - [x] Build token path: ~/.local/share/secrets/{host}{path}/personal_access_token.txt (without port)
  - [x] Read personal access token from file
- [x] HTTP request:
  - [x] Build query parameters (jql, expand, maxResults, validateQuery, fields, startAt)
  - [x] Set Accept: application/json header
  - [x] Set Authorization: Bearer {token} header
  - [x] Make GET request to {base_url}/rest/api/2/search
  - [x] Follow redirects (requests default behavior)
- [x] Response handling:
  - [x] Success: pretty-print JSON to stdout
  - [x] Error: print status code and response body to stderr, exit non-zero

## Testing
- [x] Write tests for URL-to-token-path conversion
- [x] Write tests for argument parsing
- [x] Write tests for HTTP request construction (mock requests)
- [x] Write tests for success/error response handling

## Verification
- [x] Run `make all_checks` to verify code quality
- [x] Verify console script works after `pip install -e .`
