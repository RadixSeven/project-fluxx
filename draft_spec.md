## Overview
Project Fluxx is project planning software that incorporates uncertainty for tasks and samples from the schedule distribution to produce Gantt charts based on customizable levels of certainty (for management) and more fluid timeline visualizations (for me).

## Primary UI

The primary UI consists of a DAG of tasks or branches. Each task can have subtasks (that all need to be completed for the super-task to be completed). Any leaf task has a distribution. We'll start with two: shifted lognormal (specified as min, mode and 95th percentile) and triangle (specified as min, mode, and max) but I'll certainly add more over time. Tasks can depend on another task - which means that one task must finish before the dependent task can start. If a task depends on a branch outcome, the task only needs to be done in possible worlds where the particular branch outcome happens.

There are also branch nodes representing uncertain conditions/events. For example - choosing one or another base software or whether something is approved or not. There is a discrete distribution over the outcomes. Initially, this will be just a listing of the probability of each branch. Eventually, I'll also allow drawing the branch probabilities from a Dirichlet distribution. Branches have only an occurrence point. They can have constraints on that occurrence point like the constraints on tasks - must occur after or at the same time as <endpoint>.

When you select a node on the DAG, a second pane contains an editor for that node.

You can add child nodes or nodes with no parent. You can delete nodes. You can mark nodes as done, giving the real start time and the real duration (for tasks) or which possible world occurred for branches.

## Dependencies

Task endpoints can depend on other task endpoints with two constraints: endpoint time must be equal to other endpoint, endpoint time must be greater than or equal to other endpoint. The most common idea of dependency (which I may accidentally treat as the only one in the rest of the document) is that task B end time must greater than or equal to task B start time.

Task start endpoint may also depend on one or more branch possible worlds. That means the task only needs to be done in those possible worlds.

## Sampling

At any point, the system can generate a simulation of X (e.g., 1000) runs of the project starting at "start time" (e.g., 2024 Jan 12), which defaults to the next day. From a simulation, we can generate multiple visualizations.

When multiple tasks can start at any time, one is randomly selected.

We can add more samples to a run (since they are generated independently) after a particular sampling run has finished.

### Gantt Charts

A critical output is Gantt charts that I can give to managers. I can choose a percentile P (default 97%) and it creates a timeline that ensures all tasks start and end dates are at or after the P-percentile of the corresponding percentile of runs for that task. The key constraint is that the timeline is conservative and respects dependencies.

#### Potential algorithm for generating Gantt charts

For each task (treat versions of the task on different paths through branch nodes as different), compute the P-%ile start time and the P-%ile duration. Now solve the optimization problem that assigns a start time and duration to each item that meets the dependencies and is greater than or equal to the 90%-ile start time and 90%-ile duration for that item.

### Probabilistic timeline

Choose a percentile (default=90%) Each task is represented by a box showing the minimum start, maximum end, and percentile start and percentile end. Arrows connect endpoints with a dependency relation. If the relation is equality, it's a double-ended arrow. If the relation is greater-than-or-equal-to, then the arrow goes from the (potentially) lesser to the greater (that is, in time order). Branch points create sub-diagrams for all events after the branch happens.

## History
The history of a project will always be available enabling undo and to see how things developed. If I undo and then do something else, the history of the abandoned branch should still exist and be navigable.

History nodes that included simulation will not require random number generation when reloaded - this ensures that everything is reproducible even across versions that alter the order in which things are simulated.

## Future Improvements
* I hope it will eventually integrate with Jira, using past performance to constrain the variance of task lengths and allowing Jira plan updates as I update the plan and allowing me to update the timeline as things finish and new tasks are discovered. I hope to eventually use the history estimate extra costs from adding new tasks.
* Tasks and branches will be associated with Jira issues. Any metadata that does not map cleanly to the issue's fields will be placed in an attachment. (We can adjust this storage idea when we get to the Jira integration.)
* The tasks will get people who can do them and the simulations will take those into account.
* Tasks will also include review time and potential reviewers.
* We'll add holidays and vacations to the schedule.


## Code considerations
The program will be written in Python using PyQt. All code (including GUI code) should be pytest unit tested to 100% code coverage unless I specifically agree to an exception. All code will be static analyzed using ruff and fully type-annotated using mypy. Data schemas will be enforced by pydantic. Static analysis will happen before any commit using pre-commit.
Let's use pyomo for the optimization.


