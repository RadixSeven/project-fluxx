"""Tests for project persistence."""

import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from fluxx.data import (
    FileFormatError,
    PersistenceError,
    VersionError,
    load_project,
    save_project,
)
from fluxx.data.models import (
    DAG,
    Branch,
    BranchId,
    DAGId,
    DAGVersionId,
    PossibleWorld,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    Task,
    TaskId,
    Worker,
    WorkerId,
)


@pytest.fixture
def sample_project() -> Generator[Project]:
    """Create a sample project for testing."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
    worker = Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)

    yield Project(
        metadata=metadata,
        dag=dag,
        workers=[worker],
    )


def test_save_and_load_project(sample_project: Project, tmp_path: Path) -> None:
    """Test basic save and load functionality."""
    file_path = tmp_path / "test.fluxx"

    # Save the project
    save_project(sample_project, file_path)

    # Verify file exists
    assert file_path.exists()

    # Load the project
    loaded_project = load_project(file_path)

    # Verify loaded project matches original
    assert loaded_project.version == sample_project.version
    assert loaded_project.metadata.name == sample_project.metadata.name
    assert len(loaded_project.workers) == len(sample_project.workers)
    assert loaded_project.workers[0].name == sample_project.workers[0].name
    assert loaded_project.dag.id == sample_project.dag.id


def test_save_creates_directory(sample_project: Project, tmp_path: Path) -> None:
    """Test that save_project creates parent directories if needed."""
    file_path = tmp_path / "subdir" / "another" / "test.fluxx"

    # Save should create the directory structure
    save_project(sample_project, file_path)

    assert file_path.exists()
    assert file_path.parent.exists()


def test_save_creates_valid_json(sample_project: Project, tmp_path: Path) -> None:
    """Test that saved file contains valid JSON."""
    file_path = tmp_path / "test.fluxx"

    save_project(sample_project, file_path)

    # Verify we can parse it as JSON
    with file_path.open("r") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    assert "version" in data
    assert "metadata" in data
    assert "dag" in data
    assert "workers" in data


def test_load_nonexistent_file(tmp_path: Path) -> None:
    """Test loading a file that doesn't exist."""
    file_path = tmp_path / "nonexistent.fluxx"

    with pytest.raises(PersistenceError, match="File does not exist"):
        load_project(file_path)


def test_load_invalid_json(tmp_path: Path) -> None:
    """Test loading a file with invalid JSON."""
    file_path = tmp_path / "invalid.fluxx"

    # Write invalid JSON
    with file_path.open("w") as f:
        f.write("{ this is not valid JSON }")

    with pytest.raises(FileFormatError, match="Invalid JSON"):
        load_project(file_path)


def test_load_non_dict_json(tmp_path: Path) -> None:
    """Test loading a file with JSON that isn't a dict."""
    file_path = tmp_path / "array.fluxx"

    # Write a JSON array instead of object
    with file_path.open("w") as f:
        json.dump([1, 2, 3], f)

    with pytest.raises(FileFormatError, match="does not contain a valid project"):
        load_project(file_path)


def test_load_missing_version(tmp_path: Path) -> None:
    """Test loading a file missing the version field."""
    file_path = tmp_path / "no_version.fluxx"

    # Write JSON without version field
    with file_path.open("w") as f:
        json.dump({"metadata": {"name": "Test"}}, f)

    with pytest.raises(FileFormatError, match="missing version field"):
        load_project(file_path)


def test_load_incompatible_version(tmp_path: Path) -> None:
    """Test loading a file with incompatible version."""
    file_path = tmp_path / "wrong_version.fluxx"

    # Write JSON with unsupported version
    with file_path.open("w") as f:
        json.dump({"version": "2.0", "metadata": {"name": "Test"}}, f)

    with pytest.raises(VersionError, match="version 2.0 is not compatible"):
        load_project(file_path)


def test_load_invalid_project_data(tmp_path: Path) -> None:
    """Test loading a file with invalid project structure."""
    file_path = tmp_path / "invalid_project.fluxx"

    # Write JSON with correct version but invalid project data
    with file_path.open("w") as f:
        json.dump(
            {
                "version": "1.0",
                "metadata": "this should be an object",  # Invalid
            },
            f,
        )

    with pytest.raises(FileFormatError, match="Invalid project data"):
        load_project(file_path)


def test_save_and_load_complex_project(tmp_path: Path) -> None:
    """Test saving and loading a project with more complex data."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Complex Project",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))

    # Add multiple workers
    workers = [
        Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0),
        Worker(id=WorkerId("w2"), name="Bob", hours_per_workday=6.0),
    ]

    project = Project(
        metadata=metadata,
        dag=dag,
        workers=workers,
    )

    file_path = tmp_path / "complex.fluxx"

    # Save and load
    save_project(project, file_path)
    loaded = load_project(file_path)

    # Verify all data
    assert len(loaded.workers) == 2
    assert loaded.workers[0].name == "Alice"
    assert loaded.workers[1].name == "Bob"
    assert loaded.workers[1].hours_per_workday == 6.0


def test_save_preserves_unicode(sample_project: Project, tmp_path: Path) -> None:
    """Test that Unicode characters are preserved correctly."""
    sample_project.metadata.name = "Test Project 日本語 🚀"
    file_path = tmp_path / "unicode.fluxx"

    save_project(sample_project, file_path)
    loaded = load_project(file_path)

    assert loaded.metadata.name == "Test Project 日本語 🚀"


def test_save_to_readonly_location(sample_project: Project, tmp_path: Path) -> None:
    """Test saving to a read-only location raises PersistenceError."""
    # Create a read-only directory
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o444)  # Read-only

    file_path = readonly_dir / "test.fluxx"

    try:
        with pytest.raises(PersistenceError, match="Failed to save project"):
            save_project(sample_project, file_path)
    finally:
        # Clean up: restore write permissions
        readonly_dir.chmod(0o755)


def test_load_from_unreadable_file(sample_project: Project, tmp_path: Path) -> None:
    """Test loading from an unreadable file raises PersistenceError."""
    file_path = tmp_path / "unreadable.fluxx"

    # First save the project
    save_project(sample_project, file_path)

    # Make file unreadable
    file_path.chmod(0o000)

    try:
        with pytest.raises(PersistenceError, match="Failed to read file"):
            load_project(file_path)
    finally:
        # Clean up: restore read permissions
        file_path.chmod(0o644)


def test_save_with_serialization_error(sample_project: Project, tmp_path: Path) -> None:
    """Test that serialization errors are caught and wrapped."""
    file_path = tmp_path / "test.fluxx"

    # Mock json.dump to raise an exception
    with patch("fluxx.data.persistence.json.dump") as mock_dump:
        mock_dump.side_effect = ValueError("Mock serialization error")

        with pytest.raises(PersistenceError, match="Unexpected error saving project"):
            save_project(sample_project, file_path)


def test_round_trip_with_tasks_and_branches(tmp_path: Path) -> None:
    """Test round-trip with tasks and branches in persistent objects."""
    from fluxx.data.models import PersistentBranch, PersistentObjectId, PersistentTask

    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Project with Nodes",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))

    # Create a task and branch
    task = Task(id=TaskId("t1"), title="Task 1", description="First task")
    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="First branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Create persistent objects
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={DAGVersionId("v1"): task},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={DAGVersionId("v1"): branch},
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    file_path = tmp_path / "nodes.fluxx"

    # Save and load
    save_project(project, file_path)
    loaded = load_project(file_path)

    # Verify persistent objects
    assert len(loaded.persistent_tasks) == 1
    assert len(loaded.persistent_branches) == 1

    # Verify task data
    loaded_task = loaded.persistent_tasks[PersistentObjectId("pt1")].versions[
        DAGVersionId("v1")
    ]
    assert loaded_task.title == "Task 1"

    # Verify branch data
    loaded_branch = loaded.persistent_branches[PersistentObjectId("pb1")].versions[
        DAGVersionId("v1")
    ]
    assert loaded_branch.title == "Branch 1"
    assert len(loaded_branch.possible_worlds) == 2
