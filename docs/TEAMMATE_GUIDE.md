# BeLive Tenant Support: teammate quick guide

**For the local v0.3.0 prototype. Existing-tenant enquiries and complaints only.**

[Download the two-page PDF](../output/pdf/BeLive-Quick-Guide.pdf) | [Project and detailed setup](../README.md)

## 1. Open the app and sign in

1. Download this repository using **Code > Download ZIP** and extract it, or pull your existing copy. Install **Python 3.11+** if needed.
2. Double-click **Run BeLive Prototype.bat**. Open **http://127.0.0.1:8877** on the same computer. Keep the Python window open; press **Ctrl+C once** to stop it.
3. On an empty database, choose your own **username, display name and password** (12-128 characters). This creates the first **Admin**. There is **no default password**.

**What is this account for?** It is the operator account for this app. Admins manage records, connections, accounts and backups. They can create **Support** accounts under **Tenant & property records > Operator accounts** for staff handling cases. It is separate from Google/Facebook login, tenant access keys and AI credentials.

## 2. What each page does

| Page | Main purpose |
|---|---|
| Overview | See open cases, urgency, overdue actions and cases needing staff attention. |
| Support cases | Create a complaint/enquiry, review AI assistance, assign staff handling, save replies, follow up and close with evidence. |
| Notifications | Review and approve messages for an external gateway. Delivery requires a configured gateway. Publishing to the local tenant portal is separate. |
| Public monitoring | Read selected authorised Google reviews, Facebook Page feed/post comments or Threads replies. Optional for a first demo. |
| Reviewed memory | Review wording from closed cases for future style guidance. Rejection/reopening stops reuse. This does not train a model or verify facts. |
| Tenant & property records | Add property guidance, verified tenants and support context. Issue portal keys, check the AI connection and manage operator accounts. |
| Database & records | Search saved records, correct support context, see/select the database and manage backups. A selection takes effect after restarting. |
| Reports & activity | See stored case counts and the activity history; export a support snapshot. Keep tenant exports private. |

**Where is everything saved?** In the selected SQLite database, initially **data/belive.db**. Restarting or refreshing keeps saved records. Choosing a new file opens an empty workspace; the old records stay in the old file. Accounts also belong to that database.

**Local prototype:** GitHub shares the code, not a running website. Your friend runs their own copy and database. They cannot reach your computer using their own 127.0.0.1 address.

<!-- PDF_PAGE_BREAK -->

## 3. Try one case from start to finish

For practice, use clearly labelled **DEMO** records in a practice database. To make one: **Database & records > Choose database for next launch**, choose a new filename such as **demo.db**, restart and create its admin. For real cases, use authorised, verified company records.

1. **Add records:** In **Tenant & property records**, save property support guidance first, then a tenant linked to that property and unit. Label practice references/evidence as fictional DEMO data.
2. **Create a case:** Click **New support case**. Try title **Demo Wi-Fi enquiry**, describe the issue, select the demo tenant and choose **Internal / operator intake**, then **Create & assess**.
3. **Handle it:** If AI is not configured or cannot help, staff handover is expected. Open the case, choose **Acknowledge as staff**, add an action note and save the next action/deadline.
4. **Send a portal reply:** Edit **Response draft**, click **Save reviewed wording**, tick the evidence/review confirmation, then **Publish saved response to tenant portal**. Saving a draft alone does not send it.
5. **Try the tenant view:** As admin, use **Issue tenant portal access key**, select the tenant and issue a key. Open the tenant portal on the same computer and enter that key. The tenant can read, reply or select **Issue resolved / Still unresolved**. Tenant feedback does not close the case automatically.
6. **Finish with evidence:** In the operator case, add an action note and choose **Record action & start follow-up**. After checking the outcome, enter evidence, tick confirmation, choose **Record verified resolution**, then **Close verified case**. Complete open work orders first. Record only a simulated outcome for a DEMO case.

## 4. What do I put in Resource?

**Resource identifies the company account, location or post to read.** It is not a URL, tenant reference, property name or database location. Choose the matching API first.

| Selected API / content | Example format only - replace with real IDs |
|---|---|
| Google Business Profile reviews | accounts/123/locations/456 |
| Facebook Page feed | 123456789/feed |
| Facebook post comments | 123456789_987654321/comments |
| Threads post replies | 123456789/replies |

These numbers are **format examples**, not connected BeLive resources. Ask the authorised company account administrator for the actual IDs and API access. Company API tokens belong in this project's **.env**, not in Resource. Only confirm authorisation for an approved resource. See [integration setup](INTEGRATIONS.md) for the technical requirements.

**No company IDs/tokens yet? Skip Public monitoring.** Manual cases and the local portal are enough to demonstrate the workflow. Saving an authorised source starts checks every 15 minutes while the app runs; **Pause checks / Resume checks** control that source.

## 5. Three quick fixes

- **AI hands over to staff:** Configure the project's model/Hermes connection, restart and use **Test AI connection**. A real test may use provider credits. Staff handling works without AI.
- **Tenant sees no reply:** Save the reviewed draft, confirm it and publish it to the portal. Internal notes and unsent drafts stay private.
- **Records seem gone:** Check the active path in **Database & records** and reopen the original database. A new database is a separate workspace.
