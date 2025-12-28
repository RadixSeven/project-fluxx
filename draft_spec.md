## Overview
Project Fluxx is project planning software that incorporates uncertainty for tasks and samples from the schedule distribution to produce Gantt charts based on customizable levels of certainty (for management) and more fluid timeline visualizations (for me).

## Primary UI

The primary UI consists of a DAG of tasks or branches. Each task can have subtasks (that all need to be completed for the super-task to be completed). Any leaf task has a distribution. We'll start with two: shifted lognormal (specified as min, mode and the 95th percentile (this is a fixed percentile)) and triangle (specified as min, mode, and max) but I'll certainly add more over time. Tasks can depend on another task - which means that one task must finish before the dependent task can start. If a task depends on a branch outcome, the task only needs to be done in possible worlds where the particular branch outcome happens.

There are also branch nodes representing uncertain conditions/events. For example - choosing one or another base software or whether something is approved or not. There is a discrete distribution over the outcomes. Initially, this will be just a listing of the probability of each branch. Eventually, I'll also allow drawing the branch probabilities from a Dirichlet distribution. Branches have only an occurrence point. They can have constraints on that occurrence point like the constraints on tasks - must occur after or at the same time as <endpoint>.

Tasks can have constraints on which workers will be assigned in simulations (see *Worker restrictions* below). This consists of a whitelist of workers (which, if absent, allows any worker to be assigned) and a list of tasks (each of which must have a starts-at-or-before constraint so their assignees will be defined in the simulation) whose assignee cannot be assigned to this task. In the UI, the assignee constraint is displayed as a purple line with a 🚫 symbol on the end next to the task whose assignee is not allowed.

In the UI, a branch looks like a dot (for an endpoint) with an line to a box for each possible world. When the occurrence point occurs at or after an endpoint, then there is an arrow to the dot. When a task endpoint occurs on or after a possible world, then there is an arrow from the right edge of the possible-world box to the left edge of the task box. The possible world list and their probabilities are edited in the editor pane. There is a list of possible worlds, descriptions, and weights. As the weights are updated, the probability (weight/total weight) is displayed. The bottom entry in the displayed list is always blank. When you click on one of the Title, Description, or Weight boxes in the blank row, it becomes a new world. Each row has a trashcan 🗑️ icon that the user can click to remove that possible world. The branch edit has the usual apply or revert icons.

When you select a node on the DAG, a second pane contains an editor for that node.

The DAG is auto-layed-out and the user can pan around and zoom in and out. They can click on a node to select the node being edited in the editor pane. When you commit changes to a node, the UI updates.

The DAG panel has two modes: DAG display (which shows as a graph with collapsable nodes) and the list display. A "tab" at the top switches between the two modes. The list mode displays list entries with the node title and has a search bar to narrow the list by substrings. When you've clicked on a node in the list view, it switches back to the DAG view with the new node panned to the center. 

Nodes all have a title and description. You only see the description when you click on it (in the editor pane) or when you hover over the node.

The editor pane displays the fields of the current node with appropriate controls (text boxes, list boxes, etc.) for the individual fields. There is an apply button (which I also refer to as "commit") to apply changes and a revert button to reset to the state at the last apply or when you clicked on the node. If you attempt to navigate away from a node with unapplied changes by clicking on another node, it pops up a modal asking whether to apply the changes, revert them, or undo the navigation. The editor is also where you mark a node as done and give when it started and when it finished.

No changes can be applied to a node until it is consistent and has all its required fields. All edit controls with problem values are highlighted and there is a message at the top of the editor pane about one of the problems giving instructions for how to fix it. If the user reverts a new node, then the node is not created and the view switches back to the previously selected node.

The duration distribution is a required field for leaf task nodes.

There is a button to add an endpoint dependency from the current node. It switches the editor pane to edit-dependency mode. It allows changing the source endpoint (start, end), target endpoint (start, end), and the type (>= or =) and selecting a target node (which may be a task or a branch possibility). You cannot apply changes until everything is consistent and defined. The inconsistent edit controls are highlighted and an error message is displayed at the bottom. The target endpoint selection will be ignored (and display as "occurrence point") if a branch possible world is selected as the target. If the current node is a branch, then the start displays as "occurrence point".

When selecting a target node, no other changes can be made to the other attributes or to the DAG until the user has clicked on one or canceled. The edit pane switches to select-target-node mode. The user navigates using the main panel (which can switch back and forth to list view) until they click on an acceptable node.

In the worker section, there is a list of tasks whose assignees are excluded from the current task. Each entry has a trashcan 🗑️ to remove it from the list. There is also a + icon at the end to add a task to the list. It switches to select task node mode, which allows you to select a task node like the select-target-node mode, except that only task nodes can be selected.

There is also an optional "list of allowed workers." If it is absent, the editor pane displays, "All workers allowed. `[Click to add reduced list of allowed workers]`". If present, the list is displayed. To add a worker, one can hit the + icon and type to select from a scrollable combo list. And the list entries have the clickable trashcan 🗑️ to remove them.

You can click on a dependency in the editor pane to edit that dependency. It switches to the edit-dependency mode described above.

You can add child nodes or nodes with no parent. You can delete nodes. You can mark nodes as done, giving the real start time and the real duration (for tasks) or which possible world occurred for branches.

There is a button in the editor pane for leaf tasks to convert them task to a parent. It adds the first child and navigates to it as the focus. (Potentially generating the "navigate away" check about discarding/applying changes.) If you remove the last sub-task from a parent node, it reverts to being a leaf node and its duration distribution from before it was made a parent is restored as the source of its duration during simulations.

You add subsequent child nodes by clicking an "add sibling" in one of the other child nodes. The added node becomes the focus. (This will also be a "navigate away" event asking whether to apply changes if any others have been made.)

Above the DAG view, there is a button to create a new node that has no parent. There is also a button to see the simulations associated with the current DAG. The simulations have buttons to add more samples and buttons to generate their associated visualizations. The visualization buttons bring up a dialog to set the parameters of the visualization. After generating a visualization, it is displayed for the user and they can decide whether to save it (bringing up a dialog to select where) or discard it.

There is also a list of workers for a project. Each worker has a number of hours they complete per workday and a name. A button on the DAG opens a worker list editor.

The upper left corner of the editor pane displays the most recent history event. If you click on the dropdown button, it displays a tree view you can use to navigate to a different node in the history. Undo (CTRL-Z goes to the parent history node) and Redo (CTRL-Y goes to the child history node with the most recently created leaf node under it - either itself or one of its descendants). If the editor pane is in focus, CTRL-Y and Z operate on the in-focus editor control. Only if there is no in-focus control or there are no unapplied changes to the current node do they operate on the main UI.

## Dependencies

Task endpoints can depend on other task endpoints with two constraints: endpoint time must be equal to other endpoint, endpoint time must be greater than or equal to other endpoint. The most common idea of dependency (which I may accidentally treat as the only one in the rest of the document) is that task B start time must be greater than or equal to task A end time.

Sub-tasks have the constraint that their start time is at least their parent task's start time and that their parent task's end time is at least their end time.

The dependency graph cannot have cycles.

Task start endpoint may also depend on one or more branch possible worlds. That means the task only needs to be done in those possible worlds.

## Worker restrictions

Some tasks (e.g., reviewing an earlier task) can only be done by a different worker than the one assigned to the other task.

And some tasks can only be done by particular listed workers.

These restrictions are only needed in simulation.

## Sampling/Simulation

At any point, the system can generate a simulation of X (e.g., 1000) runs of the project starting at "start time" (e.g., 2024 Jan 12), which defaults to the start of the workday following the day the simulation was started. From a simulation, we can generate multiple visualizations.

The simulation tracks time on a calendar. (This means that weekends (and holidays when we implement them) exist even though no work is done.)

Tasks with subtasks have all their work in the subtasks, so the super-task doesn't get assigned workers etc. and its duration distribution is ignored. (Its subtasks determine its duration distribution implicitly.)

The simulation treats workers as having a number of hours they can accomplish per workday and a current task. Workers can work on one task at a time. They work on an assigned task until it is finished. When no workers are available, no task can start.

We resolve a branch as soon as all its dependencies are satisfied. All tasks dependent on the worlds that did not happen will not be done.

When multiple tasks can start at the same time (e.g., their dependencies are satisfied and there are available workers who can do the task), one is randomly selected. If a task N cannot have the same worker assigned as another task M, then worker assignment to M is a dependency that must be fulfilled before N can start.

We can add more samples to a run (since they are generated independently) after a particular sampling run has finished.

### Gantt Charts

A critical output is Gantt charts that I can give to managers. The user can choose a percentile P (default 97%) through the UI for creating the chart and it creates a timeline that ensures all tasks start and end dates are at or after the Pth percentile of the corresponding percentile of runs for that task. The key constraint is that the timeline is conservative and respects dependencies.

#### Potential algorithm for generating Gantt charts

For each task (treat versions of the task on different paths through branch nodes as different), compute the Pth percentile start time and the Pth percentile duration. Now solve the optimization problem that assigns a start time and duration to each item that meets the dependencies and is greater than or equal to the Pth percentile start time and Pth percentile duration for that item. This should be linear programming.

### Probabilistic timeline

The user selects a percentile (default=90%). Each task is represented by a box showing the minimum start, maximum end, and percentile start and percentile end. Arrows connect endpoints with a dependency relation. If the relation is equality, it's a double-ended arrow. If the relation is greater-than-or-equal-to, then the arrow goes from the (potentially) lesser to the greater (that is, in time order). Branch points create sub-diagrams for all events after the branch happens.

## History
The history of a project will always be available enabling undo and to see how things developed. If I undo and then do something else, the history of the abandoned branch should still exist and be navigable. The history event nodes contain the time they occurred (and if they are extended events, like running a simulation, how long they took).

History nodes that included simulation will not require random number generation when reloaded - this ensures that everything is reproducible even across versions that alter the order in which things are simulated.

## Future Improvements
* I hope it will eventually integrate with Jira, using past performance to constrain the variance of task lengths and allowing Jira plan updates as I update the plan and allowing me to update the timeline as things finish and new tasks are discovered. I hope to eventually use the history estimate extra costs from adding new tasks.
* Tasks and branches will be associated with Jira issues. Any metadata that does not map cleanly to the issue's fields will be placed in an attachment. (We can adjust this storage idea when we get to the Jira integration.)
* Tasks will also include review time and potential reviewers.
* We'll add holidays and vacations to the schedule.
* We'll add different affinities for a worker on a task (Worker A can do it, but it will take longer)
* Allow sampling until all possible worlds happen at least K times.
* Use pymc for sampling (which will enable oversampling rare worlds while still keeping probabilities correct)
* Allow interactive hiding of sub-tasks in Gantt charts.

## Code considerations
The program will be written in Python using PyQt. All code (including GUI code) should be pytest unit tested to 100% code coverage unless I specifically agree to an exception. All code will be static analyzed using ruff and fully type-annotated using mypy. Data schemas will be enforced by pydantic. Static analysis will happen before any commit using pre-commit.
Let's use pyomo for the optimization.


