"""Outputs: report.html, review.md, audit-pack.csv, soa.csv, actions.csv, findings.csv and evidence-calendar.ics."""
from __future__ import annotations

import csv
import html
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .checks import (AREAS, CRITICAL, FRAMEWORK_NAMES, INFO, WARNING, Finding, area_status, collection_calendar,
                     coverage, coverage_summary, due_date, evidence_ok, evidence_state, frameworks_of, reuse)
from .model import Register

e = html.escape
STATUS_LABEL = {"covered": "Covered", "at_risk": "At risk", "excluded": "Excluded", "gap": "Gap"}


def summary(reg: Register, findings: list[Finding]) -> dict:
    app = [c for c in reg.controls if c.applicable]
    ids = {c.id for c in app}
    evs = [ev for ev in reg.evidence if ev.control_id in ids]
    cov = coverage_summary(reg)
    pct = {fw: (d["covered"] + d["excluded"]) / max(1, sum(d.values())) for fw, d in cov.items()}
    return {"controls": len(reg.controls), "applicable": len(app), "evidence": len(evs),
            "evidence_ok": sum(evidence_ok(ev, reg.as_of, reg.audit_date) for ev in evs),
            "days_to_audit": (reg.audit_date - reg.as_of).days if reg.audit_date else None,
            "coverage": cov, "coverage_pct": pct,
            "exceptions": sum(1 for x in reg.exceptions if x.expires is None or x.expires >= reg.as_of),
            "critical": sum(f.severity == CRITICAL for f in findings),
            "warning": sum(f.severity == WARNING for f in findings),
            "info": sum(f.severity == INFO for f in findings)}


def write_findings(findings: list[Finding], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["severity", "area", "code", "ref", "subject", "owner", "due", "frameworks", "detail", "next_step"])
        for f in findings:
            w.writerow([f.severity, f.area, f.code, f.ref, f.subject, f.owner, f.due or "", " ".join(f.frameworks),
                        f.detail, f.fix])


def write_actions(findings: list[Finding], path: Path) -> int:
    """One row per action, worst and soonest first, with a 'done' column to tick off before the audit."""
    rows = [f for f in findings if f.severity != INFO]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["priority", "severity", "due", "owner", "subject", "action", "why", "frameworks", "done"])
        for i, f in enumerate(rows, 1):
            w.writerow([i, f.severity, f.due or "", f.owner, f.subject, f.fix, f.detail, " ".join(f.frameworks), ""])
    return len(rows)


def write_audit_pack(reg: Register, path: Path) -> int:
    """The index an auditor asks for: requirement -> control -> evidence -> where it is and how current it is."""
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["framework", "ref", "requirement", "status", "control_id", "control", "control_owner", "evidence_id",
                    "evidence", "source", "frequency", "last_collected", "next_due", "result", "location"])
        for row in coverage(reg):
            rq = row["req"]
            base = [FRAMEWORK_NAMES.get(rq.framework, rq.framework), rq.ref, rq.title, STATUS_LABEL[row["status"]]]
            if not row["controls"]:
                w.writerow(base + [""] * 11)
                n += 1
                continue
            for c in row["controls"]:
                evs = [ev for ev in reg.evidence if ev.control_id == c.id]
                if not evs:
                    w.writerow(base + [c.id, c.title, c.owner] + [""] * 8)
                    n += 1
                for ev in evs:
                    d = due_date(ev)
                    w.writerow(base + [c.id, c.title, c.owner, ev.id, ev.description, ev.source, ev.frequency,
                                       ev.last_collected or "", d or "", ev.result, ev.location])
                    n += 1
    return n


def write_soa(reg: Register, path: Path) -> None:
    """Statement-of-applicability style list of the controls: applicable or not, why, status and evidence count."""
    count = defaultdict(int)
    for ev in reg.evidence:
        count[ev.control_id] += 1
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["control_id", "control", "domain", "owner", "applicable", "justification", "status", "maps",
                    "evidence_items", "last_review"])
        for c in reg.controls:
            w.writerow([c.id, c.title, c.domain, c.owner, "yes" if c.applicable else "no", c.justification,
                        c.status.replace("_", " "), "; ".join(f"{fw}:{ref}" for fw, ref in c.maps), count[c.id],
                        c.last_review or ""])


def evidence_ics(reg: Register, months: int = 12) -> str:
    """Calendar with the next due date of every piece of evidence in the next `months`, with a reminder 7 days before."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end = reg.as_of + timedelta(days=round(months * 30.44))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//evidencepack//evidence//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:Security evidence · {_ics(reg.organisation)}"]
    for ev in reg.evidence:
        c = reg.control(ev.control_id)
        if not c or not c.applicable:
            continue
        d = due_date(ev) if ev.last_collected else reg.as_of
        if d is None:
            continue
        step = ev.period_days
        while d <= end:
            if d >= reg.as_of:
                desc = (f"{ev.description} ({ev.frequency}) for {c.label}. Source: {ev.source or '?'}. "
                        f"Frameworks: {', '.join(frameworks_of(c)) or '-'}.")
                lines += ["BEGIN:VEVENT", f"UID:{ev.id}-{d:%Y%m%d}@evidencepack", f"DTSTAMP:{stamp}",
                          f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
                          f"SUMMARY:{_ics('Collect ' + ev.id + ': ' + ev.description)}", "DESCRIPTION:" + _ics(desc),
                          "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics('Evidence due in 7 days: ' + ev.id)}",
                          "TRIGGER:-P7D", "END:VALARM", "END:VEVENT"]
            if not step:
                break
            d += timedelta(days=step)
    if reg.audit_date and reg.as_of <= reg.audit_date <= end:
        lines += ["BEGIN:VEVENT", f"UID:audit-{reg.audit_date:%Y%m%d}@evidencepack", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{reg.audit_date:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{reg.audit_date + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_ics(reg.audit_name or 'Audit')}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def _ics(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, b = [], line.encode("utf-8")
    while len(b) > 75:
        cut = 75
        while (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b" " + b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)


def review_md(reg: Register, findings: list[Finding]) -> str:
    sm = summary(reg, findings)
    st = area_status(findings)
    when = (f" · {reg.audit_name or 'audit'} on {reg.audit_date:%Y-%m-%d} ({sm['days_to_audit']} days)"
            if reg.audit_date else "")
    lines = [f"# Security controls and evidence · {reg.organisation} · {reg.as_of:%Y-%m-%d}", "",
             f"{sm['applicable']} applicable controls · {sm['evidence_ok']} of {sm['evidence']} evidence items current and "
             f"passing{when} · {sm['critical']} critical, {sm['warning']} warnings.", "",
             "| Framework | Covered | At risk | Excluded | Gap | Ready |", "|---|---|---|---|---|---|"]
    for fw, d in sm["coverage"].items():
        lines.append(f"| {FRAMEWORK_NAMES.get(fw, fw)} | {d['covered']} | {d['at_risk']} | {d['excluded']} | {d['gap']} | "
                     f"{sm['coverage_pct'][fw]:.0%} |")
    lines += ["", "| Area | Status |", "|---|---|"] + [f"| {a} | {'OK' if st[a] == 'ok' else st[a].upper()} |" for a in AREAS]
    for sev, title in ((CRITICAL, "Before the audit"), (WARNING, "This month")):
        items = [f for f in findings if f.severity == sev]
        if items:
            lines += ["", f"## {title}", ""]
            for f in items:
                who = f" · {f.owner}" if f.owner else ""
                fw = f" · {', '.join(f.frameworks)}" if f.frameworks else ""
                lines.append(f"- **{f.subject}**{who}{fw}: {f.detail}  \n  Next step: {f.fix}")
    cal = collection_calendar(reg, 60)
    if cal:
        lines += ["", "## Evidence to collect (overdue and next 60 days)", "", "| Due | Evidence | Control | Who |", "|---|---|---|---|"]
        for r in cal:
            ev = r["evidence"]
            due = "now (overdue)" if r["overdue"] else f"{r['date']:%Y-%m-%d}"
            lines.append(f"| {due} | {ev.id} · {ev.description} | {r['control'].id} | {ev.collector or r['control'].owner or '?'} |")
    infos = [f for f in findings if f.severity == INFO]
    if infos:
        lines += ["", "## For information", ""] + [f"- {f.subject}: {f.detail}" for f in infos]
    lines += ["", "Work list: `actions.csv` · auditor index: `audit-pack.csv` · applicability: `soa.csv` · "
              "calendar: `evidence-calendar.ics`.", ""]
    return "\n".join(lines)


CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb;--na:#8a94a0}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0;--na:#6d7782}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}h3{font-size:15px;margin:22px 0 8px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:26px}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}.area.info{border-left-color:var(--info)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical,.gap{color:var(--bad)}.warning,.at_risk{color:var(--warn)}.info{color:var(--info)}.ok,.covered{color:var(--ok)}.excluded{color:var(--na)}
.area.critical,.area.warning,.area.info,.area.ok{color:inherit}
.fw{display:grid;grid-template-columns:170px 1fr 60px;gap:10px;align-items:center;margin:8px 0}
.stack{display:flex;height:14px;border-radius:7px;overflow:hidden;background:var(--line)}.stack i{display:block;height:100%}
.stack .covered{background:var(--ok)}.stack .at_risk{background:var(--warn)}.stack .excluded{background:var(--na)}.stack .gap{background:var(--bad)}
.legend span{display:inline-block;margin-right:14px;font-size:13px}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.legend .covered{background:var(--ok)}.legend .at_risk{background:var(--warn)}.legend .excluded{background:var(--na)}.legend .gap{background:var(--bad)}
.weeks{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}.wk{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;font-size:12px;min-height:70px}
.wk b{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.wk.audit{border:2px solid var(--info)}
.wk span{display:block;padding:2px 5px;margin-bottom:3px;border-radius:5px;background:var(--line);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wk span.late{border-left:3px solid var(--bad)}
td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);max-width:380px}code{font-size:12px}
footer{margin-top:40px;font-size:13px}
"""


def _pill(s: str) -> str:
    label = STATUS_LABEL.get(s) or ("OK" if s == "ok" else s.upper())
    return f"<span class='pill {s}'>{e(label)}</span>"


def render_html(reg: Register, findings: list[Finding], title: str) -> str:
    sm, st = summary(reg, findings), area_status(findings)
    when = (f" · {e(reg.audit_name or 'audit')} on {reg.audit_date:%d %b %Y}" if reg.audit_date else "")
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>{e(reg.organisation)} · as of {reg.as_of:%d %b %Y}{when}</p>", "<div class='tiles'>"]
    tiles = []
    if sm["days_to_audit"] is not None:
        tiles.append(("Days to the audit", str(sm["days_to_audit"]), f"{reg.audit_date:%d %b %Y}"))
    tiles.append(("Evidence current", f"{sm['evidence_ok']}/{sm['evidence']}", "collected on time and passing"))
    for fw, p in sm["coverage_pct"].items():
        d = sm["coverage"][fw]
        tiles.append((FRAMEWORK_NAMES.get(fw, fw), f"{p:.0%}", f"{d['covered'] + d['excluded']} of {sum(d.values())} ready"))
    tiles.append(("Critical", str(sm["critical"]), f"{sm['warning']} warnings · {sm['info']} for information"))
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(b)}</b><span class='muted'>{e(x)}</span></div>"
          for a, b, x in tiles]
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        h.append(f"<div class='area {st[a]}'><span class='lbl'>{e(a)}</span>{_pill(st[a])}<span class='cnt'>{n} to act on</span></div>")
    h.append("</div>")

    act = [f for f in findings if f.severity == CRITICAL]
    if act:
        h.append("<h2>Before the audit</h2><div class='wrap'><table><tr><th>Subject</th><th>What</th><th>Next step</th><th>Owner</th></tr>")
        h += [f"<tr><td><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)}{' · ' + e(', '.join(f.frameworks)) if f.frameworks else ''}</span></td>"
              f"<td>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner or '?')}</td></tr>" for f in act]
        h.append("</table></div>")

    # coverage bars
    h.append("<h2>Readiness by framework</h2>")
    for fw, d in sm["coverage"].items():
        total = max(1, sum(d.values()))
        segs = "".join(f"<i class='{k}' style='width:{d[k] / total * 100:.1f}%' title='{STATUS_LABEL[k]}: {d[k]}'></i>"
                       for k in ("covered", "excluded", "at_risk", "gap") if d[k])
        h.append(f"<div class='fw'><span>{e(FRAMEWORK_NAMES.get(fw, fw))}</span><div class='stack'>{segs}</div>"
                 f"<span class='num'>{sm['coverage_pct'][fw]:.0%}</span></div>")
    h.append("<p class='legend muted'><span><i class='covered'></i>Covered</span><span><i class='excluded'></i>Excluded (justified)</span>"
             "<span><i class='at_risk'></i>At risk</span><span><i class='gap'></i>Gap</span></p>")

    # requirement matrix
    h.append("<h2>Requirements and what stands in the way</h2>")
    rows = coverage(reg)
    for fw in sm["coverage"]:
        h.append(f"<h3>{e(FRAMEWORK_NAMES.get(fw, fw))}</h3><div class='wrap'><table><tr><th>Ref</th><th>Requirement</th>"
                 "<th>Status</th><th>Controls</th><th>To fix</th></tr>")
        for r in (x for x in rows if x["req"].framework == fw):
            ctl = ", ".join(c.id for c in r["controls"]) or "–"
            fix = ", ".join(r["issues"]) or ("" if r["status"] in ("covered", "excluded") else r["why"])
            h.append(f"<tr><td class='nw'>{e(r['req'].ref)}</td><td>{e(r['req'].title)}</td><td>{_pill(r['status'])}</td>"
                     f"<td class='nw'>{e(ctl)}</td><td class='fix'>{e(fix)}</td></tr>")
        h.append("</table></div>")

    # collection weeks
    cal = collection_calendar(reg, 63)
    h.append("<h2>Evidence to collect · next 9 weeks</h2><div class='weeks'>")
    start = reg.as_of - timedelta(days=reg.as_of.weekday())
    for i in range(9):
        ws, we = start + timedelta(days=7 * i), start + timedelta(days=7 * i + 6)
        items = [r for r in cal if (ws <= r["date"] <= we) or (i == 0 and r["overdue"])]
        audit = reg.audit_date and ws <= reg.audit_date <= we
        spans = "".join(f"<span class='{'late' if r['overdue'] else ''}' title='{e(r['evidence'].description)}'>"
                        f"{'overdue' if r['overdue'] else r['date'].strftime('%d %b')} · {e(r['evidence'].id)} {e(r['evidence'].description)}</span>"
                        for r in items)
        tag = f" · {e(reg.audit_name or 'audit')}" if audit else ""
        h.append(f"<div class='wk{' audit' if audit else ''}'><b>Week of {ws:%d %b}{tag}</b>{spans}</div>")
    h.append("</div><p class='muted'>Red edge: overdue or never collected (shown in the current week). Blue frame: the audit week.</p>")

    # exceptions
    if reg.exceptions:
        h.append("<h2>Exceptions and accepted risks</h2><div class='wrap'><table><tr><th>Id</th><th>Control</th><th>Reason</th>"
                 "<th>Approved</th><th>Expires</th><th>Compensating control</th></tr>")
        for x in reg.exceptions:
            ctl = reg.control(x.control_id)
            cls = "critical" if x.expires and x.expires < reg.as_of else "warning" if not x.expires or not x.approved_by else ""
            h.append(f"<tr><td class='nw'>{e(x.id)}</td><td>{e(ctl.label if ctl else x.control_id)}</td><td>{e(x.reason)}</td>"
                     f"<td class='nw'>{e(x.approved_by or 'not approved')}<br><span class='muted'>{x.approved_on or ''}</span></td>"
                     f"<td class='nw {cls}'>{x.expires or 'no expiry'}</td><td class='fix'>{e(x.compensating or '–')}</td></tr>")
        h.append("</table></div>")

    # evidence register
    h.append("<h2>Evidence register</h2><div class='wrap'><table><tr><th>Id</th><th>Evidence</th><th>Control</th><th>Every</th>"
             "<th>Last</th><th>Next due</th><th>Result</th></tr>")
    for ev in reg.evidence:
        c = reg.control(ev.control_id)
        if not c or not c.applicable:
            continue
        s = evidence_state(ev, reg.as_of)
        d = due_date(ev)
        cls = "critical" if s in ("missing", "overdue") else ""
        rcls = {"pass": "ok", "partial": "warning", "fail": "critical"}.get(ev.result, "")
        h.append(f"<tr><td class='nw'>{e(ev.id)}</td><td>{e(ev.description)}<br><span class='muted'>{e(ev.source)}</span></td>"
                 f"<td class='nw'>{e(c.id)}</td><td>{e(ev.frequency)}</td><td class='nw'>{ev.last_collected or 'never'}</td>"
                 f"<td class='nw {cls}'>{d or ('now' if s == 'missing' else '–')}</td><td class='{rcls}'>{e(ev.result or '–')}</td></tr>")
    h.append("</table></div>")

    ru = reuse(reg)
    if ru:
        h.append(f"<h2>Collect once, use for several frameworks</h2><p class='muted'>{len(ru)} evidence items serve more than one "
                 "framework: the same file answers the ISO auditor, the NIS2 review and the GDPR accountability file.</p>"
                 "<div class='wrap'><table><tr><th>Evidence</th><th>Control</th><th>Frameworks</th></tr>")
        h += [f"<tr><td>{e(r['evidence'].id)} · {e(r['evidence'].description)}</td><td class='nw'>{e(r['control'].id)}</td>"
              f"<td>{e(', '.join(FRAMEWORK_NAMES.get(f, f) for f in r['frameworks']))}</td></tr>" for r in ru]
        h.append("</table></div>")

    h.append("<h2>All findings</h2><div class='wrap'><table><tr><th>Severity</th><th>Area</th><th>Subject</th><th>Detail</th><th>Next step</th></tr>")
    h += [f"<tr><td>{_pill(f.severity)}</td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td><td>{e(f.detail)}</td>"
          f"<td class='fix'>{e(f.fix)}</td></tr>" for f in findings]
    h.append("</table></div><footer class='muted'>Generated by evidencepack from the control register and evidence index. "
             "Requirement titles are short descriptions written for this tool, not the text of the standards. "
             "Fictional demo data unless you ran it on your own files.</footer></main></body></html>")
    return "".join(h)
