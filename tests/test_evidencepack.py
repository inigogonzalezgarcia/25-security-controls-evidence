import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from evidencepack import checks, cli, model, simulate
from evidencepack.checks import CRITICAL, INFO, WARNING, Config, run_all
from evidencepack.model import Control, Evidence, Exception_, Register, Requirement

T = date(2026, 10, 19)


def reg(controls=(), evidence=(), exceptions=(), requirements=(), audit=None, **kw):
    return Register(controls=list(controls), evidence=list(evidence), exceptions=list(exceptions),
                    requirements=list(requirements), as_of=T, organisation="Test", audit_date=audit, **kw)


def ctl(cid="C1", **kw):
    base = dict(id=cid, title="Control", owner="Ana", status="implemented", maps=[("ISO27001", "A.8.13")],
                last_review=date(2026, 3, 1))
    base.update(kw)
    return Control(**base)


def ev(eid="E1", cid="C1", freq="monthly", last=date(2026, 10, 10), result="pass", loc="x", **kw):
    return Evidence(id=eid, control_id=cid, description="Evidence", frequency=freq, last_collected=last, result=result,
                    location=loc, **kw)


def codes(r, c=None):
    return {f.code: f for f in run_all(r, c)}


class ParsingTests(unittest.TestCase):
    def test_refs_dates_and_aliases(self):
        self.assertEqual(model.parse_refs("iso:A.5.15; NIS 2:21.2.i, rgpd:32.1.b | bad"),
                         [("ISO27001", "A.5.15"), ("NIS2", "21.2.i"), ("GDPR", "32.1.b")])
        self.assertEqual(model.parse_date("05/03/2026"), date(2026, 3, 5))
        self.assertEqual(model.parse_date("2026-02-30"), None)

    def test_semicolon_csv_with_bom_and_spanish_values(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "controls.csv").write_text("﻿id;title;owner;status;maps\nC1;Copias;Ana;Implantado;ISO:A.8.13\n"
                                            "C2;CCTV;Ana;No aplica;ISO:A.7.4\n", encoding="utf-8")
            (p / "evidence.csv").write_text("id;control_id;description;frequency;last_collected;result\n"
                                            "E1;C1;Prueba;Trimestral;15/09/2026;Correcto\n", encoding="utf-8")
            r = model.load(p, T)
            self.assertEqual([c.status for c in r.controls], ["implemented", "not_applicable"])
            self.assertEqual((r.evidence[0].frequency, r.evidence[0].result), ("quarterly", "pass"))
            self.assertEqual(r.evidence[0].last_collected, date(2026, 9, 15))


class EvidenceTests(unittest.TestCase):
    def test_clean_register_has_no_findings(self):
        r = reg([ctl()], [ev()], requirements=[Requirement("ISO27001", "A.8.13", "Backup")])
        self.assertEqual(run_all(r), [])
        self.assertEqual(checks.coverage(r)[0]["status"], "covered")

    def test_missing_overdue_thresholds(self):
        self.assertEqual(codes(reg([ctl()], [ev(last=None)]))["EVIDENCE_MISSING"].severity, CRITICAL)
        # monthly = 31 days: collected 2026-09-01 -> due 2026-10-02, 17 days late -> warning
        self.assertEqual(codes(reg([ctl()], [ev(last=date(2026, 9, 1))]))["EVIDENCE_OVERDUE"].severity, WARNING)
        # 31 days late -> critical
        self.assertEqual(codes(reg([ctl()], [ev(last=date(2026, 8, 18))]))["EVIDENCE_OVERDUE"].severity, CRITICAL)
        # exactly at the threshold (30 days late) stays a warning
        self.assertEqual(codes(reg([ctl()], [ev(last=date(2026, 8, 19))]))["EVIDENCE_OVERDUE"].severity, WARNING)

    def test_audit_close_makes_overdue_critical(self):
        r = reg([ctl()], [ev(last=date(2026, 9, 1))], audit=date(2026, 11, 10))
        self.assertEqual(codes(r)["EVIDENCE_OVERDUE"].severity, CRITICAL)

    def test_due_before_audit_only_for_quarterly_and_longer(self):
        audit = date(2026, 12, 1)
        q = codes(reg([ctl()], [ev(freq="quarterly", last=date(2026, 8, 20))], audit=audit))
        self.assertIn("EVIDENCE_DUE_BEFORE_AUDIT", q)
        m = codes(reg([ctl()], [ev(freq="monthly", last=date(2026, 10, 10))], audit=audit))
        self.assertNotIn("EVIDENCE_DUE_BEFORE_AUDIT", m)
        r = reg([ctl()], [ev(freq="quarterly", last=date(2026, 8, 20))], audit=audit,
                requirements=[Requirement("ISO27001", "A.8.13", "Backup")])
        self.assertEqual(checks.coverage(r)[0]["status"], "at_risk")
        self.assertEqual(checks.coverage(r)[0]["issues"], ["E1 due before audit"])

    def test_due_soon_without_audit_and_collection_calendar(self):
        r = reg([ctl()], [ev("E1", freq="quarterly", last=date(2026, 8, 1)), ev("E2", last=None),
                          ev("E3", freq="annual", last=date(2026, 3, 1))])
        f = codes(r)
        self.assertEqual(f["EVIDENCE_DUE_SOON"].severity, INFO)
        cal = checks.collection_calendar(r, 90)
        self.assertEqual([x["evidence"].id for x in cal], ["E2", "E1"])
        self.assertTrue(cal[0]["overdue"])

    def test_results_location_once_and_unknown_control(self):
        f = codes(reg([ctl()], [ev(result="fail"), ev("E2", result="partial", loc="")]))
        self.assertEqual(f["EVIDENCE_FAILED"].severity, CRITICAL)
        self.assertEqual(f["EVIDENCE_PARTIAL"].severity, WARNING)
        self.assertIn("EVIDENCE_NO_LOCATION", f)
        once = codes(reg([ctl()], [ev(freq="once", last=date(2023, 1, 1))]))
        self.assertNotIn("EVIDENCE_OVERDUE", once)
        self.assertIn("EVIDENCE_UNKNOWN_CONTROL", codes(reg([ctl()], [ev(), ev("E9", cid="ZZ")])))


class ControlTests(unittest.TestCase):
    def test_status_plans_and_exceptions(self):
        self.assertEqual(codes(reg([ctl(status="planned")]))["CONTROL_NO_PLAN"].severity, CRITICAL)
        self.assertEqual(codes(reg([ctl(status="partial", target_date=date(2026, 9, 1))]))["CONTROL_TARGET_MISSED"].severity,
                         CRITICAL)
        self.assertEqual(codes(reg([ctl(status="partial", target_date=date(2027, 1, 1))]))["CONTROL_NOT_IMPLEMENTED"].severity,
                         WARNING)
        x = Exception_("X1", "C1", "reason", "Ana", "CIO", date(2026, 5, 1), date(2027, 3, 1), "monitoring")
        f = codes(reg([ctl(status="planned")], exceptions=[x]))
        self.assertNotIn("CONTROL_NO_PLAN", f)

    def test_no_evidence_owner_review_na(self):
        f = codes(reg([ctl(owner="", last_review=date(2025, 6, 1))]))
        self.assertEqual(f["CONTROL_NO_EVIDENCE"].severity, CRITICAL)
        self.assertIn("CONTROL_NO_OWNER", f)
        self.assertIn("CONTROL_REVIEW_OVERDUE", f)
        self.assertIn("NA_NO_JUSTIFICATION", codes(reg([ctl(status="not_applicable")])))
        self.assertNotIn("NA_NO_JUSTIFICATION", codes(reg([ctl(status="not_applicable", justification="no dev")])))
        self.assertIn("CONTROL_UNMAPPED", codes(reg([ctl(maps=[])], [ev()])))


class ExceptionTests(unittest.TestCase):
    def test_expiry_approval_and_compensating(self):
        def x(**kw):
            base = dict(id="X1", control_id="C1", reason="r", risk_owner="Ana", approved_by="CIO",
                        approved_on=date(2026, 1, 1), expires=date(2027, 6, 1), compensating="c")
            base.update(kw)
            return Exception_(**base)
        self.assertEqual(codes(reg([ctl()], [ev()], [x(expires=date(2026, 9, 1))]))["EXCEPTION_EXPIRED"].severity, CRITICAL)
        self.assertEqual(codes(reg([ctl()], [ev()], [x(expires=date(2026, 11, 18))]))["EXCEPTION_EXPIRING"].severity, WARNING)
        self.assertNotIn("EXCEPTION_EXPIRING", codes(reg([ctl()], [ev()], [x(expires=date(2026, 11, 19))])))
        self.assertIn("EXCEPTION_EXPIRING", codes(reg([ctl()], [ev()], [x(expires=date(2026, 12, 1))], audit=date(2026, 12, 5))))
        f = codes(reg([ctl()], [ev()], [x(approved_by="", expires=None, compensating="")]))
        self.assertIn("EXCEPTION_NOT_APPROVED", f)
        self.assertIn("EXCEPTION_NO_EXPIRY", f)
        self.assertNotIn("EXCEPTION_NO_COMPENSATING", f)  # only asked of approved exceptions
        self.assertEqual(codes(reg([ctl()], [ev()], [x(compensating="")]))["EXCEPTION_NO_COMPENSATING"].severity, INFO)


class CoverageTests(unittest.TestCase):
    def test_gap_excluded_and_all_controls_must_be_good(self):
        rqs = [Requirement("ISO27001", "A.5.7", "Threat intel"), Requirement("ISO27001", "A.8.28", "Secure coding"),
               Requirement("NIS2", "21.2.c", "Continuity"), Requirement("NIS2", "21.2.x", "Optional", mandatory=False)]
        c1 = ctl("C1", maps=[("NIS2", "21.2.c")])
        c2 = ctl("C2", maps=[("NIS2", "21.2.c")])
        na = ctl("C3", status="not_applicable", justification="no dev", maps=[("ISO27001", "A.8.28")])
        r = reg([c1, c2, na], [ev("E1", "C1"), ev("E2", "C2", result="fail")], requirements=rqs)
        st = {row["req"].ref: row["status"] for row in checks.coverage(r)}
        self.assertEqual(st, {"A.5.7": "gap", "A.8.28": "excluded", "21.2.c": "at_risk", "21.2.x": "gap"})
        gaps = [f for f in run_all(r) if f.code == "REQUIREMENT_GAP"]
        self.assertEqual(sorted(f.severity for f in gaps), [CRITICAL, WARNING])
        sm = checks.coverage_summary(r)
        self.assertEqual(sm["NIS2"], {"covered": 0, "at_risk": 1, "excluded": 0, "gap": 1})

    def test_unknown_reference_and_reuse(self):
        r = reg([ctl(maps=[("ISO27001", "A.8.13"), ("GDPR", "32.1.c"), ("ISO27001", "A.9.99")])], [ev()],
                requirements=[Requirement("ISO27001", "A.8.13", "Backup"), Requirement("GDPR", "32.1.c", "Restore")])
        self.assertIn("UNKNOWN_REFERENCE", codes(r))
        self.assertEqual(checks.reuse(r)[0]["frameworks"], ["ISO27001", "GDPR"])


class DemoTests(unittest.TestCase):
    def test_demo_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            data, out = Path(d) / "data", Path(d) / "out"
            simulate.write(data)
            sm = cli.run(data, out, "Demo", Config())
            for name in ("report.html", "review.md", "evidence-calendar.ics", "findings.csv", "actions.csv",
                         "audit-pack.csv", "soa.csv"):
                self.assertTrue((out / name).stat().st_size > 0, name)
            found = {row["code"] for row in csv.DictReader(open(out / "findings.csv", encoding="utf-8"))}
            expected = {"EVIDENCE_MISSING", "EVIDENCE_OVERDUE", "EVIDENCE_FAILED", "EVIDENCE_PARTIAL",
                        "EVIDENCE_DUE_BEFORE_AUDIT", "EVIDENCE_NO_LOCATION", "EVIDENCE_UNKNOWN_CONTROL", "CONTROL_NO_PLAN",
                        "CONTROL_NO_EVIDENCE", "CONTROL_NOT_IMPLEMENTED", "CONTROL_NO_OWNER", "CONTROL_REVIEW_OVERDUE",
                        "NA_NO_JUSTIFICATION", "EXCEPTION_EXPIRED", "EXCEPTION_EXPIRING", "EXCEPTION_NOT_APPROVED",
                        "EXCEPTION_NO_EXPIRY", "REQUIREMENT_GAP", "UNKNOWN_REFERENCE"}
            self.assertEqual(expected - found, set())
            self.assertEqual(sm["days_to_audit"], 35)
            self.assertEqual((sm["critical"], sm["evidence_ok"], sm["evidence"]), (9, 19, 32))
            ics = (out / "evidence-calendar.ics").read_bytes().decode("utf-8")
            self.assertTrue(all(len(line.encode()) <= 75 for line in ics.split("\r\n")))
            self.assertIn("DTSTART;VALUE=DATE:20261123", ics)
            soa = list(csv.DictReader(open(out / "soa.csv", encoding="utf-8")))
            self.assertEqual(sum(r["applicable"] == "no" for r in soa), 2)
            settings = json.loads((data / "settings.json").read_text())
            self.assertEqual(settings["audit_date"], "2026-11-23")


if __name__ == "__main__":
    unittest.main()
