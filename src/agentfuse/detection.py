"""Bounded auxiliary signals; a clean scan never grants permission."""
import hashlib
import re
from .contracts import Evidence, ExposureState, ScanReport, Source


class TextScanner:
    patterns = (
        ("injection.override", "injection_pattern", re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)|ignor(?:e|ez|er).{0,30}(?:instructions|règles)|system\s*(?:message|override)|instructions?\s+système", re.I)),
        ("injection.authority", "injection_pattern", re.compile(r"administrator.{0,30}(?:approved|authorized)|administrat(?:eur|rice).{0,30}(?:autoris|approuv|exig)", re.I)),
        ("secret.fixture", "secret_pattern", re.compile(r"AF-DEMO-SECRET-[A-Z0-9-]+")),
    )

    def scan_text(self, text: str, source: Source) -> ScanReport:
        if len(text) > 65536:
            raise ValueError("text exceeds source limit")
        findings = []
        for rule, category, pattern in self.patterns:
            for match in pattern.finditer(text):
                key = f"{source.source_id}:{rule}:{match.start()}:{match.end()}"
                findings.append(Evidence(evidence_id="ev-" + hashlib.sha256(key.encode()).hexdigest()[:24],
                    rule_id=rule, source_id=source.source_id, category=category, start=match.start(), end=match.end()))
                if len(findings) == 256:
                    return ScanReport(source=source, scanner_version="regex-2", status="partial", total_chars=len(text), scanned_chars=len(text), findings=tuple(findings))
        return ScanReport(source=source, scanner_version="regex-2", status="complete", total_chars=len(text), scanned_chars=len(text), findings=tuple(findings))


class SourceTracker:
    def observe(self, state: ExposureState, report: ScanReport) -> ExposureState:
        old = next((s for s in state.sources if s.source_id == report.source.source_id), None)
        if old is not None and old != report.source:
            raise ValueError("source metadata changed within a task")
        complete = state.scans_complete and report.status == "complete"
        if old and complete == state.scans_complete:
            return state
        return ExposureState(task_id=state.task_id, revision=state.revision + 1,
            sources=state.sources if old else (*state.sources, report.source),
            complete=state.complete, scans_complete=complete)
