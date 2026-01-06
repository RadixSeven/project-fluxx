# TODO: Fix Jira Sync Problems (January 6, 2026)

## Status: Planning

## Main Tasks

### Task 1: Fix Import Bug - Import Child Issues
- [ ] Investigate why `jql='key=FHIR-3323'` doesn't import child issues
- [ ] Modify import to fetch and include all children of imported issues
- [ ] Handle "child of" links in addition to direct parent/child relationships
- [ ] Add tests for child import functionality

### Task 2: Implement Sync Functionality
- [ ] Review Phase 5.2 from TODO_mvp_jira_sync.md
- [ ] Implement sync logic for updating existing tasks from Jira
- [ ] Handle new children, deleted children, and changed parent relationships
- [ ] Update links during sync
- [ ] Add GUI integration (Phase 6)
- [ ] Add tests for sync functionality

### Task 3: Audit TODO_mvp_jira_sync.md for Missing Implementations
- [ ] Review all phases for missing logic
- [ ] Verify GUI is connected to all implemented logic
- [ ] Document any gaps found
- [ ] Implement missing pieces

## Progress Log

(Will be updated as work progresses)

---

## Clarifying Questions and Responses

### Questions Set 1 (Initial)

Based on my review of the specification and TODO_mvp_jira_sync.md, I have the following questions:

#### Q1.1: Child Issue Fetching Strategy
The specification (Section 11.4.2) shows this JQL for fetching children:
```
"Epic Link" = {epic_key} OR parent = {epic_key}
```

Should the import automatically expand any user-provided JQL to include children? For example:
- User provides: `key=FHIR-3323`
- System expands to: `key=FHIR-3323 OR "Epic Link" = FHIR-3323 OR parent = FHIR-3323`

Or should we do a second query for children after fetching the initial issues?

**Also**: The "parent of"/"child of" link types establish hierarchy too (per spec). Should we also recursively fetch children found via these links?

#### Q1.2: Recursive Child Fetching
If FHIR-3323 has a child FHIR-3324, and FHIR-3324 has its own children, should we fetch all descendants recursively? The spec mentions subtasks and "parent of"/"child of" links but doesn't explicitly state depth.

#### Q1.3: Sync Functionality - Scope
For sync/update (Phase 5.2), the spec says:
- Match by `(server_url, issue_key)` tuple
- Update existing tasks, create new ones

Should sync also:
a) Delete tasks that were removed from Jira? Or just mark them somehow?
b) Handle parent-child relationship changes (e.g., issue moved to different epic)?
c) Use the same child-fetching logic as import (recursively get all children)?

#### Q1.4: "Issues that were children at last sync"
You mentioned "issues that were children at the last sync - even if they are no longer children". This suggests we need to track which issues were synced. Should we:
a) Store the list of synced issue keys in `JiraSyncMetadata`?
b) Query all issues that have `jira_reference` matching the server and re-check their Jira state?

#### Q1.5: GUI for Sync
The spec mentions "Update from Jira..." menu item. Should this:
a) Sync all Jira-linked tasks in the current project?
b) Ask the user which epic/issues to sync?
c) Something else?

(Awaiting responses)

---

## Initial User Request

> I have three more tasks.
>
> 1. Fix a bug: when I start an import with jql='key=FHIR-3323', it imports the epic ticket FHIR-3323, but does not import any the child issues in the epic.
>    When doing an import, Project Fluxx should import all children as well and when doing a sync/update on a task corresponding to a Jira issue with children (either through Jira directly or through the "child of" link), it should sync any children (including new children and deleted children and issues that were children at the last sync - even if they are no longer children).
>    All synchronized issues will need their links updated.
> 2. Please implement sync (earlier you said you skipped phase 7.2 of TODO_mvp_jira_sync.md because sync was not implemented but the logic should have been implemented in phase 5.2 and the GUI integration should have been implemented in phase 6).
> 3. Check for other items in TODO_mvp_jira_sync.md whose logic should have been implemented and make sure it was implemented and that the GUI was attached to the logic.
>
> While carring this out, be mindful of keeping methods short, testable, and maintainable, testing interactions between methods, maintaining type safety and style, and ensuring correctness. Keep track of your progress in TODO_fix_jira_sync_problems_from_Jan_06.md (created below). As you finish a cohesive unit of work, make a commit to allow rolling back if there are problems. At a minimum commit after finish each of the three main tasks above, but at your discretion, you may commit when it seems reasonable and `make all_checks` and `pre-commit` pass. Once you have asked enough clarifying questions to start, try to get as many of the tasks done as you can before stopping.
>
> Beore you start the main tasks:
> a. Make a TODO list file (TODO_fix_jira_sync_problems_from_Jan_06.md) including this entire message as "Initial user request that caused the creation of this file" at the end.
> b. Check project_fluxx_specification.md and TODO_mvp_jira_sync.md ask any clarifying questions required to carry out the work. Update TODO_fix_jira_sync_problems_from_Jan_06.md with a record of the questions and responses at the end for future reference, with each set of questions and responses clearly delimited by subheadings. Check the questions and responses or instructions for contradictions and make sure to resolve them with the user. You may edit previous responses with editor notes for example "[ed. see below in response 7.3 for a clarification]". Commit each version of TODO_fix_jira_sync_problems_from_Jan_06.md to preserve a record if needed for reference.
