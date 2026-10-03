"""Per-episode statistics for the Stats page: counts, rates, timelines, distributions."""
from __future__ import annotations

import re
from collections import Counter

from ..rag.claims import STOP
from ..schemas import EditKind, ProcessingJob
from . import languages
from .analysis import DEFAULT_FILLERS, apply_cuts_to_text

WORD = re.compile(r"[^\W\d_][\w'’-]*", re.UNICODE)
BUCKET_MS = 60_000


def _bucket_count(duration_ms: int) -> int:
    return max(1, -(-max(duration_ms, 1) // BUCKET_MS))


def compute_stats(job: ProcessingJob) -> dict:
    duration = job.media.duration_ms or max((s.end_ms for s in job.segments), default=0)
    buckets = _bucket_count(duration)
    words_original = [w for s in job.segments for w in s.words] or [w for s in job.segments for w in _fake_words(s)]
    final_segments = apply_cuts_to_text(job.segments, job.proposals)
    words_final = sum(len(s.text.split()) for s in final_segments)
    tokens = [t.lower() for s in job.segments for t in WORD.findall(s.text)]
    fillers = DEFAULT_FILLERS | set(languages.strong_fillers(job.language)) | set(languages.light_fillers(job.language))
    content_tokens = [t for t in tokens if t not in STOP and t not in fillers and len(t) > 2 and not languages.elongation_kind(t)]
    minutes = max(duration / 60_000, 1 / 60)

    words_per_minute = [0] * buckets
    for word in words_original:
        words_per_minute[min(buckets - 1, word.start_ms // BUCKET_MS)] += 1
    edits_per_minute = {kind.value: [0] * buckets for kind in EditKind}
    removed_per_minute = [0] * buckets
    for proposal in job.proposals:
        index = min(buckets - 1, proposal.start_ms // BUCKET_MS)
        edits_per_minute[proposal.kind.value][index] += 1
        if proposal.accepted:
            removed_per_minute[index] += proposal.end_ms - proposal.start_ms

    by_kind = {}
    for kind in EditKind:
        items = [p for p in job.proposals if p.kind == kind]
        accepted = [p for p in items if p.accepted]
        by_kind[kind.value] = {
            "proposed": len(items),
            "accepted": len(accepted),
            "rejected": len(items) - len(accepted),
            "removed_ms": sum(p.end_ms - p.start_ms for p in accepted),
            "avg_confidence": round(sum(p.confidence for p in items) / len(items), 2) if items else None,
        }
    filler_terms = Counter(p.text.lower().strip(".,!?") for p in job.proposals if p.kind == EditKind.FILLER and p.text)
    profanity_terms = Counter(p.text.lower().strip(".,!?") for p in job.proposals if p.kind == EditKind.PROFANITY and p.text)
    pauses = [p.end_ms - p.start_ms for p in job.proposals if p.kind == EditKind.SILENCE]
    sentence_lengths = [len(s.text.split()) for s in job.segments if s.text]
    verdicts = Counter(c.verdict.value for c in job.verification.checks)
    speakers = Counter(m.group(1) for s in job.segments if (m := re.match(r"^([A-ZÀ-ÖØ-ÞА-ЯЁІЇЄҐΑ-Ω][\w ._'-]{0,30}):\s", s.text)))
    gaps = [b.start_ms - a.end_ms for a, b in zip(words_original, words_original[1:], strict=False) if 0 < b.start_ms - a.end_ms < 10_000]

    return {
        "overview": {
            "source_kind": job.source_kind.value,
            "original_duration_ms": duration,
            "final_duration_ms": job.quality.final_duration_ms or max(0, duration - sum(p.end_ms - p.start_ms for p in job.proposals if p.accepted)),
            "removed_ms": sum(p.end_ms - p.start_ms for p in job.proposals if p.accepted),
            "words_original": len(words_original),
            "words_final": words_final,
            "unique_words": len(set(tokens)),
            "vocabulary_richness": round(len(set(tokens)) / len(tokens), 3) if tokens else 0,
            "words_per_minute": round(len(words_original) / minutes, 1),
            "segments": len(job.segments),
            "avg_segment_words": round(sum(sentence_lengths) / len(sentence_lengths), 1) if sentence_lengths else 0,
            "longest_segment_words": max(sentence_lengths, default=0),
            "speakers": dict(speakers),
            "language": job.language,
            "text_edits": job.text_edits,
            "proposals": len(job.proposals),
            "accepted_edits": sum(1 for p in job.proposals if p.accepted),
            "rejected_edits": sum(1 for p in job.proposals if not p.accepted),
            "filler_rate_per_100_words": round(100 * by_kind["filler"]["proposed"] / max(len(words_original), 1), 2),
            "profanity_count": by_kind["profanity"]["proposed"],
            "repeat_count": by_kind["repeat"]["proposed"],
            "long_pauses": len(pauses),
            "longest_pause_ms": max(pauses, default=0),
            "avg_gap_ms": round(sum(gaps) / len(gaps)) if gaps else 0,
            "input_lufs": job.quality.input_lufs,
            "output_lufs": job.quality.output_lufs,
            "true_peak_dbtp": job.quality.true_peak_dbtp,
            "fact_checks": len(job.verification.checks),
            "fact_flags_open": sum(1 for c in job.verification.checks if c.flagged and not c.dismissed),
            "outputs": len(job.outputs),
            "published": sum(1 for r in job.publish_history if r.status == "success"),
            "stage": job.stage.value,
        },
        "edits_by_kind": by_kind,
        "timeline": {
            "bucket_ms": BUCKET_MS,
            "labels": [f"{index}:00" for index in range(buckets)],
            "words": words_per_minute,
            "removed_ms": removed_per_minute,
            "edits": edits_per_minute,
        },
        "top_words": [{"word": word, "count": count} for word, count in Counter(content_tokens).most_common(15)],
        "filler_terms": [{"word": word, "count": count} for word, count in filler_terms.most_common(10)],
        "profanity_terms": [{"word": word, "count": count} for word, count in profanity_terms.most_common(10)],
        "segment_length_histogram": _histogram(sentence_lengths, [5, 10, 15, 20, 30, 40]),
        "pause_histogram": _histogram([p / 1000 for p in pauses], [1, 2, 3, 5, 8]),
        "fact_check": {"verdicts": dict(verdicts), "judge": job.verification.judge, "sources": job.verification.used_libraries},
        "proposals_confidence": _histogram([p.confidence for p in job.proposals], [0.5, 0.7, 0.8, 0.9, 0.95]),
    }


def _histogram(values: list[float], edges: list[float]) -> list[dict]:
    bins = []
    lower = 0.0
    for edge in edges:
        bins.append({"label": f"{_fmt(lower)}–{_fmt(edge)}", "count": sum(1 for v in values if lower <= v < edge)})
        lower = edge
    bins.append({"label": f"{_fmt(lower)}+", "count": sum(1 for v in values if v >= lower)})
    return bins


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _fake_words(segment):
    """Segments without word timing (synthetic transcripts) still count toward timelines."""
    tokens = segment.text.split()
    if not tokens:
        return []
    step = max((segment.end_ms - segment.start_ms) / len(tokens), 1)
    from ..schemas import Word

    return [Word(text=t, start_ms=int(segment.start_ms + i * step), end_ms=int(segment.start_ms + (i + 1) * step)) for i, t in enumerate(tokens)]
