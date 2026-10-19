# Audit preparation runbook

How to use the tool in the weeks before an ISO 27001 audit (or a NIS2 or GDPR review), and month to month in between.

## Every month (30 minutes)

1. Update `evidence.csv` with what was collected this month: date, result and location. Monthly reports (device compliance, encryption, patching, backups, CAB minutes) are the bulk of it.
2. Run `python -m evidencepack report data/ --out output`.
3. Open `review.md` in the security or service review. Go through **Before the audit** and **This month**; give each line an owner and a date.
4. Import `evidence-calendar.ics` into the team calendar once a quarter so the quarterly and annual items come with a reminder.

## Eight weeks before the audit

- Set `audit_date` in `settings.json`. The quarterly and annual evidence that falls due before the audit now shows up as warnings: book the restore test, the DR test, the access review and the tabletop exercise now, not the week before.
- Check every `partial` or `planned` control: either it will be done by the audit (target date), or it needs an approved exception with a compensating control.
- Check the exceptions: any that expire before the audit need a decision (close or renew).

## Four weeks before

- From 30 days out, anything overdue is critical. Work the `actions.csv` list from the top.
- Fill the gaps in the coverage table: map an existing control, add one, or write the justification for "not applicable".
- Fix the evidence without a location. The auditor's question is always "show me", and the answer has to take seconds.

## The week of the audit

- Hand over `audit-pack.csv` (requirement → control → evidence → where it is, how current it is) and `soa.csv` as the index.
- Keep `report.html` open during the interviews: the requirement table answers "which control covers this?" and the evidence register answers "when did you last check it?".

## After the audit

- Add the auditor's findings as controls (if new) or exceptions (if accepted for now), with owners and dates.
- Record the review date on each control discussed (`last_review`).

## Deciding what counts as evidence

Good evidence is dated, comes from the system itself (an export or report, not a screenshot of a slide), shows the scope (all devices, all users) and is repeatable. For each control, ask:

- What would prove it works today? (a compliance export, a restore log, a signed review)
- How often does it need checking? (monthly for anything that drifts, quarterly for reviews and tests, annually for plans and policies)
- Who collects it, and where does it go?

One piece of evidence often serves several frameworks: the restore test answers ISO 27001 A.8.13, NIS2 21(2)(c) and GDPR 32(1)(c) at once. The report lists these under **Collect once, use for several frameworks**.
