# Bug Report: Jira Import Fails Due to Missing accountId Fields

## Summary

Importing a Jira epic fails with Pydantic validation errors when the Jira server returns user objects without `accountId` fields.

## Environment

- **Jira Server URL:** https://jira.ncbi.nlm.nih.gov
- **JQL Query:** `key=FHIR-3323`
- **Project Name:** FY26 Incremental Sync

## Error Message

```
Import failed: 6 validation errors for JiraIssueResponse
```

### Validation Errors

1. **fields.assignee.accountId**
   ```
   Field required [type=missing, input_value={'self': 'https://jira.nc...ne': 'America/New_York'}, input_type=dict]
   For further information visit https://errors.pydantic.dev/2.12/v/missing
   ```

2. **fields.worklog.worklogs.0.author.accountId**
   ```
   Field required [type=missing, input_value={'self': 'https://jira.nc...ne': 'America/New_York'}, input_type=dict]
   For further information visit https://errors.pydantic.dev/2.12/v/missing
   ```

3. **fields.worklog.worklogs.1.author.accountId**
   ```
   Field required [type=missing, input_value={'self': 'https://jira.nc...ne': 'America/New_York'}, input_type=dict]
   For further information visit https://errors.pydantic.dev/2.12/v/missing
   ```

4. **fields.worklog.worklogs.2.author.accountId**
   ```
   Field required [type=missing, input_value={'self': 'https://jira.nc...ne': 'America/New_York'}, input_type=dict]
   For further information visit https://errors.pydantic.dev/2.12/v/missing
   ```

5. **fields.worklog.worklogs.3.author.accountId**
   ```
   Field required [type=missing, input_value={'self': 'https://jira.nc...ne': 'America/New_York'}, input_type=dict]
   For further information visit https://errors.pydantic.dev/2.12/v/missing
   ```

6. **fields.worklog.worklogs.4.author.accountId**
   ```
   Field required [type=missing, input_value={'self': 'https://jira.nc...ne': 'America/New_York'}, input_type=dict]
   For further information visit https://errors.pydantic.dev/2.12/v/missing
   ```

## Root Cause Analysis

The Jira API response from this server does not include `accountId` fields in user objects (assignee and worklog authors). This is likely because:

- **Jira Server/Data Center** instances use `name` and `key` fields for user identification instead of `accountId`
- **Jira Cloud** uses `accountId` as the primary user identifier

The current Pydantic model in `fluxx/jira/api_types.py` likely marks `accountId` as a required field, which causes validation to fail for Jira Server instances.

## Suggested Fix

Make `accountId` optional in the user-related Pydantic models and use fallback fields (`name` or `key`) when `accountId` is not present. This would allow compatibility with both Jira Cloud and Jira Server/Data Center deployments.

## Steps to Reproduce

1. Open Project Fluxx with an empty/new project file
2. Go to Jira > Import from Jira...
3. Enter Server URL: `https://jira.ncbi.nlm.nih.gov`
4. Enter JQL Query: `key=FHIR-3323`
5. Enter Project Name: `FY26 Incremental Sync`
6. Click Import

## Expected Behavior

The epic and its child issues should be imported successfully.

## Actual Behavior

Import fails with 6 validation errors for missing `accountId` fields.

## Screenshot

See `failed-import-from-fhir-3323.png`
