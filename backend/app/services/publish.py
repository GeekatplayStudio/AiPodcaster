"""Builds the publish kit: transcripts, captions, chapters, notes, metadata."""
from __future__ import annotations

import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from ..schemas import OutputFile, ProcessingJob, TranscriptSegment

NEWLINE = chr(10)


def _timestamp(ms: int, srt: bool = True) -> str:
    hours, rem = divmod(max(ms, 0), 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    sep = "," if srt else "."
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{sep}{millis:03d}"


def _short(ms: int) -> str:
    hours, rem = divmod(max(ms, 0) // 1000, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return cleaned[:60] or "episode"


def retime_segments(segments: list[TranscriptSegment], keep: list[tuple[int, int]]) -> list[TranscriptSegment]:
    """Map original timestamps onto the timeline of the rendered file."""
    offsets: list[tuple[int, int, int]] = []
    cursor = 0
    for start, end in keep:
        offsets.append((start, end, cursor))
        cursor += end - start

    def map_time(ms: int) -> int:
        for start, end, new_start in offsets:
            if start <= ms <= end:
                return new_start + (ms - start)
            if ms < start:
                return new_start
        return cursor

    out: list[TranscriptSegment] = []
    for segment in segments:
        words = [w.model_copy(update={"start_ms": map_time(w.start_ms), "end_ms": map_time(w.end_ms)}) for w in segment.words]
        start = words[0].start_ms if words else map_time(segment.start_ms)
        end = words[-1].end_ms if words else map_time(segment.end_ms)
        out.append(segment.model_copy(update={"start_ms": start, "end_ms": max(end, start + 1), "words": words}))
    return out


def write_transcript_txt(path: Path, segments: list[TranscriptSegment]) -> None:
    path.write_text("\n\n".join(f"[{_short(s.start_ms)}] {s.text}" for s in segments) + "\n", "utf-8")


def write_srt(path: Path, segments: list[TranscriptSegment]) -> None:
    blocks = [f"{index}\n{_timestamp(s.start_ms)} --> {_timestamp(s.end_ms)}\n{s.text}\n" for index, s in enumerate(segments, start=1)]
    path.write_text("\n".join(blocks), "utf-8")


def write_vtt(path: Path, segments: list[TranscriptSegment]) -> None:
    blocks = [f"{_timestamp(s.start_ms, srt=False)} --> {_timestamp(s.end_ms, srt=False)}\n{s.text}\n" for s in segments]
    path.write_text("WEBVTT\n\n" + "\n".join(blocks), "utf-8")


def write_chapters(path: Path, chapters: list[dict]) -> None:
    lines = [f"{_short(int(c['start_ms']))} {c['title']}" for c in chapters]
    path.write_text("\n".join(lines) + "\n", "utf-8")


def write_show_notes(path: Path, job: ProcessingJob) -> None:
    notes = job.show_notes
    lines = [f"# {notes.title}", "", notes.summary, "", "## Chapters", ""]
    lines += [f"- {_short(int(c['start_ms']))} — {c['title']}" for c in notes.chapters]
    if notes.keywords:
        lines += ["", "## Keywords", "", ", ".join(notes.keywords)]
    lines += ["", "## Production notes", "", f"- Original duration: {_short(job.quality.original_duration_ms)}", f"- Final duration: {_short(job.quality.final_duration_ms)}", f"- Edits applied: {job.quality.accepted_edits}", f"- Voice: {job.voice_mode.value}"]
    path.write_text("\n".join(lines) + "\n", "utf-8")


def write_metadata(path: Path, job: ProcessingJob) -> None:
    payload = {
        "title": job.show_notes.title,
        "description": job.show_notes.summary,
        "keywords": job.show_notes.keywords,
        "language": job.language,
        "duration_seconds": round(job.quality.final_duration_ms / 1000, 2),
        "published_at": datetime.now(UTC).isoformat(),
        "chapters": job.show_notes.chapters,
        "quality": job.quality.model_dump(),
        "source_file": job.asset_name,
        "voice_mode": job.voice_mode.value,
        "generator": "AiPodcaster",
    }
    path.write_text(json.dumps(payload, indent=2), "utf-8")


def write_edit_list(path: Path, job: ProcessingJob) -> None:
    rows = [p.model_dump(mode="json") for p in job.proposals]
    path.write_text(json.dumps({"job_id": str(job.id), "edits": rows}, indent=2), "utf-8")


def write_fact_check(path: Path, job: ProcessingJob) -> None:
    report = job.verification
    open_flags = sum(1 for c in report.checks if c.flagged and not c.dismissed)
    lines = [
        f"# Fact check report — {job.show_notes.title}",
        "",
        f"Status: {report.status.value} · judge: {report.judge or 'n/a'}",
        f"Sources: {', '.join(report.used_libraries) or 'none'}{' + Wikipedia' if report.used_online else ''}",
        f"Claims checked: {report.claims_checked} · flagged: {open_flags}",
        "",
    ]
    for check in report.checks:
        marker = "⚠️" if check.flagged and not check.dismissed else "✓" if check.verdict.value == "supported" else "•"
        lines.append(f"## {marker} [{_short(check.start_ms)}] {check.claim}")
        lines.append(f"Verdict: **{check.verdict.value}** ({round(check.confidence * 100)}%){' · dismissed' if check.dismissed else ''}")
        lines.append(check.explanation)
        if check.suggested_correction:
            lines.append(f"Suggested correction: {check.suggested_correction}")
        for evidence in check.evidence[:3]:
            link = f" ({evidence.url})" if evidence.url else ""
            lines.append(f"- {evidence.source}{link}: “{evidence.excerpt[:300].strip()}”")
        lines.append("")
    path.write_text(NEWLINE.join(lines) + NEWLINE, "utf-8")


def write_rss_item(path: Path, job: ProcessingJob, audio_name: str) -> None:
    notes = job.show_notes
    xml = f"""<item>
  <title>{_escape(notes.title)}</title>
  <description>{_escape(notes.summary)}</description>
  <enclosure url="https://REPLACE-WITH-YOUR-HOST/{audio_name}" type="audio/mpeg"/>
  <itunes:duration>{_short(job.quality.final_duration_ms)}</itunes:duration>
  <itunes:keywords>{_escape(", ".join(notes.keywords))}</itunes:keywords>
  <pubDate>{datetime.now(UTC).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
</item>
"""
    path.write_text(xml, "utf-8")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_zip(output_dir: Path, files: list[OutputFile], name: str) -> OutputFile:
    target = output_dir / name
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            archive.write(output_dir / item.name, arcname=item.name)
    return OutputFile(name=name, label="Publish kit (zip)", size_bytes=target.stat().st_size, content_type="application/zip")
