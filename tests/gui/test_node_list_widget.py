"""Tests for NodeListWidget."""

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from fluxx.data.models import PossibleWorld, PossibleWorldId, Triangular
from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.list_view.node_list_widget import NodeListWidget


def test_node_list_widget_initialization(qtbot: QtBot) -> None:
    """Test NodeListWidget initialization."""
    controller = ProjectController()
    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    assert widget.search_field is not None
    assert widget.node_list is not None
    assert widget.all_nodes == []


def test_node_list_widget_loads_empty_project(qtbot: QtBot) -> None:
    """Test loading an empty project."""
    controller = ProjectController()
    controller.new_project("Test Project")
    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    assert widget.node_list.count() == 0


def test_node_list_widget_loads_tasks(qtbot: QtBot) -> None:
    """Test loading tasks into the list."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add tasks
    task1_id = controller.create_task(
        title="Task One",
        description="First task",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )
    task2_id = controller.create_task(
        title="Task Two",
        description="Second task",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Should show both tasks
    assert widget.node_list.count() == 2

    # Check items - now include status
    items = [widget.node_list.item(i) for i in range(widget.node_list.count())]
    texts = [item.text() for item in items if item is not None]
    assert "[Task] Task One [Not Started]" in texts
    assert "[Task] Task Two [Not Started]" in texts

    # Check data stored in items
    item_ids = [
        item.data(Qt.ItemDataRole.UserRole) for item in items if item is not None
    ]
    assert task1_id in item_ids
    assert task2_id in item_ids


def test_node_list_widget_loads_branches(qtbot: QtBot) -> None:
    """Test loading branches into the list."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add branch
    branch_id = controller.create_branch(
        title="Branch One",
        description="First branch",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw_001"),
                title="World A",
                description="First world",
                weight=1.0,
            ),
            PossibleWorld(
                id=PossibleWorldId("pw_002"),
                title="World B",
                description="Second world",
                weight=2.0,
            ),
        ],
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Should show branch + 2 possible worlds = 3 items
    assert widget.node_list.count() == 3

    # Check branch item (should be sorted alphabetically)
    # After sorting: "Branch One", "World A (from Branch One)",
    #  "World B (from Branch One)"
    branch_item = widget.node_list.item(0)
    assert branch_item is not None
    assert branch_item.text() == "[Branch] Branch One [Unresolved]"
    assert branch_item.data(Qt.ItemDataRole.UserRole) == branch_id

    # Check possible world items - no status since branch is unresolved
    pw_a_item = widget.node_list.item(1)
    assert pw_a_item is not None
    assert pw_a_item.text() == "[PossibleWorld] World A (from Branch One)"
    # Data should be tuple (branch_id, pw_id) - but PySide6 converts to list
    pw_a_data = pw_a_item.data(Qt.ItemDataRole.UserRole)
    assert isinstance(pw_a_data, (tuple, list))
    assert pw_a_data[0] == branch_id

    pw_b_item = widget.node_list.item(2)
    assert pw_b_item is not None
    assert pw_b_item.text() == "[PossibleWorld] World B (from Branch One)"
    pw_b_data = pw_b_item.data(Qt.ItemDataRole.UserRole)
    assert isinstance(pw_b_data, (tuple, list))
    assert pw_b_data[0] == branch_id


def test_node_list_widget_loads_mixed_nodes(qtbot: QtBot) -> None:
    """Test loading both tasks and branches."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add task
    controller.create_task(
        title="Task Alpha",
        description="A task",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    # Add branch
    controller.create_branch(
        title="Branch Beta",
        description="A branch",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw_001"),
                title="World A",
                description="First world",
                weight=1.0,
            ),
        ],
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Should show task + branch + possible world = 3 items
    assert widget.node_list.count() == 3

    # Check items are sorted by title (now with status)
    # Alphabetically: "Branch Beta", "Task Alpha", "World A (from Branch Beta)"
    items = [widget.node_list.item(i) for i in range(widget.node_list.count())]
    texts = [item.text() for item in items if item is not None]
    assert texts[0] == "[Branch] Branch Beta [Unresolved]"
    assert texts[1] == "[Task] Task Alpha [Not Started]"
    assert texts[2] == "[PossibleWorld] World A (from Branch Beta)"


def test_node_list_widget_search_filters_nodes(qtbot: QtBot) -> None:
    """Test search functionality filters nodes."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add tasks with different titles
    controller.create_task(
        title="Alpha Task",
        description="First",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )
    controller.create_task(
        title="Beta Task",
        description="Second",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )
    controller.create_task(
        title="Gamma Task",
        description="Third",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Initially all tasks shown
    assert widget.node_list.count() == 3

    # Search for "Alpha"
    widget.search_field.setText("Alpha")

    # Should show only Alpha
    assert widget.node_list.count() == 1
    item = widget.node_list.item(0)
    assert item is not None
    assert "Alpha Task" in item.text()


def test_node_list_widget_fuzzy_search(qtbot: QtBot) -> None:
    """Test fuzzy search matching."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add task
    controller.create_task(
        title="Implementation Task",
        description="Do something",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Fuzzy search with partial match
    widget.search_field.setText("implem")

    # Should match "Implementation"
    assert widget.node_list.count() == 1

    # Search with typo
    widget.search_field.setText("implmentaton")

    # Should still match (fuzzy matching with threshold > 60)
    assert widget.node_list.count() == 1


def test_node_list_widget_selection_updates_controller(qtbot: QtBot) -> None:
    """Test clicking item updates controller selection."""
    controller = ProjectController()
    controller.new_project("Test Project")

    task_id = controller.create_task(
        title="Test Task",
        description="A task",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Click the item
    item = widget.node_list.item(0)
    assert item is not None
    widget.node_list.itemClicked.emit(item)

    # Controller should have selected the task
    assert controller.get_selected_node_id() == task_id


def test_node_list_widget_responds_to_selection_changes(qtbot: QtBot) -> None:
    """Test widget updates when controller selection changes."""
    controller = ProjectController()
    controller.new_project("Test Project")

    task1_id = controller.create_task(
        title="Task One",
        description="First",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )
    task2_id = controller.create_task(
        title="Task Two",
        description="Second",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Select first task via controller
    controller.select_node(task1_id)

    # First item should be selected
    item_0 = widget.node_list.item(0)
    item_1 = widget.node_list.item(1)
    assert item_0 is not None
    assert item_1 is not None
    assert item_0.isSelected()
    assert not item_1.isSelected()

    # Select second task via controller
    controller.select_node(task2_id)

    # Second item should be selected
    assert not item_0.isSelected()
    assert item_1.isSelected()


def test_node_list_widget_responds_to_project_changes(qtbot: QtBot) -> None:
    """Test widget updates when project changes."""
    controller = ProjectController()
    controller.new_project("Test Project")

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Initially empty
    assert widget.node_list.count() == 0

    # Add a task
    controller.create_task(
        title="New Task",
        description="Added later",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    # Widget should update
    assert widget.node_list.count() == 1


def test_node_list_widget_color_coding(qtbot: QtBot) -> None:
    """Test tasks and branches have different colors."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add task
    controller.create_task(
        title="Task",
        description="A task",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    # Add branch
    controller.create_branch(
        title="Branch",
        description="A branch",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw_001"),
                title="World A",
                description="First world",
                weight=1.0,
            ),
        ],
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Get items (should be 3: branch, task, possible world)
    # Sorted alphabetically: "Branch", "Task", "World A (from Branch)"
    branch_item = widget.node_list.item(0)
    task_item = widget.node_list.item(1)
    pw_item = widget.node_list.item(2)

    assert branch_item is not None
    assert task_item is not None
    assert pw_item is not None

    # Check colors
    from PySide6.QtGui import QColor

    assert branch_item.foreground().color() == QColor(Qt.GlobalColor.darkYellow)
    assert task_item.foreground().color() == QColor(Qt.GlobalColor.blue)
    assert pw_item.foreground().color() == QColor(Qt.GlobalColor.darkGreen)


def test_node_list_widget_search_preserves_selection(qtbot: QtBot) -> None:
    """Test search preserves current selection."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add tasks
    task1_id = controller.create_task(
        title="Alpha Task",
        description="First",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )
    controller.create_task(
        title="Beta Task",
        description="Second",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Select first task
    controller.select_node(task1_id)
    item_0 = widget.node_list.item(0)
    assert item_0 is not None
    assert item_0.isSelected()

    # Search for Alpha
    widget.search_field.setText("Alpha")

    # Should still be selected
    assert widget.node_list.count() == 1
    search_item_0 = widget.node_list.item(0)
    assert search_item_0 is not None
    assert search_item_0.isSelected()


def test_node_list_widget_clears_search(qtbot: QtBot) -> None:
    """Test clearing search shows all nodes again."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add tasks
    controller.create_task(
        title="Alpha Task",
        description="First",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )
    controller.create_task(
        title="Beta Task",
        description="Second",
        duration_distribution=Triangular(
            min=1.0,
            mode=5.0,
            max=10.0,
        ),
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Search
    widget.search_field.setText("Alpha")
    assert widget.node_list.count() == 1

    # Clear search
    widget.search_field.clear()

    # Should show all tasks again
    assert widget.node_list.count() == 2


def test_node_list_widget_displays_completed_task_status(qtbot: QtBot) -> None:
    """Test that completed tasks show correct status and color."""
    from datetime import UTC, datetime, timedelta

    from PySide6.QtGui import QColor

    from fluxx.data.models import DoneCompletion, WorkerId

    controller = ProjectController()
    controller.new_project("Test Project")

    # Create a task
    task_id = controller.create_task(
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=5.0, max=10.0),
    )

    start_time = datetime.now(UTC)
    # Mark it as completed
    controller.update_task(
        task_id,
        completion=DoneCompletion(
            assignee=WorkerId("w1"),
            start_time=start_time,
            hours_logged=8.0,
            end_time=start_time + timedelta(hours=8),
        ),
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Check status text
    item = widget.node_list.item(0)
    assert item is not None
    assert "[Completed]" in item.text()

    # Check color (should be darkGreen for completed)
    assert item.foreground().color() == QColor(Qt.GlobalColor.darkGreen)


def test_node_list_widget_displays_in_progress_task_status(qtbot: QtBot) -> None:
    """Test that in-progress tasks show correct status and color."""
    from datetime import UTC, datetime

    from PySide6.QtGui import QColor

    from fluxx.data.models import StartedCompletion, WorkerId

    controller = ProjectController()
    controller.new_project("Test Project")

    # Create a task
    task_id = controller.create_task(
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=5.0, max=10.0),
    )

    # Mark it as in progress
    controller.update_task(
        task_id,
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=datetime.now(UTC),
            hours_logged=4.0,
        ),
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Check status text
    item = widget.node_list.item(0)
    assert item is not None
    assert "[In Progress]" in item.text()

    # Check color (should be darkYellow for in progress)
    assert item.foreground().color() == QColor(Qt.GlobalColor.darkYellow)


def test_node_list_widget_displays_resolved_branch_status(qtbot: QtBot) -> None:
    """Test that resolved branches show correct status and color."""
    from PySide6.QtGui import QColor

    controller = ProjectController()
    controller.new_project("Test Project")

    # Create a branch with possible worlds
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw_001"),
                title="Option A",
                description="First option",
                weight=1.0,
            ),
            PossibleWorld(
                id=PossibleWorldId("pw_002"),
                title="Option B",
                description="Second option",
                weight=1.0,
            ),
        ],
    )

    # Resolve the branch to Option A
    controller.update_branch(branch_id, chosen_world_id=PossibleWorldId("pw_001"))

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Find branch item
    for i in range(widget.node_list.count()):
        item = widget.node_list.item(i)
        assert item is not None
        if item.text().startswith("[Branch]"):
            # Check status text
            assert "[Resolved: Option A]" in item.text()
            # Check color (should be darkGreen for resolved)
            assert item.foreground().color() == QColor(Qt.GlobalColor.darkGreen)
            break
    else:
        raise AssertionError("Branch item not found")


def test_node_list_widget_displays_chosen_possible_world_status(qtbot: QtBot) -> None:
    """Test that chosen possible worlds show correct status and color."""
    from PySide6.QtGui import QColor

    controller = ProjectController()
    controller.new_project("Test Project")

    # Create a branch with possible worlds
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw_001"),
                title="Option A",
                description="First option",
                weight=1.0,
            ),
            PossibleWorld(
                id=PossibleWorldId("pw_002"),
                title="Option B",
                description="Second option",
                weight=1.0,
            ),
        ],
    )

    # Resolve the branch to Option A
    controller.update_branch(branch_id, chosen_world_id=PossibleWorldId("pw_001"))

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Find the possible world items
    chosen_found = False
    not_chosen_found = False

    for i in range(widget.node_list.count()):
        item = widget.node_list.item(i)
        assert item is not None
        if "[PossibleWorld]" in item.text():
            if "Option A" in item.text():
                assert "[Chosen]" in item.text()
                assert item.foreground().color() == QColor(Qt.GlobalColor.darkGreen)
                chosen_found = True
            elif "Option B" in item.text():
                assert "[Not Chosen]" in item.text()
                assert item.foreground().color() == QColor(Qt.GlobalColor.gray)
                not_chosen_found = True

    assert chosen_found, "Chosen possible world not found"
    assert not_chosen_found, "Not chosen possible world not found"


def test_node_list_widget_possible_world_click(qtbot: QtBot) -> None:
    """Test clicking on a possible world selects the parent branch."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Create a branch with a possible world
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw_001"),
                title="Option A",
                description="First option",
                weight=1.0,
            ),
        ],
    )

    widget = NodeListWidget(controller)
    qtbot.addWidget(widget)

    # Find and click the possible world item
    for i in range(widget.node_list.count()):
        item = widget.node_list.item(i)
        assert item is not None
        if "[PossibleWorld]" in item.text():
            # Click the item
            widget._on_item_clicked(item)
            break

    # Branch should now be selected
    assert controller.get_selected_node_id() == branch_id
