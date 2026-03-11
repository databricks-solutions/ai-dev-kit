# APJ STS ASQ Follow-up Triage

Goal: Triage responses to ASQs that were put 'On Hold' or 'Under Review'. Follow the steps listed below in plan mode and recommend actions that can be manually reviewed before execution.

## Steps

### 1. Retrieve On Hold / Under Review ASQs
Start by getting a list of all ASQs in the **Technical_Onboarding_Services_APJ** queue in SFDC with status **'On Hold'** or **'Under Review'**.

### 2. Read All Chatter History
For **every** ASQ retrieved, read **all** chatter posts and comments in full — do not limit to recent activity. This is required to understand the full history, identify the last triage chatter sent, and determine whether a response has been received.

For each ASQ, identify:
- The **last chatter post sent by the triage team** and its date
- Whether there has been a **response from the requestor or any other party** after that post
- The **full content** of any response received

### 3. Determine Action Based on Chatter State
Apply the following rules strictly:

- **No response received AND last triage chatter was sent within the last 3 days:** Do **NOT** formulate a chatter update. Mark as "Waiting — no action needed".
- **No response received AND last triage chatter was sent more than 3 days ago:** Send a reminder to the requestor via SFDC chatter/activity using a **structured Salesforce Mention**.
- **Response received from requestor or other party:** Formulate a chatter update based on the content of the response (see Step 5).
- **No chatter history at all:** Send initial follow-up to requestor.

### 4. Escalate Long-Standing Under Review ASQs
For ASQs that have been 'Under Review' for more than 1 week:
- Change status to **'On Hold'**
- Update the SFDC chatter/activity informing the requestor using a **structured Salesforce Mention**

### 5. Recommend Next Steps for Updated ASQs
For ASQs where a response to triage chatter has been received, recommend the next steps:
- **Ready for triage:** Follow the steps and practices as per the ASQ triage process (see `new-asq-triage.md`). When assigning to an engineer, set status to **'In Progress'** — there is no 'Assigned' status. Also update the **OwnerId** of the ASQ record to the assigned engineer's Salesforce User ID.
- **Workspace setup ASQ — checklist still not attached:** Re-send a reminder to the requestor using a **structured Salesforce Mention** with a link to [go/wssetup-cheatsheet](https://sites.google.com/databricks.com/sts-workspace-setup) and keep status as **'Under Review'**.
- **No longer required:** Modify the status to **"Rejected"** and recommend action based on latest comment on SFDC chatter/activity

### 6. Output Format
Show the final results in a **tabular format** with recommendations on all ASQs analyzed.

### 7. Chatter Updates
Formulate an update for the SFDC activity/chatter feed to inform the requestor and assignee. **Always include the original requestor in every SFDC chatter update using a structured Salesforce Mention, even when assigning to a different engineer.**

**MANDATORY:** Every SFDC chatter/activity update — without exception — must end with the following statement:

> *'Triaged with the help of Databricks FE AI agents. Please respond via the ASQ or apj-sts slack channel if we got this wrong. We are still evaluating and refining our AI tools and execution.'*

This applies to all chatter posts including: reminders, status change notifications, assignment notifications, requestor visibility updates, closure messages, and any other chatter activity on ASQs.

### 8. Structured Mentions
Ensure a **structured Salesforce Mention** is used to respond to requestors or to include engineers assigned the ASQ or marked for #Shadow on the ASQ.
