"""Claim verification against library and online evidence.

Judging uses a language model when one is configured. Otherwise a transparent
heuristic compares numbers and keywords between the claim and the best evidence
and only ever reports *possible* contradictions.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from uuid import UUID

from ..config import AppSettings
from ..providers import llm
from ..schemas import Evidence, FactCheck, ProcessingJob, Verdict, VerificationReport, VerificationStatus
from .claims import Claim, extract_claims, figures_in, keywords
from .index import search
from .online import wikipedia_evidence
from .schemas import Library

JUDGE_PROMPT = (
    "You are a meticulous fact checker for a podcast. For each claim decide, using ONLY the evidence given, whether the evidence "
    "supports it, contradicts it, or does not cover it. Be strict about numbers, dates and names. "
    "Return JSON: {\"results\": [{\"index\": int, \"verdict\": \"supported|contradicted|unsupported|uncertain\", "
    "\"confidence\": 0-1, \"explanation\": short sentence, \"correction\": corrected statement or empty string}]}\n\n"
)


def _evidence_from_hits(hits, limit: int) -> list[Evidence]:
    return [
        Evidence(source_kind="library", source=f"{hit.library_name} / {hit.document_name}", url=hit.source_url, excerpt=hit.text[:1500], score=hit.score, library_id=hit.library_id, document_id=hit.document_id)
        for hit in hits[:limit]
    ]


def _compare_figures(claim: str, excerpt: str) -> tuple[list[str], list[str], int]:
    """Return (matched figures, conflicting figures, keyword overlap) between a claim and one passage."""
    claim_keywords = {k.lower() for k in keywords(claim, 10)}
    excerpt_lower = excerpt.lower()
    overlap = sum(1 for k in claim_keywords if k in excerpt_lower)
    claim_figures, evidence_figures = figures_in(claim), figures_in(excerpt)
    matched: list[str] = []
    conflicts: list[str] = []
    for unit, values in claim_figures.items():
        found = evidence_figures.get(unit, set())
        for value in values:
            if value in found:
                matched.append(f"{value} {unit}".strip())
            elif found:
                conflicts.append(f"{value} vs {'/'.join(sorted(found)[:3])} {unit}".strip())
    return matched, conflicts, overlap


def heuristic_judge(claim: str, evidence: list[Evidence], min_similarity: float) -> tuple[Verdict, float, str, bool]:
    relevant = [e for e in evidence if e.score >= min_similarity][:4]
    if not relevant:
        return Verdict.UNSUPPORTED, 0.3, "No relevant evidence was found in the selected sources.", False
    total_figures = sum(len(v) for v in figures_in(claim).values())
    best = relevant[0]
    first_conflict: tuple[Evidence, list[str]] | None = None
    for item in relevant:
        matched, conflicts, overlap = _compare_figures(claim, item.excerpt)
        if overlap < 2:
            continue
        if total_figures and matched and len(matched) == total_figures:
            return Verdict.SUPPORTED, min(0.85, 0.5 + item.score / 2), f"Evidence from “{item.source}” mentions the same figures ({', '.join(matched)}).", False
        if conflicts and first_conflict is None:
            first_conflict = (item, conflicts)
    if first_conflict:
        item, conflicts = first_conflict
        soft = item.source_kind == "online"
        confidence = min(0.6 if soft else 0.75, 0.3 + item.score / 2)
        return Verdict.CONTRADICTED, confidence, f"Evidence from “{item.source}” gives different figures: {'; '.join(conflicts[:3])}. Please verify.", True
    matched, _, overlap = _compare_figures(claim, best.excerpt)
    if total_figures and matched:
        return Verdict.UNCERTAIN, 0.45, f"Evidence from “{best.source}” confirms {', '.join(matched)} but not every figure in the claim.", False
    if best.score >= 0.6 and overlap >= 3:
        return Verdict.SUPPORTED, min(0.7, best.score), f"Closely matching passage found in “{best.source}”.", False
    return Verdict.UNCERTAIN, 0.4, f"Related material found in “{best.source}” but it neither clearly confirms nor refutes the claim.", False


def llm_judge(settings: AppSettings, items: list[tuple[Claim, list[Evidence]]]) -> list[tuple[Verdict, float, str, str]] | None:
    provider = settings.language_model.provider
    if provider == "none" or not llm.is_configured(settings):
        return None
    blocks = []
    for index, (claim, evidence) in enumerate(items):
        quotes = "\n".join(f"  - [{e.source_kind}: {e.source}] {e.excerpt[:700]}" for e in evidence) or "  (no evidence found)"
        blocks.append(f"Claim {index}: {claim.text}\nEvidence:\n{quotes}")
    prompt = JUDGE_PROMPT + "\n\n".join(blocks)
    try:
        raw = llm.complete(settings, prompt, json_mode=True)
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0)) if match else {}
    except Exception:  # noqa: BLE001
        return None
    results: dict[int, tuple[Verdict, float, str, str]] = {}
    for item in data.get("results", []) if isinstance(data.get("results"), list) else []:
        try:
            verdict = Verdict(str(item.get("verdict", "uncertain")).lower())
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
            results[int(item["index"])] = (verdict, confidence, str(item.get("explanation", ""))[:2000], str(item.get("correction", ""))[:1000])
        except (KeyError, TypeError, ValueError):
            continue
    if not results:
        return None
    return [results.get(index, (Verdict.UNCERTAIN, 0.3, "The model did not return a verdict for this claim.", "")) for index in range(len(items))]


def verify_job(job: ProcessingJob, libraries: list[Library], use_online: bool, settings: AppSettings) -> VerificationReport:
    report = VerificationReport(status=VerificationStatus.RUNNING, used_libraries=[lib.name for lib in libraries], used_online=use_online)
    claims, extractor = extract_claims(settings, job.segments)
    per_claim = settings.fact_check.evidence_per_claim
    items: list[tuple[Claim, list[Evidence]]] = []
    for claim in claims:
        evidence: list[Evidence] = []
        if libraries:
            evidence += _evidence_from_hits(search(libraries, claim.text, settings, limit=per_claim), per_claim)
        if use_online:
            evidence += [Evidence(source_kind="online", source=f"Wikipedia: {p.title}", url=p.url, excerpt=p.text[:1500], score=p.score) for p in wikipedia_evidence(settings, claim.text, limit=min(3, per_claim))]
        evidence.sort(key=lambda e: e.score, reverse=True)
        items.append((claim, evidence[: per_claim + 2]))

    judged = llm_judge(settings, items) if items else None
    judge_name = settings.language_model.provider if judged else "heuristic"
    checks: list[FactCheck] = []
    for index, (claim, evidence) in enumerate(items):
        if judged:
            verdict, confidence, explanation, correction = judged[index]
            flagged = verdict == Verdict.CONTRADICTED or (verdict == Verdict.UNCERTAIN and confidence >= 0.6)
        else:
            verdict, confidence, explanation, flagged = heuristic_judge(claim.text, evidence, settings.fact_check.min_similarity)
            correction = ""
        checks.append(FactCheck(segment_id=claim.segment_id, start_ms=claim.start_ms, claim=claim.text, verdict=verdict, flagged=flagged, confidence=confidence, explanation=explanation, suggested_correction=correction, evidence=evidence))
    report.checks = checks
    report.claims_checked = len(checks)
    report.flagged = sum(1 for c in checks if c.flagged)
    report.judge = f"{judge_name} (claims: {extractor})"
    report.status = VerificationStatus.COMPLETE
    report.message = f"{report.flagged} of {len(checks)} claims need attention" if checks else "No checkable claims were found in the transcript"
    report.finished_at = datetime.now(UTC)
    return report


def library_ids_for(report: VerificationReport) -> set[UUID]:
    return {e.library_id for c in report.checks for e in c.evidence if e.library_id}
