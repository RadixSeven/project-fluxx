"""Tests for NodeListWidget."""

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    NodeId,
    PossibleWorld,
    PossibleWorldId,
    Triangular,
)
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

    # Check items
    items = [widget.node_list.item(i) for i in range(widget.node_list.count())]
    texts = [item.text() for item in items if item is not None]
    assert "[Task] Task One" in texts
    assert "[Task] Task Two" in texts

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

    # Should show branch
    assert widget.node_list.count() == 1

    # Check item
    item = widget.node_list.item(0)
    assert item is not None
    assert item.text() == "[Branch] Branch One"
    assert item.data(Qt.ItemDataRole.UserRole) == branch_id


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

    # Should show both
    assert widget.node_list.count() == 2

    # Check items are sorted by title
    items = [widget.node_list.item(i) for i in range(widget.node_list.count())]
    texts = [item.text() for item in items if item is not None]
    assert texts[0] == "[Branch] Branch Beta"
    assert texts[1] == "[Task] Task Alpha"


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
    assert controller.get_selected_node_id() == NodeId(str(task_id))


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
    controller.select_node(NodeId(str(task1_id)))

    # First item should be selected
    item_0 = widget.node_list.item(0)
    item_1 = widget.node_list.item(1)
    assert item_0 is not None
    assert item_1 is not None
    assert item_0.isSelected()
    assert not item_1.isSelected()

    # Select second task via controller
    controller.select_node(NodeId(str(task2_id)))

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

    # Get items
    branch_item = widget.node_list.item(0)  # Sorted alphabetically
    task_item = widget.node_list.item(1)

    assert branch_item is not None
    assert task_item is not None

    # Check colors
    from PySide6.QtGui import QColor

    assert branch_item.foreground().color() == QColor(Qt.GlobalColor.darkGreen)
    assert task_item.foreground().color() == QColor(Qt.GlobalColor.blue)


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
    controller.select_node(NodeId(str(task1_id)))
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
