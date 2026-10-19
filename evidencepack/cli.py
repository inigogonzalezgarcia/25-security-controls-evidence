"""Command line: `demo` builds everything from a fictional control register, `report` runs on your own CSV files."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import report, simulate
from .checks import Config, run_all
from .model import load, parse_date


def run(data: Path, out: Path, title: str, c: Config, as_of: date | None = None, audit: date | None = None) -> dict:
    reg = load(data, as_of)
    if audit:
        reg.audit_date = audit
    findings = run_all(reg, c)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(reg, findings, title), encoding="utf-8")
    (out / "review.md").write_text(report.review_md(reg, findings), encoding="utf-8")
    (out / "evidence-calendar.ics").write_text(report.evidence_ics(reg), encoding="utf-8", newline="")
    report.write_findings(findings, out / "findings.csv")
    report.write_actions(findings, out / "actions.csv")
    report.write_audit_pack(reg, out / "audit-pack.csv")
    report.write_soa(reg, out / "soa.csv")
    return report.summary(reg, findings)


def _date(value: str) -> date:
    d = parse_date(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evidencepack", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="write the fictional register to sample_data/ and build the outputs")
    d.add_argument("--data", type=Path, default=Path("sample_data"))
    d.add_argument("--out", type=Path, default=Path("output"))

    r = sub.add_parser("report", help="build the outputs from your own folder of CSV files")
    r.add_argument("data", type=Path, help="folder with controls.csv (and evidence.csv, exceptions.csv, frameworks.csv, settings.json)")
    r.add_argument("--out", type=Path, default=Path("output"))
    r.add_argument("--title", default="Security controls and evidence")
    r.add_argument("--as-of", type=_date, help="review date, YYYY-MM-DD (default: settings.json or today)")
    r.add_argument("--audit", type=_date, help="audit date, YYYY-MM-DD (default: settings.json)")
    r.add_argument("--overdue-critical", type=int, default=Config.overdue_critical)
    r.add_argument("--audit-window", type=int, default=Config.audit_window)
    r.add_argument("--exception-warning", type=int, default=Config.exception_warning)
    a = p.parse_args(argv)

    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, "Security controls and evidence · Contoso Iberia", Config())
    else:
        c = Config(overdue_critical=a.overdue_critical, audit_window=a.audit_window, exception_warning=a.exception_warning)
        try:
            sm = run(a.data, a.out, a.title, c, a.as_of, a.audit)
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    ready = " · ".join(f"{fw} {p:.0%}" for fw, p in sm["coverage_pct"].items())
    days = f" · audit in {sm['days_to_audit']} days" if sm["days_to_audit"] is not None else ""
    print(f"{sm['applicable']} applicable controls · {sm['evidence_ok']}/{sm['evidence']} evidence current{days} · "
          f"ready: {ready or 'no catalogue'} · {sm['critical']} critical, {sm['warning']} warnings · outputs in {a.out}/")
    return 0
