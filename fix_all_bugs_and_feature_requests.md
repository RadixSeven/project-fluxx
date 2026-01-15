1. Make a plan to fix or enact the first item on the list `bugs_and_feature_requests.md`. `bugs_and_feature_requests.md` is a Markdown list and "the first item" refers to the first item and its children. Put the plan in an appropriately named `TODO_*.md` file. (There are other TODO_*.md files to give you an idea of what you might name it.) Add the plan file name to the end of the list item the plan addresses in the format `PLAN_FILE: TODO_file_name_here.md`. (If the list item we're addressing has children, add the `PLAN_FILE` annotation to the end of the parent). Adding the plan file name will enable you to remember it later. (To simplify the language, we'll call resolving the issue "fixing" it in future steps and the changes needed to resolve it will be called "the fix.")
2. Commit the draft.
3. Start a sub-agent to review the plan file (which may be a partly completed plan on which you are iterating)
   and incorporate the sub-agent's feedback.
4. Commit the improved plan file.
5. Execute the plan in the plan file.
6. Run `source venv/bin/activate && pre-commit` and `source venv/bin/activate && make all_checks`, fixing problems they surface until they both pass.
7. Verify that the fix works (When iterating a request where impossible items were identified in step 10, do not require that the fix has addressed parts of the request that were marked as impossible - since that is probably impossible.)
8. Commit the changes made by following the plan.
9. Thoroughly and systematically review the plan and the original item on the list from `bugs_and_feature_requests.md` to see if any aspects were missed (even review items marked as completed - they may have been marked in error).
10. If any aspects were missed:
    a. If any items were missed because they are impossible to complete or not impossible in general but blocked
       by current circumstances that are likely to last more than 1 hour, (I'll call both of these "impossible" below
       to simplify the language.)
        i. Consider carefully whether the item is really impossible or whether you can change things about the
           architecture that make it possible. For example, I have often seen developers say
           that a piece of defensive code is impossible to reach in tests. However, when they refactored the function
           into smaller pieces, they were able to mock functions or inject values to make it reachable. Or they were
           assuming that code had to be covered by tests that replicated normal inputs to a calling function and by
           passing abnormal inputs (for example, MagicMock objects that returned unusual or inconsistent results) they
           were able to execute the defensive code.
        ii. If the item is not really impossible or there are things you haven't tried that might work, don't treat
            it as an impossible item. Instead, treat the steps to remedy it or that you haven't tried as ways
            to fix the missing items. These missing item fixes will be recorded in step (10.b) below.
        iii. For each truly impossible item, add a list item (which may have sub-points under it) to `completed_bugs_and_feature_requests.md`. The new list item and its sub-points must
            1. Be a sub-list of a placeholder list item `- PLACEHOLDER: Impossible items while executing <plan filename>`
               (if the placeholder already exists, add the new item as an additional sub-item.)
            2. Give the filename of the plan with the impossible item and which item was impossible. The repetition
               of the filename is needed because the placeholder will be replaced by the original request once
               the request is completed.
            3. Give the latest commit containing a version of the plan with the impossible item
            4. Summarize what was planned, why it is impossible, the solutions that were tried, and what will be done
               instead to come as close to resolving the original item from `bugs_and_feature_requests.md`
        iv. Revise the plan to substitute what will be done instead (from 10.a.iii.4 above) for each impossible step.
            Do not assume readers know of the specification of the impossible step, since you are substituting
            a possible step for the impossible step and the impossible step will thus no longer be in the plan
            document. In the substitute step, explain what is being done and the motivation and why it was impossible
            to fulfill the original plan. Explaining why the earlier plan(s) didn't work will help you remember what
            has already been tried in case the user has questions later or in case you discover problems while carrying
            out the new plan and need to revise the plan further.
        v. Commit the changes to the plan and `completed_bugs_and_feature_requests.md`
    b. Add steps to the plan to fix the non-impossible missing items.
    c. Mark completed steps as completed. This is not wasted effort because we will return to step 3, which will
       review the plan including the updated steps, which will be followed by step 5 to execute the plan. Both the
       reviewer and the executor need an up-to-date view of the progress in the plan.
    d. Commit the updated plan.
    e. If the user created STOP_FIXES in the current directory, stop.
    f. Go back to step 3. (The new review is intentional.)
11. If the user created STOP_FIXES in the current directory, stop.
12. Since we passed step 10, we know that the plan was successfully executed (step 9 confirmed that no items were missed
    and step 10 would have iterated if the review indicated missing plan elements) and that the fix works except for
    impossible parts of the request (step 7). Remove the plan file that corresponds to the first item on the list `bugs_and_feature_requests.md` (step 1 defines "the first item").
13. Check for files matching the pattern `bugs_and_feature_requests_*.md` where `*` is a number
    (e.g., `bugs_and_feature_requests_01.md`, `bugs_and_feature_requests_2.md`). These files allow the user to add
    new items while the executor is working. The user follows a safe creation pattern: create the file under a
    temporary name (not matching the pattern), write the contents, then rename it to match the pattern. Once renamed,
    the user must not modify the file. Users will never edit `bugs_and_feature_requests.md` while the executor is
    running. If any files matching the pattern `bugs_and_feature_requests_*.md` where `*` is a number exist:
    a. Sort them by their numeric suffix (numerically, so `_2` comes before `_10` and `_011` comes after `_10`).
    b. Append the contents of each file, in sorted order, to the end of `bugs_and_feature_requests.md`.
    c. Delete the numbered files after their contents have been appended.
14. Move the first item on the list `bugs_and_feature_requests.md` to `completed_bugs_and_feature_requests.md` (you may have to create `completed_bugs_and_feature_requests.md`.) That item should no longer appear in `bugs_and_feature_requests.md` but should appear in `completed_bugs_and_feature_requests.md`. If there were impossible items related to this completed item, there will be a placeholder of the form `- PLACEHOLDER: Impossible items while executing <plan filename>`, then the moved item will replace this placeholder rather than being a new item. If there is no placeholder then the moved item will be a new item. (Step 1 defines "the first item")
15. Commit the changes to the plan (its deletion), the changes to `bugs_and_feature_requests.md`,
    the changes to `completed_bugs_and_feature_requests.md` (which may involve its creation),
    and the deletion of any numbered files merged in step 13.
16. If there are no more items in `bugs_and_feature_requests.md`:
    a. Check for numbered files as in step 13. If any exist, merge them per step 13, commit the changes
       to `bugs_and_feature_requests.md` and the deletion of the numbered files, then continue to step 17.
    b. Otherwise (there are no numbered files and no items in `bugs_and_feature_requests.md`), stop.
17. Go back to step 1 to take care of the first item.
