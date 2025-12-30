"""Project persistence (save/load) functionality.

Handles saving and loading Project Fluxx projects to/from JSON files.
"""

import json
from pathlib import Path

from fluxx.data.models import Project


class PersistenceError(Exception):
    """Base exception for persistence errors."""

    pass


class VersionError(PersistenceError):
    """Raised when file version is incompatible."""

    pass


class FileFormatError(PersistenceError):
    """Raised when file format is invalid."""

    pass


def save_project(project: Project, path: Path) -> None:
    """Save a project to a .fluxx file.

    Args:
        project: The project to save
        path: Path to save the file to (should have .fluxx extension)

    Raises:
        PersistenceError: If saving fails
    """
    try:
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize project to JSON using Pydantic
        json_data = project.model_dump(mode="json")

        # Write to file with pretty formatting
        with path.open("w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

    except OSError as e:
        raise PersistenceError(f"Failed to save project to {path}: {e}") from e
    except Exception as e:
        raise PersistenceError(f"Unexpected error saving project: {e}") from e


def load_project(path: Path) -> Project:
    """Load a project from a .fluxx file.

    Args:
        path: Path to the .fluxx file to load

    Returns:
        The loaded Project

    Raises:
        PersistenceError: If the file doesn't exist or can't be read
        FileFormatError: If the file format is invalid
        VersionError: If the file version is incompatible
    """
    try:
        # Check that file exists
        if not path.exists():
            raise PersistenceError(f"File does not exist: {path}")

        # Read and parse JSON
        with path.open("r", encoding="utf-8") as f:
            json_data = json.load(f)

    except json.JSONDecodeError as e:
        raise FileFormatError(f"Invalid JSON in file {path}: {e}") from e
    except OSError as e:
        raise PersistenceError(f"Failed to read file {path}: {e}") from e

    # Validate that it's a dict (basic format check)
    if not isinstance(json_data, dict):
        raise FileFormatError(f"File {path} does not contain a valid project")

    # Check version compatibility
    version = json_data.get("version")
    if not version:
        raise FileFormatError(f"File {path} missing version field")

    # For now, we only support version 1.0
    # In the future, this would include migration logic
    if version != "1.0":
        raise VersionError(
            f"File version {version} is not compatible with this version of Fluxx "
            f"(supports 1.0)"
        )

    # Deserialize using Pydantic
    try:
        project = Project.model_validate(json_data)
    except Exception as e:
        raise FileFormatError(f"Invalid project data in {path}: {e}") from e

    return project
