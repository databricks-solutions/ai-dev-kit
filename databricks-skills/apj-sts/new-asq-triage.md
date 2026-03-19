# APJ STS ASQ Triage

Goal: Triage incoming ASQs for the APJ STS Team and respond to requestor for clarification or recommend engineer to assign to. Follow the steps listed below in plan mode.

## Steps

### 1. Retrieve New ASQs
Start by getting a list of all the new ASQs in the **Technical_Onboarding_Services_APJ** queue in SFDC where the attached use case is **not** in Validating or Lost stage.

If an ASQ has **no use case linked** in the ASQ fields:
- Update the SFDC activity/chatter feed to inform the requestor using a **structured Salesforce Mention** asking them to attach the relevant use case to the ASQ before it can be triaged.
- Change the status of the ASQ to **'Under Review'**.

### 2. Handle Validating/Lost Stage Use Cases
For any ASQs with attached use case in Validating or Lost stage:
- Update the SFDC activity/chatter feed to inform the requestor using a **structured Salesforce Mention** stating STS requires use cases to be within U3-U5 stages.
- Change the status of the ASQs to **'Under Review'**.
- **Exception:** Workspace setup ASQs can be accepted with use case attached in U2 stage.

### 3. Validate Workspace Setup ASQs
For workspace setup ASQs, check if:
- The workspace type has been specified.
- The completed workspace checklist based on the cloud (Azure, AWS, or GCP) has been attached to the ASQ.

If the workspace type is not specified and the workspace checklist is not filled and attached:
- Update the SFDC activity/chatter feed to inform the requestor using a **structured Salesforce Mention** stating the request does not specify the workspace type and cannot be assigned to an engineer. Include a link to [go/wssetup-cheatsheet](https://sites.google.com/databricks.com/sts-workspace-setup) for reference.
- Change the status of the ASQs to **'Under Review'**.

If the workspace type is specified but the workspace checklist has **not** been attached:
- **Assign the ASQ to the most suitable engineer** (do not leave it in the queue) and set status to **'Under Review'** so the engineer can follow up directly.
- Update the SFDC activity/chatter feed using a **structured Salesforce Mention** to the requestor and assigned engineer, stating that no attached document can be seen and the checklist is required before kicking off. Use the language: *"we are unable to see any attached document on this ASQ"*. Include a link to [go/wssetup-cheatsheet](https://sites.google.com/databricks.com/sts-workspace-setup) to help them complete the checklist.

### 4. Validate Against STS Catalog
For **all** ASQs with attached use cases not in Validating or Lost stage (including workspace setup ASQs), validate the request against the [go/sts catalog](https://docs.google.com/presentation/d/1EcxZB5Q5bT3waYUMDM72OcxCEpz6XaXtmJzzPqwSu0E/edit#slide=id.g148df5594df_0_673) of services.

**Explicit exclusion — DBR Migration:** The STS catalog explicitly states DBR Migration is **NOT an ASQ service**. If the primary ask involves a DBR runtime upgrade, set the ASQ to **'On Hold'** and redirect the requestor to:
- Share the "Mastering DBR Migrations at Scale" blog post
- Post questions in **#dbr-migration-squad**
- Invite the customer to the monthly **Databricks Office Hours: DBR Migration**

**Partial scope:** If an ASQ has mixed scope (some components in scope, some out), set to **'On Hold'**, clearly state which parts are outside STS scope, and invite the requestor to refile a focused ASQ for the in-scope components.

If the ASQ requested is fully not covered by the catalog:
- Update the SFDC activity/chatter feed to inform the requestor using a **structured Salesforce Mention** stating the request is outside of STS scope.
- Change the status of the ASQs to **'On Hold'**.

### 5. Validate Launch Accelerator ASQs
For ASQs with category **Launch Accelerator**:
- Analyse the request against the [go/launchaccelerator](https://docs.google.com/presentation/d/14m2jbzDTD3Le_JSbeUDyJ5fxhXbr3ybZ8R-pKvvqNTU/edit?slide=id.g38402bb4784_0_0#slide=id.g38402bb4784_0_0) deck and ensure requirements are met.
- Check consumption on the account to ensure it has **not been over $1000 in the last 6 months**.
- If the requirements are not met:
  - Update the SFDC activity/chatter feed to inform the requestor using a **structured Salesforce Mention** stating the Launch Accelerator requirements are not met.
  - Change the status of the ASQs to **'On Hold'**.

### 6. Recommend Engineer Assignment
For ASQs that qualify for STS support, recommend which APJ STS engineer the request can be assigned to considering the following:

#### Assignment Criteria
- The outcome/ask of the ASQ.
- [Engineer expertise](https://docs.google.com/spreadsheets/d/1vn6LmBVBlthTvyNDJpJLIryIfSy1pU6mN7wFXYobaWE/edit?gid=793712447#gid=793712447).
- [Engineer capacity for coming week and assignment wishlist](https://docs.google.com/spreadsheets/d/127ULgyQH8eDvqNJA5r35xeYvHHfS4_vjnO-BnqEvTNo/edit?gid=2004962154#gid=2004962154).
- **Real-time workload:** Also query SFDC directly for each engineer's current **In Progress** ASQs to get an accurate workload count. The capacity spreadsheet is filled weekly and may be stale — engineers may have ASQs past their end date that are still showing as active.
- Upcoming planned holidays on engineer calendar.
- Take into account if the ASQ requestor has requested for a specific engineer.
- **Sequential/linked ASQs:** When multiple ASQs from the same account are submitted as a phased engagement, note the dependency and assign the same engineer to all phases for continuity.

#### Region/Language Rules
- **Korea** ASQs can be assigned only to **Haley**.
- **Yotaro** can be assigned Japan workspace setup, AI/BI and Lakeflow ASQs.
- **Louis** and **Ching** have to be assigned if Australia or New Zealand time constraints are mentioned.
- **Louis** has to be assigned if Mandarin or Chinese language requirement is specified.

#### Shadow Assignments
- Identify engineers to be added to SFDC chatter/activity for shadow based on the shadow wishlist column in the [capacity spreadsheet](https://docs.google.com/spreadsheets/d/127ULgyQH8eDvqNJA5r35xeYvHHfS4_vjnO-BnqEvTNo/edit?gid=2004962154#gid=2004962154).
- Add engineer for shadow tagging their email id and **#Shadow**.

#### Status Values
- When assigning an ASQ to an engineer, set the status to **'In Progress'**. There is no 'Assigned' status — do not use it.
- When assigning an ASQ to an engineer, also update the **OwnerId** of the ASQ record to the assigned engineer's Salesforce User ID.

#### Output Format
- Show the final results in a **tabular format** with recommendations on all ASQs analyzed. Include:
  - ASQ number
  - Summary of ASQ ask and outcome
  - Use case attached and stage
  - Recommended engineer
  - Any other relevant details
- Formulate an update for the SFDC activity/chatter feed to inform the requestor and assignee. **Always include the original requestor in every SFDC chatter update using a structured Salesforce Mention, even when assigning to a different engineer.**
- Always add this statement at the end of the SFDC chatter/activity update:
  > *'Triaged with the help of Databricks FE AI agents. Please respond via the ASQ or apj-sts slack channel if we got this wrong. We are still evaluating and refining our AI tools and execution.'*
- Ensure a **structured Salesforce Mention** is used to respond to requestors or to include engineers assigned the ASQ or marked for #Shadow on the ASQ.

### 7. Review Before Execution
After completing the analysis:
- Present the full triage results and **ALL** proposed SFDC actions (chatter text, status changes, and @mentions) in a summary table for review.
- **DO NOT** post any SFDC chatter, update any record status, or send any @mentions until explicit confirmation with **"go ahead"** or **"approved"**.
- Wait for explicit approval before executing any writes to Salesforce.
