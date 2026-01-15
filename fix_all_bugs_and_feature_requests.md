1. Make a plan to fix the first item on the list `bugs_and_feature_requests.md` put the plan in an appropriately named `TODO_*.md` file. (There are other TODO_*.md files to give you an idea of what you might name it.) Remember the name.
2. Commit the draft.
3. Start a sub-agent to review the file and incorporate the feedback.
4. Commit the improved plan file.
5. Execute the plan in the plan file.
6. Run `source venv/bin/activate && pre-commit` and `source venv/bin/activate && make all_checks`, fixing problems they surface until they both pass.
7. Commit the changes made by following the plan.
8. Thoroughly and systematically review the plan and the original item on the list from `bugs_and_feature_requests.md` to see if any aspects were missed (even review items marked as completed - they may have been marked in error).
9. If any aspects were missed:
   a. Add steps to the plan to fix the missing items.
   b. Mark completed steps as completed.
   c. Commit the updated plan.
   d. Go back to step 3.
10. If the user created STOP_FIXES in the current directory, stop.
11. Remove the plan file that corresponds to the first item on the list `bugs_and_feature_requests.md`.
12. Move the first item on the list `bugs_and_feature_requests.md` and move it to `completed_bugs_and_feature_requests.md` (you may have to create `completed_bugs_and_feature_requests.md`.) That item should no longer appear in `bugs_and_feature_requests.md` but should appear in `completed_bugs_and_feature_requests.md`.
13. Commit the changes to the plan (its deletion), the changes to `bugs_and_feature_requests.md` and the changes to `completed_bugs_and_feature_requests.md` (which may involve its creation).
14. If there are no more items in `bugs_and_feature_requests.md`, stop.
14. Otherwise, go back to step 1 to take care of the first item.
