"""Load the control register, the evidence index, exceptions and the framework catalogue from CSV files."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

FREQUENCY_DAYS = {"weekly": 7, "monthly": 31, "quarterly": 92, "semiannual": 183, "annual": 366, "once": None}
FREQ_ALIASES = {"week": "weekly", "semanal": "weekly", "month": "monthly", "mensual": "monthly",
                "quarter": "quarterly", "trimestral": "quarterly", "half-yearly": "semiannual", "semestral": "semiannual",
                "yearly": "annual", "year": "annual", "anual": "annual", "one-off": "once", "unica": "once", "única": "once"}
STATUSES = ("implemented", "partial", "planned", "not_applicable")
STATUS_ALIASES = {"done": "implemented", "implantado": "implemented", "yes": "implemented", "in progress": "partial",
                  "parcial": "partial", "planificado": "planned", "todo": "planned", "n/a": "not_applicable",
                  "na": "not_applicable", "no aplica": "not_applicable", "not applicable": "not_applicable"}
RESULTS = ("pass", "partial", "fail")
RESULT_ALIASES = {"ok": "pass", "passed": "pass", "correcto": "pass", "parcial": "partial", "ko": "fail",
                  "failed": "fail", "fallo": "fail"}
FRAMEWORK_ALIASES = {"iso": "ISO27001", "iso27001": "ISO27001", "iso 27001": "ISO27001", "iso/iec 27001": "ISO27001",
                     "nis2": "NIS2", "nis 2": "NIS2", "gdpr": "GDPR", "rgpd": "GDPR"}


def parse_date(value: str | None) -> date | None:
    v = (value or "").strip()
    if not v:
        return None
    for sep in ("-", "/"):
        parts = v.split(sep)
        if len(parts) == 3:
            try:
                if len(parts[0]) == 4:
                    return date(int(parts[0]), int(parts[1]), int(parts[2]))
                return date(int(parts[2]), int(parts[1]), int(parts[0]))  # DD/MM/YYYY
            except ValueError:
                return None
    return None


def norm_framework(name: str) -> str:
    n = name.strip()
    return FRAMEWORK_ALIASES.get(n.lower(), n)


def parse_refs(value: str) -> list[tuple[str, str]]:
    """'ISO27001:A.8.13; NIS2:21.2.c, GDPR:32.1.c' -> [('ISO27001', 'A.8.13'), ('NIS2', '21.2.c'), ('GDPR', '32.1.c')]"""
    out = []
    for raw in value.replace(",", ";").replace("|", ";").split(";"):
        raw = raw.strip()
        if not raw or ":" not in raw:
            continue
        fw, ref = raw.split(":", 1)
        out.append((norm_framework(fw), ref.strip()))
    return out


@dataclass
class Requirement:
    framework: str
    ref: str
    title: str
    mandatory: bool = True

    @property
    def key(self) -> tuple[str, str]:
        return (self.framework, self.ref)


@dataclass
class Control:
    id: str
    title: str
    domain: str = ""
    owner: str = ""
    status: str = "implemented"
    maps: list[tuple[str, str]] = field(default_factory=list)
    justification: str = ""
    last_review: date | None = None
    target_date: date | None = None
    status_raw: str = ""

    @property
    def applicable(self) -> bool:
        return self.status != "not_applicable"

    @property
    def label(self) -> str:
        return f"{self.id} · {self.title}"


@dataclass
class Evidence:
    id: str
    control_id: str
    description: str
    source: str = ""
    frequency: str = "annual"
    last_collected: date | None = None
    result: str = ""
    location: str = ""
    collector: str = ""
    frequency_raw: str = ""

    @property
    def period_days(self) -> int | None:
        return FREQUENCY_DAYS.get(self.frequency)


@dataclass
class Exception_:
    id: str
    control_id: str
    reason: str
    risk_owner: str = ""
    approved_by: str = ""
    approved_on: date | None = None
    expires: date | None = None
    compensating: str = ""


@dataclass
class Register:
    controls: list[Control]
    evidence: list[Evidence]
    exceptions: list[Exception_]
    requirements: list[Requirement]
    as_of: date
    organisation: str = "Your organisation"
    audit_date: date | None = None
    audit_name: str = ""
    review_months: int = 12

    def control(self, cid: str) -> Control | None:
        return next((c for c in self.controls if c.id == cid), None)


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig")
    first = text.splitlines()[0] if text else ""
    delim = ";" if first.count(";") > first.count(",") else ","
    rows = []
    for r in csv.DictReader(text.splitlines(), delimiter=delim):
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
    return rows


def _status(v: str) -> str:
    s = v.strip().lower().replace("-", "_")
    s = STATUS_ALIASES.get(s.replace("_", " "), STATUS_ALIASES.get(s, s))
    return s if s in STATUSES else ("implemented" if not s else s)


def _freq(v: str) -> str:
    s = v.strip().lower()
    return FREQ_ALIASES.get(s, s) if s else "annual"


def _result(v: str) -> str:
    s = v.strip().lower()
    return RESULT_ALIASES.get(s, s)


def load(folder: Path, as_of: date | None = None) -> Register:
    folder = Path(folder)
    if not (folder / "controls.csv").exists():
        raise FileNotFoundError(f"{folder / 'controls.csv'} not found")
    settings = {}
    if (folder / "settings.json").exists():
        settings = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
    as_of = as_of or parse_date(settings.get("as_of")) or date.today()
    controls = []
    for r in _rows(folder / "controls.csv"):
        if not r.get("id"):
            continue
        controls.append(Control(id=r["id"], title=r.get("title", ""), domain=r.get("domain", ""), owner=r.get("owner", ""),
                                status=_status(r.get("status", "")), status_raw=r.get("status", ""),
                                maps=parse_refs(r.get("maps", "")), justification=r.get("justification", ""),
                                last_review=parse_date(r.get("last_review")), target_date=parse_date(r.get("target_date"))))
    evidence = []
    for r in _rows(folder / "evidence.csv"):
        if not r.get("control_id"):
            continue
        evidence.append(Evidence(id=r.get("id") or f"E{len(evidence) + 1:03d}", control_id=r["control_id"],
                                 description=r.get("description", ""), source=r.get("source", ""),
                                 frequency=_freq(r.get("frequency", "")), frequency_raw=r.get("frequency", ""),
                                 last_collected=parse_date(r.get("last_collected")), result=_result(r.get("result", "")),
                                 location=r.get("location", ""), collector=r.get("collector", "")))
    exceptions = []
    for r in _rows(folder / "exceptions.csv"):
        if not r.get("control_id"):
            continue
        exceptions.append(Exception_(id=r.get("id") or f"X{len(exceptions) + 1:02d}", control_id=r["control_id"],
                                     reason=r.get("reason", ""), risk_owner=r.get("risk_owner", ""),
                                     approved_by=r.get("approved_by", ""), approved_on=parse_date(r.get("approved_on")),
                                     expires=parse_date(r.get("expires")), compensating=r.get("compensating", "")))
    requirements = []
    for r in _rows(folder / "frameworks.csv"):
        if not r.get("framework") or not r.get("ref"):
            continue
        requirements.append(Requirement(framework=norm_framework(r["framework"]), ref=r["ref"], title=r.get("title", ""),
                                        mandatory=r.get("mandatory", "yes").lower() not in {"no", "false", "0"}))
    return Register(controls=controls, evidence=evidence, exceptions=exceptions, requirements=requirements, as_of=as_of,
                    organisation=settings.get("organisation", "Your organisation"),
                    audit_date=parse_date(settings.get("audit_date")), audit_name=settings.get("audit_name", ""),
                    review_months=int(settings.get("review_months", 12)))
