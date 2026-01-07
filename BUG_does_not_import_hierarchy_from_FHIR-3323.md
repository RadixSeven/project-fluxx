When I import FHIR-3323, it now imports all the children, but it does not
connect the dependencies from parent to child. Additionally, it does not
properly reproduce the hierarchy. If P_issue is a parent issue and C_issue is a
child issue and P_task is the task connected to P_issue and C_task is the task
connected to C_issue, P_task should be the parent of C_task.
