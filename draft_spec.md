## Overview
Project Fluxx is project planning software that incorporates uncertainty for tasks and samples from the schedule distribution to produce Gantt charts based on customizable levels of certainty (for management) and more fluid timeline visualizations (for me).

## Primary UI

The primary UI consists of a DAG of tasks or branches. Each task can have subtasks (that all need to be completed for the super-task to be completed). Any leaf task has a distribution. We'll start with two: shifted lognormal (specified as min, mode and 95th percentile) and triangle (specified as min, mode, and max) but I'll certainly add more over time. Tasks can depend on another task - which means that one task must finish before the dependent task can start. If a task depends on a branch outcome, the task only needs to be done in possible worlds where the particular branch outcome happens.

There are also branch nodes representing uncertain conditions/events. For example - choosing one or another base software or whether something is approved or not. There is a discrete distribution over the outcomes. Initially, this will be just a listing of the probability of each branch. Eventually, I'll also allow drawing the branch probabilities from a Dirichet distribution.

When you select a node on the DAG, a second pane contains an editor.

You can add child nodes. You can delete nodes.

## Sampling

At any point, the system can generate a simulation of X (e.g., 1000) runs of the project starting at "start time". From a simulation, we can generate multiple visualizations.

When multiple tasks can start at any time, one is randomly selected.

### Gantt Charts

A critical output is Gantt charts that I can give to managers. I can choose a percentile P (default 97%) and it creates a timeline that ensures all tasks start and end dates are at or after the P-percentile of the corresponding percentile of runs for that task.

### Probabilistic time line

Choose a percentile (default=90%) Each task is represented by a box showing the minimum start, maximum end, and percentile start and percentile end. Arrows connect tasks with a dependency relation.

## History
The history of a project will always be available enabling undo and to see how things developed. If I undo and then do something else, the history of the abandoned branch should still exist and be navigable.

## Future Improvements
* I hope it will eventually integrate with Jira, using past performance to constrain the variance of task lengths and allowing Jira plan updates as I update the plan and allowing me to update the timeline as things finish and new tasks are discovered. I hope to eventually use the history estimate extra costs from adding new tasks.
* The tasks will get people who can do them and the simulations will take those into account.
* Tasks will also include review time and potential reviewers.
* We'll add holidays and vacations to the schedule.


## Code considerations
The program will be written in Python using PyQt. All code (including GUI code) should be pytest unit tested to 100% code coverage unless I specifically agree to an exception. All code will be static analyzed using ruff and fully type-annotated using mypy. Data schemas will be enforced by pydantic. Static analysis will happen before any commit using pre-commit.


