"""CLI tool to remove history from a Project Fluxx file.

Creates a clean copy of a .fluxx file with only the current DAG state,
removing all version history. Useful for creating minimal example files.
"""

import argparse
import sys
from pathlib import Path

from fluxx.data.models import (
    DAGVersionId,
    PersistentBranch,
    PersistentObjectId,
    PersistentTask,
    Project,
)
from fluxx.data.persistence import load_project, save_project


def remove_history(project: Project) -> Project:
    """Create a new project with history removed.

    Keeps only the current version of all tasks and branches.
    Clears history events and simulations.

    Args:
        project: The source project

    Returns:
        A new project with no history
    """
    current_version = project.dag.current_version_id

    # Create new persistent tasks with only current version
    new_persistent_tasks: dict[PersistentObjectId, PersistentTask] = {}
    for persistent_id, persistent_task in project.persistent_tasks.items():
        if current_version in persistent_task.versions:
            new_persistent_tasks[persistent_id] = PersistentTask(
                id=persistent_task.id,
                versions={current_version: persistent_task.versions[current_version]},
            )

    # Create new persistent branches with only current version
    new_persistent_branches: dict[PersistentObjectId, PersistentBranch] = {}
    for persistent_id, persistent_branch in project.persistent_branches.items():
        if current_version in persistent_branch.versions:
            new_persistent_branches[persistent_id] = PersistentBranch(
                id=persistent_branch.id,
                versions={current_version: persistent_branch.versions[current_version]},
            )

    # Create new DAG version ID for the clean project
    clean_version = DAGVersionId(f"{current_version}_clean")

    # Remap versions to the clean version ID
    remapped_tasks: dict[PersistentObjectId, PersistentTask] = {}
    for persistent_id, persistent_task in new_persistent_tasks.items():
        task = persistent_task.versions[current_version]
        remapped_tasks[persistent_id] = PersistentTask(
            id=persistent_task.id,
            versions={clean_version: task},
        )

    remapped_branches: dict[PersistentObjectId, PersistentBranch] = {}
    for persistent_id, persistent_branch in new_persistent_branches.items():
        branch = persistent_branch.versions[current_version]
        remapped_branches[persistent_id] = PersistentBranch(
            id=persistent_branch.id,
            versions={clean_version: branch},
        )

    # Create clean project
    return Project(
        version=project.version,
        metadata=project.metadata,
        workers=project.workers,
        dag=project.dag.model_copy(
            update={
                "current_version_id": clean_version,
            }
        ),
        persistent_tasks=remapped_tasks,
        persistent_branches=remapped_branches,
        history_events=[],
        current_event_id=None,
        simulations=[],
    )


def main() -> int:
    """Entry point for fluxx-remove-history CLI tool.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        prog="fluxx-remove-history",
        description="Remove history from a Project Fluxx file",
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Input .fluxx file",
    )
    parser.add_argument(
        "output_file",
        type=Path,
        help="Output .fluxx file (will be created without history)",
    )

    args = parser.parse_args()

    input_path: Path = args.input_file
    output_path: Path = args.output_file

    # Validate input file exists
    if not input_path.exists():
        print(f"Error: Input file does not exist: {input_path}", file=sys.stderr)
        return 1

    # Prevent overwriting input file
    if input_path.resolve() == output_path.resolve():
        print("Error: Input and output files must be different", file=sys.stderr)
        return 1

    try:
        # Load project
        project = load_project(input_path)

        # Remove history
        clean_project = remove_history(project)

        # Save clean project
        save_project(clean_project, output_path)

        print(f"Created {output_path} without history")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
