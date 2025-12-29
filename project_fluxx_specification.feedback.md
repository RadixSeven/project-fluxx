Thank you for writing project_fluxx_specificatoin.md here are some points I noticed when reviewing it:
* Worker ID is optional - only present when there are same-named workers
* Duration distribution: should be written as two sub-classes. An amorphous list of "parameters" loses a lot of the utility of automatic type checking.
```
class ShiftedLognormal(DurationDistribution):
    min: real
    mode: real (must be > min)
    95_percentile: real (must be > min)

class Triangular(DurationDistribution):
    min: real
    mode: real (must be > min)
    max: real (must be > mode)
```
* We should be sure that part of the validation for adding a dependency is that it does not create a cycle.
* Sample status can be inferred from "failed_tasks" is empty = success. Don't include the unnecessary value. As much as feasible, illegal states should be unrepresentable.
* The is_done is also not necessary on tasks. If the actual duration is present, then the task is done (otherwise you don't know how long it took). 
* There should be a constraint that the actual duration cannot be set without the actual start being set. (Note that a task could have an actual start but not be done. This indicates a task in progress. This will need to be taken into account in the simulation. It will need to use rejection sampling to select from the distribution and reject all durations that are less than the elapsed time (in assignee-hour workdays) between the start time and the simulation.)
* We also need an actual assignee. This must be set when the task actual start time is set. It will be needed to determine the elapsed number of work hours since the start time.
* For the branch, the chosen_world_id is present iff the branch "is done" so we can eliminate the is_done field.
* These changes require a minor rework of the "Completion tracking" section.
* We can record the percentiles calculated for a simulation as a cache, but that can be a later optimization. I don't know if it will be needed. Let's calculate it on the fly when creating visualizations for now.
* TODO: check after finishing reading. The schemas ought to take into account the durable nature of the objects when linking to them. I think you ought to include a DAG object and a DAG event object. The DAG object has a map of the id->object relation at the point in time represented by the DAG (e.g., at time_1, task_1234 maps to persistent_task_object_4567). The DAG event objects are the persistent events that apply modifications to the DAG. There are also other event classes for creating persistent objects.
* Clicking on a possible world box when not selecting a dependency opens the branch in the editor pane
* DAG List display mode should allow fuzzy matching (RapidFuzz library) for a better user experience.
* The history event display should be above the DAG panel not the editor panel. (Conceptually, you're selecting a historical DAG.)
* Add sibling is not in parent tasks, it is in child tasks. (It would be logical to add an "Add child" button in the parent that has a similar effect, though.)
* "blank" weight in the possible worlds section is treated as 0 until the user enters something else.
* History nodes with simulations DO NOT store the random seed, they store a representation of the simulation that does not require random number generation to "hydrate" the simulation. This ensures repeatability even if the simulation implementation changes.
* It is probably easiest to include the dependencies linking parent and child explicitly rather than to have special cases to implement them.
* For simulation mechanics, in addition to holidays and vacations being added in the future, sick days will also be added.
* I think you forgot that if task N excludes assignee of task M, there must be a dependency that task N start >= task M start in addition to the assignment happening first.
* The last condition on sampling run failure is: "Unfulfilled dependencies exist for ALL tasks in current possible world." (Your copy leaves out the all.) This is a failure since the simulation cannot progress since no new task can be started.
* For Gantt chart, rather than minimizing total project duration (which requires computing the critical path), it would be better to minimize the sum of start times plus the sum of durations (possibly with some scaling factor). It should give similar results.
* For the Probabilistic timeline, it would probably be better to show the (1-P)th percentile start time to match showing the minimum start time.


