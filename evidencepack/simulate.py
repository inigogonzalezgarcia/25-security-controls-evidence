"""Fictional demo data: Contoso Iberia, five weeks before an ISO 27001 surveillance audit, also in scope for NIS2 and GDPR."""
from __future__ import annotations

import csv
import json
from pathlib import Path

AS_OF = "2026-10-19"
AUDIT = "2026-11-23"

# Short titles of the requirements, written for this tool. ISO/IEC 27001 Annex A uses its own control names;
# NIS2 (Directive (EU) 2022/2555) and the GDPR are quoted by article.
FRAMEWORKS = [
    ("ISO27001", "A.5.7", "Threat intelligence"),
    ("ISO27001", "A.5.9", "Inventory of information and assets"),
    ("ISO27001", "A.5.15", "Access control rules"),
    ("ISO27001", "A.5.18", "Access rights: grant, review and remove"),
    ("ISO27001", "A.5.19", "Security in supplier relationships"),
    ("ISO27001", "A.5.23", "Security of cloud services"),
    ("ISO27001", "A.5.24", "Incident management planning"),
    ("ISO27001", "A.5.29", "Security during disruption"),
    ("ISO27001", "A.5.30", "ICT readiness for business continuity"),
    ("ISO27001", "A.5.31", "Legal, regulatory and contractual requirements"),
    ("ISO27001", "A.5.34", "Privacy and protection of personal data"),
    ("ISO27001", "A.6.3", "Security awareness and training"),
    ("ISO27001", "A.7.4", "Physical security monitoring"),
    ("ISO27001", "A.7.10", "Storage media"),
    ("ISO27001", "A.8.1", "User endpoint devices"),
    ("ISO27001", "A.8.2", "Privileged access rights"),
    ("ISO27001", "A.8.5", "Secure authentication"),
    ("ISO27001", "A.8.7", "Protection against malware"),
    ("ISO27001", "A.8.8", "Technical vulnerabilities"),
    ("ISO27001", "A.8.9", "Configuration management"),
    ("ISO27001", "A.8.12", "Data leakage prevention"),
    ("ISO27001", "A.8.13", "Information backup"),
    ("ISO27001", "A.8.15", "Logging"),
    ("ISO27001", "A.8.16", "Monitoring activities"),
    ("ISO27001", "A.8.20", "Network security"),
    ("ISO27001", "A.8.24", "Use of cryptography"),
    ("ISO27001", "A.8.28", "Secure coding"),
    ("ISO27001", "A.8.32", "Change management"),
    ("NIS2", "20.2", "Management body: approval, oversight and training"),
    ("NIS2", "21.2.a", "Risk analysis and information system security policies"),
    ("NIS2", "21.2.b", "Incident handling"),
    ("NIS2", "21.2.c", "Business continuity, backup, disaster recovery and crisis management"),
    ("NIS2", "21.2.d", "Supply chain security"),
    ("NIS2", "21.2.e", "Security in acquisition, development and maintenance, including vulnerability handling"),
    ("NIS2", "21.2.f", "Assessing the effectiveness of the measures"),
    ("NIS2", "21.2.g", "Basic cyber hygiene and cybersecurity training"),
    ("NIS2", "21.2.h", "Cryptography and encryption"),
    ("NIS2", "21.2.i", "HR security, access control and asset management"),
    ("NIS2", "21.2.j", "Multi-factor authentication and secured communications"),
    ("NIS2", "23", "Reporting significant incidents (24 h / 72 h / 1 month)"),
    ("GDPR", "28", "Processor contracts"),
    ("GDPR", "30", "Records of processing activities"),
    ("GDPR", "32.1.a", "Pseudonymisation and encryption"),
    ("GDPR", "32.1.b", "Confidentiality, integrity, availability and resilience"),
    ("GDPR", "32.1.c", "Restore availability and access after an incident"),
    ("GDPR", "32.1.d", "Regular testing of the measures"),
    ("GDPR", "33", "Breach notification to the authority within 72 hours"),
    ("GDPR", "35", "Data protection impact assessment"),
]

LAURA, DIEGO, MARTA, PABLO, ELENA, JAVIER = ("Laura Gómez", "Diego Martín", "Marta Ruiz", "Pablo Ortega",
                                             "Elena Sanz", "Javier Molina")

# id, title, domain, owner, status, maps, justification, last_review, target_date
CONTROLS = [
    ("SC-01", "Asset inventory reconciled with MDM and CMDB", "Assets", MARTA, "implemented",
     "ISO27001:A.5.9; NIS2:21.2.i", "", "2026-03-10", ""),
    ("SC-02", "Quarterly access reviews and leaver removal", "Identity", LAURA, "implemented",
     "ISO27001:A.5.15; ISO27001:A.5.18; NIS2:21.2.i; GDPR:32.1.b", "", "2026-03-10", ""),
    ("SC-03", "Privileged access just in time (PIM)", "Identity", LAURA, "implemented",
     "ISO27001:A.8.2; NIS2:21.2.i", "", "2026-03-10", ""),
    ("SC-04", "MFA and Conditional Access for every user", "Identity", LAURA, "implemented",
     "ISO27001:A.8.5; NIS2:21.2.j; GDPR:32.1.b", "", "2026-03-10", ""),
    ("SC-05", "Endpoint compliance policies (Intune)", "Endpoints", MARTA, "implemented",
     "ISO27001:A.8.1; NIS2:21.2.g", "", "2026-03-11", ""),
    ("SC-06", "Disk encryption with escrowed recovery keys", "Endpoints", MARTA, "implemented",
     "ISO27001:A.8.24; NIS2:21.2.h; GDPR:32.1.a", "", "2026-03-11", ""),
    ("SC-07", "Endpoint detection and response on every device", "Endpoints", MARTA, "implemented",
     "ISO27001:A.8.7; NIS2:21.2.g", "", "2026-03-11", ""),
    ("SC-08", "Vulnerability scanning and patching within SLA", "Operations", DIEGO, "implemented",
     "ISO27001:A.8.8; NIS2:21.2.e; GDPR:32.1.d", "", "2026-03-12", ""),
    ("SC-09", "Backups with an immutable copy and restore tests", "Resilience", DIEGO, "implemented",
     "ISO27001:A.8.13; NIS2:21.2.c; GDPR:32.1.c", "", "2026-03-12", ""),
    ("SC-10", "Disaster recovery and business continuity tests", "Resilience", DIEGO, "implemented",
     "ISO27001:A.5.29; ISO27001:A.5.30; NIS2:21.2.c; GDPR:32.1.c", "", "2026-03-12", ""),
    ("SC-11", "Central logging and security monitoring (SIEM)", "Operations", LAURA, "implemented",
     "ISO27001:A.8.15; ISO27001:A.8.16; NIS2:21.2.b", "", "2026-03-12", ""),
    ("SC-12", "Incident response with 24 h / 72 h notification", "Incidents", LAURA, "implemented",
     "ISO27001:A.5.24; NIS2:21.2.b; NIS2:23; GDPR:33", "", "2026-03-13", ""),
    ("SC-13", "Supplier security assessments and processor agreements", "Suppliers", PABLO, "implemented",
     "ISO27001:A.5.19; ISO27001:A.5.23; NIS2:21.2.d; GDPR:28", "", "2025-06-10", ""),
    ("SC-14", "Security awareness, phishing tests and management training", "People", LAURA, "implemented",
     "ISO27001:A.6.3; NIS2:21.2.g; NIS2:20.2", "", "2026-03-13", ""),
    ("SC-15", "Change management through the CAB", "Operations", PABLO, "implemented",
     "ISO27001:A.8.32; NIS2:21.2.e", "", "2026-03-13", ""),
    ("SC-16", "Network segmentation and firewall rule review", "Network", "", "implemented",
     "ISO27001:A.8.20", "", "2026-03-14", ""),
    ("SC-17", "Records of processing and impact assessments", "Privacy", ELENA, "implemented",
     "ISO27001:A.5.31; ISO27001:A.5.34; GDPR:30; GDPR:35", "", "2026-05-20", ""),
    ("SC-18", "Risk assessment and management review", "Governance", JAVIER, "implemented",
     "NIS2:21.2.a; NIS2:21.2.f; NIS2:20.2; GDPR:32.1.d", "", "2025-12-10", ""),
    ("SC-19", "Secure development", "Development", PABLO, "not_applicable",
     "ISO27001:A.8.28", "No software is developed in house; suppliers' development is covered by SC-13.", "2026-03-14", ""),
    ("SC-20", "Data loss prevention for email and cloud storage", "Privacy", LAURA, "partial",
     "ISO27001:A.8.12; GDPR:32.1.b", "", "2026-03-14", "2027-01-31"),
    ("SC-21", "CCTV and alarm monitoring of the office", "Physical", JAVIER, "not_applicable",
     "ISO27001:A.7.4", "", "2026-03-14", ""),
    ("SC-22", "Removable media blocked except approved devices", "Endpoints", MARTA, "planned",
     "ISO27001:A.7.10; NIS2:21.2.g", "", "2026-03-11", ""),
    ("SC-23", "Secure configuration baselines for servers and laptops", "Operations", DIEGO, "implemented",
     "ISO27001:A.8.9; NIS2:21.2.e; ISO27001:A.8.99", "", "2026-03-12", ""),
]

E = "ISMS/Evidence/"
# id, control, description, source, frequency, last_collected, result, location, collector
EVIDENCE = [
    ("E01", "SC-01", "Device inventory reconciliation (MDM vs CMDB)", "Intune + CMDB", "monthly", "2026-10-03", "pass", E + "2026-10/E01-inventory.xlsx", MARTA),
    ("E02", "SC-02", "Quarterly access review of business groups", "Entra ID access reviews", "quarterly", "2026-07-08", "pass", E + "2026-Q3/E02-access-review.pdf", LAURA),
    ("E03", "SC-02", "Leavers disabled within 24 hours (HR vs directory)", "HR export + Entra ID", "monthly", "2026-09-30", "pass", E + "2026-09/E03-leavers.xlsx", LAURA),
    ("E04", "SC-03", "PIM activations reviewed", "Entra ID PIM", "monthly", "2026-09-12", "pass", E + "2026-09/E04-pim.csv", LAURA),
    ("E05", "SC-04", "Conditional Access policies export", "Entra ID", "quarterly", "2026-08-20", "pass", E + "2026-Q3/E05-ca-policies.json", LAURA),
    ("E06", "SC-04", "MFA registration report (97%, 6 accounts pending)", "Entra ID", "monthly", "2026-10-01", "partial", E + "2026-10/E06-mfa.csv", LAURA),
    ("E07", "SC-05", "Device compliance report", "Intune", "monthly", "2026-10-05", "pass", E + "2026-10/E07-compliance.csv", MARTA),
    ("E08", "SC-06", "Encryption and recovery key escrow report", "Intune + Jamf Pro", "monthly", "2026-10-05", "pass", E + "2026-10/E08-encryption.csv", MARTA),
    ("E09", "SC-07", "EDR coverage: devices without a sensor", "EDR console", "monthly", "2026-08-29", "pass", E + "2026-08/E09-edr.csv", MARTA),
    ("E10", "SC-08", "Vulnerability scan summary (3 critical over SLA)", "Vulnerability scanner", "monthly", "2026-10-02", "partial", E + "2026-10/E10-scan.pdf", DIEGO),
    ("E11", "SC-08", "Patch compliance report", "Intune + WSUS", "monthly", "2026-10-06", "pass", E + "2026-10/E11-patching.csv", DIEGO),
    ("E12", "SC-09", "Backup job report", "Veeam", "weekly", "2026-10-16", "pass", E + "2026-10/E12-backup.pdf", DIEGO),
    ("E13", "SC-09", "Restore test: file, mailbox and VM", "Veeam", "quarterly", "2026-06-12", "pass", E + "2026-Q2/E13-restore.pdf", DIEGO),
    ("E14", "SC-09", "Immutable backup copy check", "Veeam", "monthly", "2026-10-09", "fail", E + "2026-10/E14-immutable.pdf", DIEGO),
    ("E15", "SC-10", "Disaster recovery test report", "DR runbook", "annual", "2025-11-14", "pass", E + "2025/E15-dr-test.pdf", DIEGO),
    ("E16", "SC-10", "Business continuity plan approval", "BCP", "annual", "2026-03-02", "pass", E + "2026/E16-bcp.pdf", JAVIER),
    ("E17", "SC-11", "SIEM data connectors health", "SIEM", "monthly", "2026-10-10", "pass", E + "2026-10/E17-siem.png", LAURA),
    ("E18", "SC-11", "Log retention settings (365 days)", "SIEM + Log Analytics", "annual", "2026-01-20", "pass", E + "2026/E18-retention.png", LAURA),
    ("E19", "SC-12", "Incident response plan and authority contacts", "ISMS", "annual", "2026-02-11", "pass", E + "2026/E19-irp.pdf", LAURA),
    ("E20", "SC-12", "Tabletop exercise report", "ISMS", "annual", "2025-09-30", "pass", E + "2025/E20-tabletop.pdf", LAURA),
    ("E21", "SC-12", "Incident register with notification times", "ITSM", "quarterly", "2026-09-30", "pass", E + "2026-Q3/E21-incidents.xlsx", LAURA),
    ("E22", "SC-13", "Security questionnaires of critical suppliers", "Supplier register", "annual", "2026-04-15", "pass", E + "2026/E22-suppliers.xlsx", PABLO),
    ("E23", "SC-13", "Register of processor agreements", "Legal", "annual", "2026-04-15", "pass", "", ELENA),
    ("E24", "SC-14", "Awareness training completion", "Learning platform", "quarterly", "2026-09-25", "pass", E + "2026-Q3/E24-training.csv", LAURA),
    ("E25", "SC-14", "Phishing simulation results (9% clicked)", "Phishing platform", "quarterly", "2026-07-15", "partial", E + "2026-Q3/E25-phishing.pdf", LAURA),
    ("E26", "SC-14", "Management body cybersecurity training record", "HR", "annual", "", "", "", JAVIER),
    ("E27", "SC-15", "CAB minutes and change log", "ITSM", "monthly", "2026-10-07", "pass", E + "2026-10/E27-cab.pdf", PABLO),
    ("E28", "SC-16", "Firewall rule review", "Firewall", "semiannual", "2026-02-18", "pass", E + "2026/E28-fw-review.xlsx", DIEGO),
    ("E29", "SC-17", "Records of processing reviewed", "Privacy", "annual", "2026-05-20", "pass", E + "2026/E29-ropa.xlsx", ELENA),
    ("E30", "SC-17", "Impact assessment for the HR system", "Privacy", "once", "2025-12-01", "pass", E + "2025/E30-dpia-hr.pdf", ELENA),
    ("E31", "SC-18", "Risk register review", "ISMS", "quarterly", "2026-09-15", "pass", E + "2026-Q3/E31-risks.xlsx", JAVIER),
    ("E32", "SC-18", "Management review minutes and KPIs", "ISMS", "annual", "2025-12-10", "pass", E + "2025/E32-mgmt-review.pdf", JAVIER),
    ("E33", "SC-30", "Visitor log review", "Reception", "monthly", "2026-10-01", "pass", E + "2026-10/E33-visitors.pdf", PABLO),
]

# id, control, reason, risk owner, approved by, approved on, expires, compensating
EXCEPTIONS = [
    ("X01", "SC-08", "Legacy label printer server cannot be patched until it is replaced", DIEGO, JAVIER, "2026-05-10",
     "2026-11-10", "Isolated VLAN, no internet access, weekly scan"),
    ("X02", "SC-20", "DLP rules in audit mode only while false positives are tuned", LAURA, JAVIER, "2026-03-30",
     "2026-09-30", "Weekly review of the DLP audit log"),
    ("X03", "SC-14", "Board members exempt from phishing simulations", LAURA, "", "", "", ""),
]


def write(folder: Path) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    def w(name: str, header: list[str], rows: list[tuple]) -> None:
        with open(folder / name, "w", newline="", encoding="utf-8") as fh:
            cw = csv.writer(fh, lineterminator="\n")
            cw.writerow(header)
            cw.writerows(rows)

    w("frameworks.csv", ["framework", "ref", "title"], FRAMEWORKS)
    w("controls.csv", ["id", "title", "domain", "owner", "status", "maps", "justification", "last_review", "target_date"], CONTROLS)
    w("evidence.csv", ["id", "control_id", "description", "source", "frequency", "last_collected", "result", "location",
                       "collector"], EVIDENCE)
    w("exceptions.csv", ["id", "control_id", "reason", "risk_owner", "approved_by", "approved_on", "expires", "compensating"],
      EXCEPTIONS)
    (folder / "settings.json").write_text(json.dumps(
        {"organisation": "Contoso Iberia", "as_of": AS_OF, "audit_date": AUDIT,
         "audit_name": "ISO/IEC 27001 surveillance audit", "review_months": 12}, indent=2) + "\n", encoding="utf-8")
