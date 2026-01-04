# JQL Entry Point Implementation Checklist

## Setup
- [ ] Add `requests` to dependencies in pyproject.toml
- [ ] Add `jql` console script entry point to pyproject.toml

## Implementation (src/fluxx/jql.py)
- [ ] Create argument parser with:
  - [ ] Positional JQL query argument
  - [ ] `--url` to override JIRA_API_BASE_URL
  - [ ] `--expand` option
  - [ ] `--max-results` option
  - [ ] `--validate-query` option
  - [ ] `--fields` option (default: '*all')
  - [ ] `--start-at` option
- [ ] URL/token path logic:
  - [ ] Read JIRA_API_BASE_URL from environment (or --url)
  - [ ] Parse URL to extract host, port, path
  - [ ] Build token path: ~/.local/share/secrets/{host}.{port}{path}/personal_access_token.txt (with port)
  - [ ] Build token path: ~/.local/share/secrets/{host}{path}/personal_access_token.txt (without port)
  - [ ] Read personal access token from file
- [ ] HTTP request:
  - [ ] Build query parameters (jql, expand, maxResults, validateQuery, fields, startAt)
  - [ ] Set Accept: application/json header
  - [ ] Set Authorization: Bearer {token} header
  - [ ] Make GET request to {base_url}/rest/api/2/search
  - [ ] Follow redirects (requests default behavior)
- [ ] Response handling:
  - [ ] Success: pretty-print JSON to stdout
  - [ ] Error: print status code and response body to stderr, exit non-zero

## Testing
- [ ] Write tests for URL-to-token-path conversion
- [ ] Write tests for argument parsing
- [ ] Write tests for HTTP request construction (mock requests)
- [ ] Write tests for success/error response handling

## Verification
- [ ] Run `make all_checks` to verify code quality
- [ ] Verify console script works after `pip install -e .`
