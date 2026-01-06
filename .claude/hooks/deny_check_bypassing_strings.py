#!/usr/bin/env python3
"""
PreToolUse hook that denies tool calls containing forbidden strings associated
with accidentally disabling type safety or code style checks.
"""

import json
import sys

DENIED_STRINGS = [
    "approved_exceptions_to_static_analysis_policy.txt",
    "regenerate-policy-exceptions",
    "Makefile",
]


def contains_denied_string(obj: object) -> str | None:
    """Recursively check if any denied string appears in the object.

    Returns:
        The denied string if found, None otherwise.
    """
    if isinstance(obj, str):
        for denied in DENIED_STRINGS:
            if denied in obj:
                return denied
    elif isinstance(obj, dict):
        for value in obj.values():
            if found := contains_denied_string(value):
                return found
    elif isinstance(obj, list):
        for item in obj:
            if found := contains_denied_string(item):
                return found
    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    tool_input = input_data.get("tool_input", {})

    if found := contains_denied_string(tool_input):
        print(
            f"Tool call denied: contains string '{found}' "
            f"associated with accidentally bypassing type safety or "
            f"code style checks.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
