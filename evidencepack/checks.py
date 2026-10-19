"""Checks: evidence freshness and results, control status and ownership, exceptions, and coverage per framework."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .model import Control, Evidence, Register

CRITICAL, WARNING, INFO = "critical", "warning", "info"
SEV_ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Evidence", "Controls", "Exceptions", "Coverage", "Data quality")
FRAMEWORK_NAMES = {"ISO27001": "ISO/IEC 27001:2022", "NIS2": "NIS2 art. 21", "GDPR": "GDPR"}


@dataclass
class Config:
    overdue_critical: int = 30      # days overdue that make a missing refresh critical
    due_window: int = 30            # days ahead to warn about evidence falling due (without an audit date)
    audit_window: int = 30          # an audit this close turns every overdue item critical
    exception_warning: int = 30     # days before an exception expires


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    due: date | None = None
    ref: str = ""
    frameworks: list[str] = field(default_factory=list)


def due_date(ev: Evidence) -> date | None:
    if not ev.last_collected or ev.period_days is None:
        return None
    return ev.last_collected + timedelta(days=ev.period_days)


def evidence_state(ev: Evidence, as_of: date) -> str:
    """missing / overdue / fresh (results are judged separately)."""
    if not ev.last_collected:
        return "missing"
    d = due_date(ev)
    if d is not None and d < as_of:
        return "overdue"
    return "fresh"


def routine(ev: Evidence) -> bool:
    """Weekly and monthly evidence comes round on its own; quarterly and longer needs planning."""
    return ev.period_days is not None and ev.period_days <= 31


def evidence_ok(ev: Evidence, as_of: date, audit: date | None = None) -> bool:
    """Fresh, passed, and (for quarterly or longer evidence) still valid on the audit day if there is one."""
    if evidence_state(ev, as_of) != "fresh" or ev.result not in ("pass", ""):
        return False
    d = due_date(ev)
    return not (audit and d and d < audit and not routine(ev))


def frameworks_of(c: Control) -> list[str]:
    seen = []
    for fw, _ in c.maps:
        if fw not in seen:
            seen.append(fw)
    return seen


def active_exception(reg: Register, cid: str):
    return next((x for x in reg.exceptions if x.control_id == cid and x.approved_by
                 and (x.expires is None or x.expires >= reg.as_of)), None)


def _days(n: int) -> str:
    return f"{n} day{'s' if n != 1 else ''}"


def check_evidence(reg: Register, c: Config) -> list[Finding]:
    out, t, audit = [], reg.as_of, reg.audit_date
    audit_close = audit is not None and 0 <= (audit - t).days <= c.audit_window
    for ev in reg.evidence:
        ctl = reg.control(ev.control_id)
        if ctl is None:
            out.append(Finding(WARNING, "Data quality", "EVIDENCE_UNKNOWN_CONTROL", ev.id,
                               f"Evidence '{ev.description}' points to control {ev.control_id}, which is not in controls.csv.",
                               "Fix the control id or add the control to the register.", ev.collector, ref=ev.id))
            continue
        if not ctl.applicable:
            continue
        subj, owner, fws = f"{ev.id} · {ev.description}", ev.collector or ctl.owner, frameworks_of(ctl)
        st = evidence_state(ev, t)
        if st == "missing":
            out.append(Finding(CRITICAL, "Evidence", "EVIDENCE_MISSING", subj,
                               f"Never collected ({ev.frequency}) for {ctl.label}.",
                               f"Collect it (source: {ev.source or 'the source system'}), save it to the evidence folder and record the date.",
                               owner, t, ev.id, fws))
        elif st == "overdue":
            late = (t - due_date(ev)).days
            sev = CRITICAL if late > c.overdue_critical or audit_close else WARNING
            out.append(Finding(sev, "Evidence", "EVIDENCE_OVERDUE", subj,
                               f"Last collected {ev.last_collected:%Y-%m-%d} ({ev.frequency}); due {due_date(ev):%Y-%m-%d}, "
                               f"{_days(late)} late." + (f" The audit is in {_days((audit - t).days)}." if audit_close else ""),
                               f"Run or collect it again (source: {ev.source or 'the source system'}) and replace the old copy.",
                               owner, t, ev.id, fws))
        else:
            d = due_date(ev)
            if d and audit and t <= d < audit and not routine(ev):
                out.append(Finding(WARNING, "Evidence", "EVIDENCE_DUE_BEFORE_AUDIT", subj,
                                   f"Falls due {d:%Y-%m-%d}, before the audit on {audit:%Y-%m-%d}.",
                                   "Collect the next copy before the audit so it is current on the day.", owner, d, ev.id, fws))
            elif d and not audit and not routine(ev) and (d - t).days <= c.due_window:
                out.append(Finding(INFO, "Evidence", "EVIDENCE_DUE_SOON", subj, f"Falls due {d:%Y-%m-%d}.",
                                   "Plan the next collection.", owner, d, ev.id, fws))
        if ev.last_collected and ev.result == "fail":
            out.append(Finding(CRITICAL, "Evidence", "EVIDENCE_FAILED", subj,
                               f"The last result ({ev.last_collected:%Y-%m-%d}) is a fail: the evidence shows the control is not working.",
                               "Fix the cause, re-run the test or report and record it; if it cannot be fixed before the audit, "
                               "raise a dated exception with a compensating control.", owner, t, ev.id, fws))
        elif ev.last_collected and ev.result == "partial":
            out.append(Finding(WARNING, "Evidence", "EVIDENCE_PARTIAL", subj,
                               f"The last result ({ev.last_collected:%Y-%m-%d}) is partial.",
                               "Record what is missing and the date it will be fixed, then collect again.", owner, t, ev.id, fws))
        if ev.last_collected and not ev.location:
            out.append(Finding(WARNING, "Evidence", "EVIDENCE_NO_LOCATION", subj,
                               "No location recorded: nobody will find it when the auditor asks.",
                               "Add the folder, ticket or link where the file is kept.", owner, ref=ev.id, frameworks=fws))
    return out


def check_controls(reg: Register, c: Config) -> list[Finding]:
    out, t = [], reg.as_of
    ev_by = defaultdict(list)
    for ev in reg.evidence:
        ev_by[ev.control_id].append(ev)
    review_limit = t - timedelta(days=round(reg.review_months * 30.44))
    for ctl in reg.controls:
        fws = frameworks_of(ctl)
        if not ctl.applicable:
            if not ctl.justification:
                out.append(Finding(WARNING, "Controls", "NA_NO_JUSTIFICATION", ctl.label,
                                   "Marked not applicable with no justification. The Statement of Applicability needs one.",
                                   "Write why it does not apply (scope, no such systems, covered elsewhere).", ctl.owner,
                                   ref=ctl.id, frameworks=fws))
            continue
        if not ctl.owner:
            out.append(Finding(WARNING, "Controls", "CONTROL_NO_OWNER", ctl.label, "No owner.",
                               "Name one person who answers for this control in the audit.", "", ref=ctl.id, frameworks=fws))
        exc = active_exception(reg, ctl.id)
        if ctl.status in ("partial", "planned"):
            if exc:
                pass  # covered by an approved exception; its expiry is checked separately
            elif ctl.target_date and ctl.target_date < t:
                out.append(Finding(CRITICAL, "Controls", "CONTROL_TARGET_MISSED", ctl.label,
                                   f"{ctl.status.capitalize()}; the target date {ctl.target_date:%Y-%m-%d} has passed and there is no approved exception.",
                                   "Agree a new date with the owner and record a risk acceptance until then.", ctl.owner,
                                   ctl.target_date, ctl.id, fws))
            elif ctl.target_date:
                out.append(Finding(WARNING, "Controls", "CONTROL_NOT_IMPLEMENTED", ctl.label,
                                   f"{ctl.status.capitalize()}, target {ctl.target_date:%Y-%m-%d}.",
                                   "Keep the plan moving; if it will not be done by the audit, record an approved exception.",
                                   ctl.owner, ctl.target_date, ctl.id, fws))
            else:
                out.append(Finding(CRITICAL, "Controls", "CONTROL_NO_PLAN", ctl.label,
                                   f"{ctl.status.capitalize()} with no target date and no approved exception.",
                                   "Set a target date and an owner, or record a risk acceptance with an expiry.", ctl.owner,
                                   t, ctl.id, fws))
        if ctl.status == "implemented" and not ev_by[ctl.id]:
            out.append(Finding(CRITICAL, "Controls", "CONTROL_NO_EVIDENCE", ctl.label,
                               "Marked implemented but no evidence is listed: in an audit, a control without proof is a finding.",
                               "Decide what proves it (report, export, ticket, test record), how often, and add it to evidence.csv.",
                               ctl.owner, t, ctl.id, fws))
        if ctl.last_review and ctl.last_review < review_limit:
            out.append(Finding(WARNING, "Controls", "CONTROL_REVIEW_OVERDUE", ctl.label,
                               f"Last reviewed {ctl.last_review:%Y-%m-%d}, more than {reg.review_months} months ago.",
                               "Review the control description, owner and evidence with the owner and record the date.",
                               ctl.owner, ref=ctl.id, frameworks=fws))
        elif not ctl.last_review:
            out.append(Finding(INFO, "Controls", "CONTROL_NEVER_REVIEWED", ctl.label, "No review date recorded.",
                               "Record the date of the last review.", ctl.owner, ref=ctl.id, frameworks=fws))
        if not ctl.maps:
            out.append(Finding(INFO, "Data quality", "CONTROL_UNMAPPED", ctl.label,
                               "Not mapped to any framework requirement.",
                               "Map it (ISO27001:A.x.y; NIS2:21.2.x; GDPR:32.1.x) or check whether it is still needed.",
                               ctl.owner, ref=ctl.id))
    return out


def check_exceptions(reg: Register, c: Config) -> list[Finding]:
    out, t = [], reg.as_of
    for x in reg.exceptions:
        ctl = reg.control(x.control_id)
        subj = f"{x.id} · {ctl.label if ctl else x.control_id}"
        fws = frameworks_of(ctl) if ctl else []
        owner = x.risk_owner or (ctl.owner if ctl else "")
        if ctl is None:
            out.append(Finding(WARNING, "Data quality", "EXCEPTION_UNKNOWN_CONTROL", subj,
                               f"Exception for control {x.control_id}, which is not in controls.csv.",
                               "Fix the control id.", owner, ref=x.id))
        if not x.approved_by:
            out.append(Finding(WARNING, "Exceptions", "EXCEPTION_NOT_APPROVED", subj,
                               f"'{x.reason}' has no approver, so it does not count as an accepted risk.",
                               "Get it approved by the risk owner (or the management body for NIS2) and record who and when.",
                               owner, ref=x.id, frameworks=fws))
        if x.expires is None:
            out.append(Finding(WARNING, "Exceptions", "EXCEPTION_NO_EXPIRY", subj,
                               "No expiry date: an exception without an end date becomes permanent by default.",
                               "Set an expiry (6–12 months) and a review date.", owner, ref=x.id, frameworks=fws))
        elif x.expires < t:
            out.append(Finding(CRITICAL, "Exceptions", "EXCEPTION_EXPIRED", subj,
                               f"Expired {x.expires:%Y-%m-%d} ({_days((t - x.expires).days)} ago): the gap is open again.",
                               "Close the gap, or renew the exception with a fresh risk assessment and approval.",
                               owner, x.expires, x.id, fws))
        elif (x.expires - t).days <= c.exception_warning or (reg.audit_date and x.expires < reg.audit_date):
            out.append(Finding(WARNING, "Exceptions", "EXCEPTION_EXPIRING", subj,
                               f"Expires {x.expires:%Y-%m-%d}" + (f", before the audit on {reg.audit_date:%Y-%m-%d}."
                                                                  if reg.audit_date and x.expires < reg.audit_date else "."),
                               "Decide: close the gap or renew the exception before it expires.", owner, x.expires, x.id, fws))
        if x.approved_by and not x.compensating:
            out.append(Finding(INFO, "Exceptions", "EXCEPTION_NO_COMPENSATING", subj,
                               "No compensating control recorded.",
                               "Write what reduces the risk meanwhile (monitoring, manual check, restricted access).",
                               owner, ref=x.id, frameworks=fws))
    return out


def coverage(reg: Register) -> list[dict]:
    """One row per catalogue requirement: covered / at risk / excluded / gap, with the controls and evidence behind it."""
    by_ref = defaultdict(list)
    for ctl in reg.controls:
        for key in ctl.maps:
            by_ref[key].append(ctl)
    ev_by = defaultdict(list)
    for ev in reg.evidence:
        ev_by[ev.control_id].append(ev)
    rows = []
    for rq in reg.requirements:
        ctls = by_ref.get(rq.key, [])
        app = [c for c in ctls if c.applicable]
        evs = [ev for c in app for ev in ev_by[c.id]]
        if not ctls:
            status, why = "gap", "No control mapped"
        elif not app:
            status = "excluded" if all(c.justification for c in ctls) else "gap"
            why = "Not applicable (justified)" if status == "excluded" else "Not applicable, no justification"
        else:
            good = [c for c in app if c.status == "implemented" and ev_by[c.id]
                    and all(evidence_ok(ev, reg.as_of, reg.audit_date) for ev in ev_by[c.id])]
            excepted = [c for c in app if active_exception(reg, c.id)]
            if len(good) == len(app):
                status, why = "covered", "Every mapped control implemented with current, passing evidence"
            elif excepted:
                status, why = "at_risk", "Open gap under an approved exception"
            else:
                status, why = "at_risk", "Evidence missing, out of date or failing, or control not implemented"
        issues = []
        for c in app:
            if c.status != "implemented":
                issues.append(f"{c.id} {c.status.replace('_', ' ')}")
            elif not ev_by[c.id]:
                issues.append(f"{c.id} no evidence")
            for ev in ev_by[c.id]:
                if not evidence_ok(ev, reg.as_of, reg.audit_date):
                    st = evidence_state(ev, reg.as_of)
                    why = st if st != "fresh" else (ev.result if ev.result in ("fail", "partial") else "due before audit")
                    issues.append(f"{ev.id} {why}")
        rows.append({"req": rq, "status": status, "why": why, "controls": app or ctls, "evidence": evs,
                     "issues": [] if status == "covered" else issues})
    return rows


def check_coverage(reg: Register, c: Config) -> list[Finding]:
    out = []
    known = {r.key for r in reg.requirements}
    for row in coverage(reg):
        rq = row["req"]
        if row["status"] == "gap":
            out.append(Finding(CRITICAL if rq.mandatory else WARNING, "Coverage", "REQUIREMENT_GAP",
                               f"{FRAMEWORK_NAMES.get(rq.framework, rq.framework)} {rq.ref} · {rq.title}",
                               f"{row['why']}.", "Map an existing control to it, add a new control, or justify why it does not apply.",
                               "", reg.as_of, f"{rq.framework}:{rq.ref}", [rq.framework]))
    if reg.requirements:
        for ctl in reg.controls:
            bad = [f"{fw}:{ref}" for fw, ref in ctl.maps if (fw, ref) not in known]
            if bad:
                out.append(Finding(INFO, "Data quality", "UNKNOWN_REFERENCE", ctl.label,
                                   f"Mapped to {', '.join(bad)}, which is not in frameworks.csv.",
                                   "Check the reference or add it to the catalogue.", ctl.owner, ref=ctl.id))
    return out


def run_all(reg: Register, c: Config | None = None) -> list[Finding]:
    c = c or Config()
    fs = check_evidence(reg, c) + check_controls(reg, c) + check_exceptions(reg, c) + check_coverage(reg, c)
    fs.sort(key=lambda f: (SEV_ORDER[f.severity], f.due or date.max, AREAS.index(f.area), f.subject))
    return fs


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {a: "ok" for a in AREAS}
    for f in findings:
        cur = st[f.area]
        if cur == "ok" or SEV_ORDER[f.severity] < SEV_ORDER[cur]:
            st[f.area] = f.severity
    return st


def coverage_summary(reg: Register) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for row in coverage(reg):
        d = out.setdefault(row["req"].framework, {"covered": 0, "at_risk": 0, "excluded": 0, "gap": 0})
        d[row["status"]] += 1
    return out


def collection_calendar(reg: Register, days: int = 90) -> list[dict]:
    """Evidence falling due in the next `days` (and anything already overdue), soonest first."""
    end = reg.as_of + timedelta(days=days)
    rows = []
    for ev in reg.evidence:
        ctl = reg.control(ev.control_id)
        if not ctl or not ctl.applicable:
            continue
        d = due_date(ev) if ev.last_collected else reg.as_of
        if d is not None and d <= end:
            rows.append({"date": d, "evidence": ev, "control": ctl, "overdue": d < reg.as_of or not ev.last_collected})
    return sorted(rows, key=lambda r: (r["date"], r["evidence"].id))


def reuse(reg: Register) -> list[dict]:
    """Evidence items that serve more than one framework: collect once, show to every auditor."""
    rows = []
    for ev in reg.evidence:
        ctl = reg.control(ev.control_id)
        if ctl and ctl.applicable:
            fws = frameworks_of(ctl)
            if len(fws) > 1:
                rows.append({"evidence": ev, "control": ctl, "frameworks": fws})
    return rows
