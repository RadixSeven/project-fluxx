"""Central controller managing Project state and coordinating all GUI operations."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from fluxx.data import (
    add_branch,
    add_dependency,
    add_sibling_subtask,
    add_task,
    can_redo,
    can_undo,
    convert_to_parent_task,
    load_project,
    redo,
    remove_dependency,
    save_project,
    undo,
    update_branch,
    update_task,
)
from fluxx.data.models import (
    DAG,
    BranchId,
    DAGId,
    DAGVersionId,
    Dependency,
    NodeId,
    PossibleWorld,
    Project,
    ProjectMetadata,
    ShiftedLognormal,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)


class ProjectController(QObject):
    """Controller managing all Project state and operations.

    This is the central coordinator that all GUI widgets interact with.
    It maintains the current Project state, handles all modifications,
    and emits signals when state changes occur.

    Signals:
        project_changed: Emitted when the Project instance changes
        selection_changed: Emitted when the selected node changes
        file_path_changed: Emitted when the current file path changes
        modified_changed: Emitted when the modified state changes
    """

    # Qt signals
    project_changed = Signal(Project)
    selection_changed = Signal(object)  # Optional[NodeId]
    file_path_changed = Signal(object)  # Optional[Path]
    modified_changed = Signal(bool)

    def __init__(self) -> None:
        """Initialize the controller with an empty project."""
        super().__init__()
        self._project: Project | None = None
        self._file_path: Path | None = None
        self._modified: bool = False
        self._selected_node_id: NodeId | None = None

        # Create default empty project
        self.new_project("Untitled")

    def get_project(self) -> Project:
        """Get the current project.

        Returns:
            Current Project instance

        Raises:
            RuntimeError: If no project is loaded (should never happen)
        """
        if self._project is None:
            raise RuntimeError("No project loaded")
        return self._project

    def get_file_path(self) -> Path | None:
        """Get the current file path.

        Returns:
            Path to current file, or None if not saved
        """
        return self._file_path

    def is_modified(self) -> bool:
        """Check if project has unsaved changes.

        Returns:
            True if project has been modified since last save
        """
        return self._modified

    def get_selected_node_id(self) -> NodeId | None:
        """Get the currently selected node ID.

        Returns:
            NodeId of selected node, or None if no selection
        """
        return self._selected_node_id

    def _set_project(self, project: Project, mark_modified: bool = True) -> None:
        """Set the current project and emit signals.

        Args:
            project: New project instance
            mark_modified: Whether to mark project as modified
        """
        self._project = project

        if mark_modified and not self._modified:
            self._modified = True
            self.modified_changed.emit(True)

        self.project_changed.emit(project)

    def _set_file_path(self, path: Path | None) -> None:
        """Set the current file path and emit signal.

        Args:
            path: New file path, or None to clear
        """
        self._file_path = path
        self.file_path_changed.emit(path)

    def _clear_modified(self) -> None:
        """Clear the modified flag and emit signal."""
        if self._modified:
            self._modified = False
            self.modified_changed.emit(False)

    # File operations

    def new_project(self, name: str) -> None:
        """Create a new empty project.

        Args:
            name: Name for the new project
        """
        now = datetime.now(UTC)
        metadata = ProjectMetadata(
            name=name,
            created=now,
            last_modified=now,
        )
        dag = DAG(
            id=DAGId(f"dag_{now.timestamp()}"),
            current_version_id=DAGVersionId(f"v_{now.timestamp()}"),
        )

        project = Project(
            metadata=metadata,
            dag=dag,
            workers=[],
        )

        self._project = project
        self._set_file_path(None)
        self._clear_modified()
        self._selected_node_id = None
        self.project_changed.emit(project)
        self.selection_changed.emit(None)

    def open_project(self, path: Path) -> None:
        """Open a project from a file.

        Args:
            path: Path to project file

        Raises:
            Exception: If file cannot be loaded
        """
        project = load_project(path)
        self._project = project
        self._set_file_path(path)
        self._clear_modified()
        self._selected_node_id = None
        self.project_changed.emit(project)
        self.selection_changed.emit(None)

    def save_project(self) -> None:
        """Save project to current file.

        Raises:
            ValueError: If no file path is set (use save_project_as first)
        """
        if self._file_path is None:
            raise ValueError("No file path set - use save_project_as")

        save_project(self.get_project(), self._file_path)
        self._clear_modified()

    def save_project_as(self, path: Path) -> None:
        """Save project to a new file.

        Args:
            path: Path to save project to
        """
        save_project(self.get_project(), path)
        self._set_file_path(path)
        self._clear_modified()

    # Node operations

    def create_task(
        self,
        title: str,
        description: str = "",
        parent_id: TaskId | None = None,
        duration_distribution: Triangular | ShiftedLognormal | None = None,
        allowed_workers: list[WorkerId] | None = None,
    ) -> TaskId:
        """Create a new task.

        Args:
            title: Task title
            description: Task description
            parent_id: Parent node ID (for subtasks)
            duration_distribution: Duration distribution (for leaf tasks)
            allowed_workers: List of allowed worker IDs (None means all workers allowed)

        Returns:
            ID of created task
        """
        project, task_id = add_task(
            self.get_project(),
            title=title,
            description=description,
            parent_id=parent_id,
            duration_distribution=duration_distribution,
            allowed_workers=allowed_workers,
        )
        self._set_project(project)
        return task_id

    def update_task(self, task_id: TaskId, **kwargs: Any) -> None:
        """Update a task's properties.

        Args:
            task_id: ID of task to update
            **kwargs: Fields to update (title, description, etc.)
        """
        project = update_task(self.get_project(), task_id, **kwargs)
        self._set_project(project)

    def create_branch(
        self,
        title: str,
        description: str = "",
        possible_worlds: list[PossibleWorld] | None = None,
    ) -> BranchId:
        """Create a new branch.

        Args:
            title: Branch title
            description: Branch description
            possible_worlds: List of possible worlds

        Returns:
            ID of created branch
        """
        project, branch_id = add_branch(
            self.get_project(),
            title=title,
            description=description,
            possible_worlds=possible_worlds or [],
        )
        self._set_project(project)
        return branch_id

    def update_branch(self, branch_id: BranchId, **kwargs: Any) -> None:
        """Update a branch's properties.

        Args:
            branch_id: ID of branch to update
            **kwargs: Fields to update (title, description, possible_worlds)
        """
        project = update_branch(self.get_project(), branch_id, **kwargs)
        self._set_project(project)

    def add_dependency(self, source_node_id: NodeId, dependency: Dependency) -> None:
        """Add a dependency to a node.

        Args:
            source_node_id: Source node ID
            dependency: Dependency to add
        """
        project = add_dependency(self.get_project(), source_node_id, dependency)
        self._set_project(project)

    def remove_dependency(self, source_node_id: NodeId, dependency: Dependency) -> None:
        """Remove a dependency from a node.

        Args:
            source_node_id: Source node ID
            dependency: Dependency to remove
        """
        project = remove_dependency(self.get_project(), source_node_id, dependency)
        self._set_project(project)

    def convert_to_parent(self, task_id: TaskId, child_title: str) -> TaskId:
        """Convert a leaf task to a parent task with one child.

        The child task inherits the duration distribution. Two required dependencies
        are created:
        - child.start >= parent.start (added to child)
        - parent.end >= child.end (added to parent)

        Args:
            task_id: ID of the task to convert to parent
            child_title: Title for the new child task

        Returns:
            ID of the newly created child task

        Raises:
            DAGOperationError: If the task is already a parent or doesn't exist
        """
        project, child_id = convert_to_parent_task(
            self.get_project(), task_id, child_title
        )
        self._set_project(project)
        # Select the newly created child
        self.select_node(NodeId(child_id))
        return child_id

    def add_sibling(
        self,
        task_id: TaskId,
        sibling_title: str,
        duration_distribution: Triangular | ShiftedLognormal | None = None,
    ) -> TaskId:
        """Add a sibling subtask to an existing subtask.

        Creates a new task with the same parent as the given task. Two required
        dependencies are created:
        - sibling.start >= parent.start (added to sibling)
        - parent.end >= sibling.end (added to parent)

        Args:
            task_id: ID of an existing subtask (to get parent)
            sibling_title: Title for the new sibling task
            duration_distribution: Duration distribution for the new sibling

        Returns:
            ID of the newly created sibling task

        Raises:
            DAGOperationError: If the task doesn't have a parent or doesn't exist
        """
        project, sibling_id = add_sibling_subtask(
            self.get_project(), task_id, sibling_title, duration_distribution
        )
        self._set_project(project)
        # Select the newly created sibling
        self.select_node(NodeId(sibling_id))
        return sibling_id

    # History operations

    def can_undo(self) -> bool:
        """Check if undo is available.

        Returns:
            True if undo is possible
        """
        return can_undo(self.get_project())

    def can_redo(self) -> bool:
        """Check if redo is available.

        Returns:
            True if redo is possible
        """
        return can_redo(self.get_project())

    def undo(self) -> None:
        """Undo the last operation.

        Raises:
            UndoError: If there's nothing to undo
        """
        project = undo(self.get_project())
        self._set_project(project)

    def redo(self) -> None:
        """Redo the next operation.

        Raises:
            UndoError: If there's nothing to redo
        """
        project = redo(self.get_project())
        self._set_project(project)

    # Worker management

    def add_worker(
        self,
        name: str,
        hours_per_workday: float,
        worker_id: str | None = None,
        description: str | None = None,
    ) -> WorkerId:
        """Add a worker to the project.

        Args:
            name: Worker name
            hours_per_workday: Hours per workday
            worker_id: Optional ID for distinguishing same-named workers
            description: Optional worker description

        Returns:
            The WorkerId of the new worker
        """
        from fluxx.data.id_generation import generate_worker_id

        new_worker_id = generate_worker_id()
        worker = Worker(
            id=new_worker_id,
            name=name,
            worker_id=worker_id,
            description=description,
            hours_per_workday=hours_per_workday,
        )

        # Create updated project with new worker
        project = self.get_project()
        updated_project = project.model_copy(
            update={"workers": project.workers + [worker]}
        )

        self._set_project(updated_project)
        return new_worker_id

    def update_worker(
        self,
        worker_id: WorkerId,
        name: str | None = None,
        hours_per_workday: float | None = None,
        worker_optional_id: str | None = None,
        description: str | None = None,
    ) -> None:
        """Update a worker.

        Args:
            worker_id: Worker ID to update
            name: New worker name (None to keep current)
            hours_per_workday: New hours per workday (None to keep current)
            worker_optional_id: New worker_id (None to keep current)
            description: New description (None to keep current)
        """
        project = self.get_project()

        # Find the worker
        worker_index = None
        for i, worker in enumerate(project.workers):
            if worker.id == worker_id:
                worker_index = i
                break

        if worker_index is None:
            return  # Worker not found

        # Get current worker
        current_worker = project.workers[worker_index]

        # Update with new values
        updated_worker = current_worker.model_copy(
            update={
                k: v
                for k, v in {
                    "name": name,
                    "hours_per_workday": hours_per_workday,
                    "worker_id": worker_optional_id,
                    "description": description,
                }.items()
                if v is not None
            }
        )

        # Create updated workers list
        updated_workers = project.workers.copy()
        updated_workers[worker_index] = updated_worker

        # Create updated project
        updated_project = project.model_copy(update={"workers": updated_workers})
        self._set_project(updated_project)

    def remove_worker(self, worker_id: WorkerId) -> None:
        """Remove a worker from the project.

        Args:
            worker_id: Worker ID to remove
        """
        project = self.get_project()

        # Filter out the worker
        updated_workers = [w for w in project.workers if w.id != worker_id]

        # Create updated project
        updated_project = project.model_copy(update={"workers": updated_workers})
        self._set_project(updated_project)

    def get_workers(self) -> list[Worker]:
        """Get all workers in the project.

        Returns:
            List of workers
        """
        return self.get_project().workers

    # Selection

    def select_node(self, node_id: NodeId | None) -> None:
        """Select a node.

        Args:
            node_id: Node ID to select, or None to clear selection
        """
        if self._selected_node_id != node_id:
            self._selected_node_id = node_id
            self.selection_changed.emit(node_id)
