# APJ STS ASQ Follow-up Triage

Goal: Triage responses to ASQs that were put 'On Hold' or 'Under Review'. Follow the steps listed below in plan mode and recommend actions that can be manually reviewed before execution.

## Steps

### 1. Retrieve On Hold / Under Review ASQs
Start by getting a list of all ASQs in the **Technical_Onboarding_Services_APJ** queue in SFDC with status **'On Hold'** or **'Under Review'**.

### 2. Pre-Chatter Checks (run before reading chatter)

Before reading chatter history, perform the following checks on each ASQ record:

**a. Attachments check**
Query `ContentDocumentLink` for each ASQ. If a workspace setup checklist is already attached, do not ask for it again — proceed directly to engineer assignment steps.

**b. Use case stage (live check)**
Re-query the linked use case stage directly from SFDC — do not rely on stage information from initial triage, as it may be stale. If the stage has been advanced since initial triage, acknowledge the progress and drop any stage-related blocker from the reminder.

**c. Requestor fallback**
If `Requestor__r` is null on the ASQ record, extract the requestor from the first @mention in the earliest triage chatter post and use that user for structured mentions in all chatter updates.

**d. Scope check for non-Platform Administration ASQs**
For ASQs where `Support_Type__c` is not `Platform Administration` (e.g. ML & GenAI, Data Engineering), verify the request is within STS scope before defaulting to a workspace checklist ask. The workspace checklist flow only applies to workspace setup requests.

### 3. Read All Chatter History
For **every** ASQ retrieved, read **all** chatter posts and comments in full — do not limit to recent activity. This is required to understand the full history, identify the last triage chatter sent, and determine whether a response has been received.

For each ASQ, identify:
- The **last chatter post sent by the triage team** and its date
- Whether there has been a **response from the requestor or any other party** after that post
- The **full content** of any response received

### 4. Determine Action Based on Chatter State
Apply the following rules strictly:

- **No response received AND last triage chatter was sent within the last 3 days:** Do **NOT** formulate a chatter update. Mark as "Waiting — no action needed".
- **No response received AND last triage chatter was sent more than 3 days ago:** Send a reminder to the requestor via SFDC chatter/activity using a **structured Salesforce Mention**.
- **Response received from requestor or other party:** Formulate a chatter update based on the content of the response (see Step 6).
- **No chatter history at all:** Send initial follow-up to requestor.

**Duplicate post guard:** Before posting any chatter, verify the most recent post does not already contain the same core message sent within the last 2 hours. If a duplicate is detected, skip — do not post again.

**End date expiry:** If the ASQ's end date has passed and no response has been received, explicitly ask whether the engagement is still required or should be closed — regardless of the 3-day window. Do not continue sending checklist or schedule reminders past the end date without acknowledging it.

**Start date proximity:** If the ASQ's start date is today or tomorrow, flag it for immediate attention regardless of the 3-day window and surface it in the output table even if no chatter action is due.

**Read description before templating:** Before sending a checklist ask, read the full request description. If it indicates an existing workspace (e.g. "e2 trial account created", "workspace already provisioned"), do not ask generically for workspace type and checklist — instead ask for the workspace URL and confirm remaining setup steps.

**Final notice threshold:** After 3 or more unanswered triage posts with zero engagement (no chatter responses, no record updates, no attachments added), send a final notice with an explicit close-by date rather than another standard reminder.

### 5. Escalate Long-Standing Under Review ASQs
For ASQs that have been 'Under Review' for more than 1 week:
- Change status to **'On Hold'**
- Update the SFDC chatter/activity informing the requestor using a **structured Salesforce Mention**

### 6. Recommend Next Steps for Updated ASQs
For ASQs where a response to triage chatter has been received, recommend the next steps:
- **Ready for triage:** Follow the steps and practices as per the ASQ triage process (see `new-asq-triage.md`). When assigning to an engineer, set status to **'In Progress'** — there is no 'Assigned' status. Also update the **OwnerId** of the ASQ record to the assigned engineer's Salesforce User ID.
- **Workspace setup ASQ — checklist still not attached:** Re-send a reminder to the requestor using a **structured Salesforce Mention** with a link to [go/wssetup-cheatsheet](https://sites.google.com/databricks.com/sts-workspace-setup) and keep status as **'Under Review'**.
- **No longer required:** Modify the status to **"Rejected"** and recommend action based on latest comment on SFDC chatter/activity

### 7. Output Format
Show the final results in a **tabular format** with recommendations on all ASQs analyzed.

### 8. Chatter Updates
Formulate an update for the SFDC activity/chatter feed to inform the requestor and assignee. **Always include the original requestor in every SFDC chatter update using a structured Salesforce Mention, even when assigning to a different engineer.**

**MANDATORY:** Every SFDC chatter/activity update — without exception — must end with the following statement:

> *'Triaged with the help of Databricks FE AI agents. Please respond via the ASQ or apj-sts slack channel if we got this wrong. We are still evaluating and refining our AI tools and execution.'*

This applies to all chatter posts including: reminders, status change notifications, assignment notifications, requestor visibility updates, closure messages, and any other chatter activity on ASQs.

### 9. Structured Mentions
Ensure a **structured Salesforce Mention** is used to respond to requestors or to include engineers assigned the ASQ or marked for #Shadow on the ASQ.
