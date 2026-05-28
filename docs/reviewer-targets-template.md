# Reviewer Targets Template

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.
>
> This template contains **no real personal data**. Use pseudonyms or handles only.

This is a **local planning template** for tracking controlled reviewer outreach.

## Template

For each reviewer, fill out the following fields:

```markdown
### Reviewer [n]

- **Reviewer handle:** @example_handle or pseudonym
- **Reason for asking:** e.g., Python CLI expertise, safety reviewer, docs writer
- **Expected expertise:** e.g., pytest, CLI design, security audit
- **Contact channel:** e.g., GitHub DM, email, Discord
- **Date contacted:** YYYY-MM-DD
- **Response status:** not contacted / contacted / agreed / declined / no response
- **Feedback issue link:** #ISSUE_NUMBER or n/a
- **Classification labels:** type:*, area:*, priority:* (filled after feedback arrives)
- **Follow-up needed:** yes / no
- **Notes:** any additional context
```

## Example entries

### Reviewer 1

- **Reviewer handle:** @cli_reviewer_alpha
- **Reason for asking:** Experienced Python CLI maintainer; can evaluate command structure and help text.
- **Expected expertise:** Click/Typer CLI frameworks, pytest, packaging.
- **Contact channel:** GitHub DM.
- **Date contacted:** 2026-05-28
- **Response status:** agreed.
- **Feedback issue link:** #123
- **Classification labels:** `type: feedback`, `area: cli`, `priority: normal`
- **Follow-up needed:** no.
- **Notes:** Focused on command discoverability; suggested adding `atlas commands` listing.

### Reviewer 2

- **Reviewer handle:** @safety_beta
- **Reason for asking:** Security reviewer with experience in audit logging and kill switches.
- **Expected expertise:** Safety boundaries, audit integrity, threat modeling.
- **Contact channel:** Email.
- **Date contacted:** 2026-05-28
- **Response status:** contacted.
- **Feedback issue link:** n/a
- **Classification labels:** n/a
- **Follow-up needed:** yes (awaiting response).
- **Notes:** Sent walkthrough and checklist. Reminder scheduled for one week.

## Safety rules for this template

- Do not store real names, email addresses, phone numbers, or physical addresses.
- Do not store credentials, API keys, or broker account details.
- Do not share this file outside the maintainer team.
- Treat this as a planning aid, not a customer database.
