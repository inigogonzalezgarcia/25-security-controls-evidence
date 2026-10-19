# Data format

Five files in one folder. Only `controls.csv` is required; each other file switches on its checks. Comma or semicolon separated, UTF-8 (a BOM is fine). Dates as `YYYY-MM-DD` or `DD/MM/YYYY`. Column names are case-insensitive.

## controls.csv: the control register

| Column | Required | Meaning |
|---|---|---|
| `id` | yes | Your control id, e.g. `SC-09` |
| `title` | | Short description |
| `domain` | | Identity, Endpoints, Resilience… (only for grouping) |
| `owner` | | The person who answers for it in the audit |
| `status` | | `implemented` (default), `partial`, `planned` or `not_applicable`. Spanish values work too: `implantado`, `parcial`, `planificado`, `no aplica` |
| `maps` | | Requirements it covers, separated by `;`: `ISO27001:A.8.13; NIS2:21.2.c; GDPR:32.1.c`. Aliases: `ISO`, `NIS 2`, `RGPD` |
| `justification` | for `not_applicable` | Why it does not apply (goes into the Statement of Applicability) |
| `last_review` | | Date the control was last reviewed with its owner |
| `target_date` | for `partial` / `planned` | When it will be implemented |

## evidence.csv: what proves each control

| Column | Required | Meaning |
|---|---|---|
| `id` | | Evidence id, e.g. `E13` (generated if empty) |
| `control_id` | yes | The control it proves |
| `description` | | What it is: "Restore test: file, mailbox and VM" |
| `source` | | Where it comes from: Intune, Entra ID, Veeam, SIEM, ITSM… |
| `frequency` | | `weekly`, `monthly`, `quarterly`, `semiannual`, `annual` (default) or `once`. Spanish: `mensual`, `trimestral`, `semestral`, `anual`, `única` |
| `last_collected` | | Date of the copy you hold. Empty = never collected |
| `result` | | `pass`, `partial` or `fail` (`ok`, `ko`, `correcto`, `parcial`, `fallo` also work) |
| `location` | | Folder, ticket or link where the file is kept |
| `collector` | | Who collects it (defaults to the control owner in the outputs) |

The next due date is `last_collected` + 7, 31, 92, 183 or 366 days. Weekly and monthly evidence is treated as routine: it only raises a finding when it is late. Quarterly and longer evidence also gets a warning when it falls due before the audit date, because it needs planning (a restore test, a DR test, an access review).

## exceptions.csv: accepted risks

| Column | Meaning |
|---|---|
| `id` | Exception id |
| `control_id` | The control with the gap |
| `reason` | Why the control cannot be met for now |
| `risk_owner` | Who owns the risk |
| `approved_by`, `approved_on` | Who accepted it and when. Without an approver it does not count |
| `expires` | When it ends. Without one it is flagged |
| `compensating` | What reduces the risk meanwhile |

An approved, unexpired exception stops a `partial` or `planned` control from being flagged as having no plan; the requirement still shows **At risk** in the coverage, because the gap is real.

## frameworks.csv: the requirement catalogue

| Column | Meaning |
|---|---|
| `framework` | `ISO27001`, `NIS2`, `GDPR` or any other name you use in `maps` (e.g. `ENS`, `ISO22301`) |
| `ref` | The reference used in `maps`: `A.8.13`, `21.2.c`, `32.1.c` |
| `title` | Your own short title |
| `mandatory` | `yes` (default) or `no`. A gap in a mandatory requirement is critical, otherwise a warning |

The demo catalogue lists 28 ISO/IEC 27001:2022 Annex A controls relevant to IT operations, the NIS2 measures of article 21(2)(a)–(j) plus articles 20(2) and 23, and GDPR articles 28, 30, 32(1)(a)–(d), 33 and 35. The titles are short descriptions written for this tool; use the official text of each standard for your Statement of Applicability. Add the rest of Annex A, or another framework, by adding rows.

Coverage per requirement:

- **Covered**: every applicable control mapped to it is implemented, has evidence, and all that evidence is current and passing (and, for quarterly or longer evidence, still current on the audit day).
- **Excluded**: only mapped to controls marked `not_applicable` with a justification.
- **At risk**: mapped, but a control is partial or planned, or a piece of evidence is missing, late, partial or failing.
- **Gap**: nothing mapped, or only not-applicable controls without a justification.

## settings.json

```json
{"organisation": "Contoso Iberia", "as_of": "2026-10-19", "audit_date": "2026-11-23",
 "audit_name": "ISO/IEC 27001 surveillance audit", "review_months": 12}
```

`as_of` is the review date (default: today). `audit_date` switches on the audit countdown, the "due before the audit" warnings and the audit week in the calendar. `review_months` is how old a control review can be.
