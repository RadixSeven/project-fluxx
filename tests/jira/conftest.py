"""Pytest configuration and fixtures for Jira tests."""

import importlib.resources
import json

from fluxx.data.json_types import JsonObject


def load_fixture(name: str) -> JsonObject:
    """Load JSON fixture using importlib.resources for portability.

    Args:
        name: Name of the fixture file (e.g., 'issue_basic.json')

    Returns:
        Parsed JSON as a dictionary
    """
    files = importlib.resources.files("tests.jira.fixtures")
    traversable = files.joinpath(name)
    content = traversable.read_text()
    result: JsonObject = json.loads(content)
    return result
