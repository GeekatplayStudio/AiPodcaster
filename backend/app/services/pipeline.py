"""Job orchestration: ingest → transcribe → propose → (approval) → render → publish.

Runs in a worker thread so the API stays responsive. Each stage persists its
progress so the client can poll and the job survives a restart.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

from ..config import MAX_DURATION_SECONDS, AppSettings, settings_store
from ..schemas import EditKind, JobStage, OutputFile, ProcessingJob, VoiceMode
from ..storage import JobStore, job_store
from . import analysis, audio, llm, publish, speech
from .transcription import TranscriptionError, build_provider

log = logging.getLogger("aipodcaster.pipeline")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="media")
_active: set[UUID] = set()
_active_lock = threading.Lock()


class PipelineError(RuntimeError):
    pass


def _update(store: JobStore, job: ProcessingJob, stage: JobStage, progress: int, message: str) -> ProcessingJob:
    job.stage, job.progress, job.message = stage, progress, message
    return store.save(job)


def _fail(store: JobStore, job: ProcessingJob, error: Exception) -> None:
    log.exception("Job %s failed", job.id)
    job.stage, job.error, job.message = JobStage.FAILED, str(error)[:500], "Failed"
    store.save(job)


def source_path(store: JobStore, job_id: UUID) -> Path:
    return store.job_dir(job_id) / "source.bin"


def canonical_wav(store: JobStore, job_id: UUID) -> Path:
    return store.job_dir(job_id) / "canonical.wav"


def run_analysis(job_id: UUID, store: JobStore = job_store, settings: AppSettings | None = None) -> ProcessingJob:
    """Synchronous analysis stage (ingest, transcribe, propose)."""
    job = store.get(job_id)
    settings = settings or settings_store.get()
    try:
        job = _update(store, job, JobStage.INGEST, 5, "Validating and converting media")
        source = source_path(store, job.id)
        if not audio.looks_like_media(source):
            raise PipelineError("The uploaded file does not look like a supported audio or video file")
        info = audio.probe(source)
        if info.duration_ms <= 0:
            raise PipelineError("Could not determine the recording length")
        if info.duration_ms > MAX_DURATION_SECONDS * 1000:
            raise PipelineError(f"Recording exceeds the {MAX_DURATION_SECONDS // 60} minute limit")
        job.media = info
        wav = audio.to_wav(source, canonical_wav(store, job.id))
        wav16 = audio.to_wav_16k(source, store.job_dir(job.id) / "speech16k.wav")
        loudness = audio.measure_loudness(wav, settings.cleanup.target_lufs)
        job.quality.input_lufs = loudness["input_i"]
        job.quality.original_duration_ms = info.duration_ms

        job = _update(store, job, JobStage.TRANSCRIBE, 25, f"Transcribing with {settings.transcription.provider}")
        provider = build_provider(settings)
        result = provider.transcribe(wav16)
        if not result.segments:
            raise PipelineError("No speech was detected in the recording")
        job.segments, job.language, job.transcription_provider = result.segments, result.language, result.provider

        job = _update(store, job, JobStage.PROPOSE_EDITS, 70, "Analysing fillers, repeats, profanity and pauses")
        silences = audio.detect_silences(wav, min_ms=max(300, settings.cleanup.max_pause_ms // 2)) if settings.cleanup.tighten_silence else []
        job.proposals = analysis.build_proposals(job.segments, silences, settings.cleanup, info.duration_ms)
        job.show_notes = llm.generate_show_notes(settings, job.segments, Path(job.asset_name).stem.replace("_", " ").replace("-", " ").title())
        job.error = None
        return _update(store, job, JobStage.WAITING_FOR_APPROVAL, 100, f"{len(job.proposals)} suggestions ready for review")
    except (audio.AudioError, TranscriptionError, PipelineError, OSError, ValueError) as error:
        _fail(store, job, error)
        return store.get(job.id)
    except Exception as error:  # noqa: BLE001 - keep the worker alive
        _fail(store, job, error)
        return store.get(job.id)


def run_render(job_id: UUID, store: JobStore = job_store, settings: AppSettings | None = None) -> ProcessingJob:
    """Synchronous render stage; requires an approved job."""
    job = store.get(job_id)
    settings = settings or settings_store.get()
    output_dir = store.output_dir(job.id)
    output_dir.mkdir(exist_ok=True)
    try:
        job = _update(store, job, JobStage.RENDER, 10, "Compiling approved edits")
        wav = canonical_wav(store, job.id)
        duration = job.media.duration_ms
        accepted = [p for p in job.proposals if p.accepted]
        cuts = [(p.start_ms, p.end_ms) for p in accepted]
        keep = analysis.keep_ranges(duration, cuts)
        final_segments = analysis.apply_cuts_to_text(job.segments, job.proposals)
        base = publish.slug(job.show_notes.title or Path(job.asset_name).stem)
        edited_wav = store.job_dir(job.id) / "edited.wav"

        if job.source_kind.value == "text" and job.voice_mode != VoiceMode.SYNTHETIC:
            raise PipelineError("This episode was created from text; choose a synthetic voice provider in Settings to produce audio")
        if job.voice_mode == VoiceMode.SYNTHETIC:
            job = _update(store, job, JobStage.RENDER, 30, f"Synthesising voice with {settings.speech.provider}")
            edited_wav = _synthesise(settings, final_segments, store.job_dir(job.id), edited_wav)
            final_duration = audio.probe(edited_wav).duration_ms
            retimed = _retime_synthetic(final_segments, final_duration)
        else:
            job = _update(store, job, JobStage.RENDER, 30, "Cutting audio")
            audio.cut_segments(wav, edited_wav, keep)
            final_duration = audio.probe(edited_wav).duration_ms
            retimed = publish.retime_segments(final_segments, keep)

        job = _update(store, job, JobStage.RENDER, 60, "Mastering loudness")
        master_wav = output_dir / f"{base}-master.wav"
        audio.master(edited_wav, master_wav, settings.cleanup.target_lufs)
        loudness = audio.measure_loudness(master_wav, settings.cleanup.target_lufs)
        mp3 = output_dir / f"{base}.mp3"
        audio.export_mp3(master_wav, mp3, metadata={"title": job.show_notes.title, "comment": "Produced with AiPodcaster"})

        job = _update(store, job, JobStage.RENDER, 85, "Building publish kit")
        job.quality.output_lufs, job.quality.true_peak_dbtp = loudness["input_i"], loudness["input_tp"]
        job.quality.removed_ms = max(0, duration - final_duration) if job.voice_mode == VoiceMode.ORIGINAL else sum(e - s for s, e in cuts)
        if job.source_kind.value == "text":
            job.media.duration_ms = job.media.duration_ms or final_duration
        job.quality.accepted_edits, job.quality.rejected_edits = len(accepted), len(job.proposals) - len(accepted)
        job.quality.final_duration_ms = final_duration
        job.show_notes.chapters = _retime_chapters(job.show_notes.chapters, keep, job.voice_mode)
        files = _write_kit(output_dir, base, job, retimed, mp3, master_wav)
        files.append(publish.build_zip(output_dir, files, f"{base}-publish-kit.zip"))
        job.outputs = files
        job.error = None
        return _update(store, job, JobStage.COMPLETE, 100, "Episode ready")
    except (audio.AudioError, speech.SpeechError, PipelineError, OSError, ValueError) as error:
        _fail(store, job, error)
        return store.get(job.id)
    except Exception as error:  # noqa: BLE001
        _fail(store, job, error)
        return store.get(job.id)


def _write_kit(output_dir: Path, base: str, job: ProcessingJob, segments, mp3: Path, master_wav: Path) -> list[OutputFile]:
    writers = [
        (f"{base}-transcript.txt", "Transcript (text)", "text/plain", lambda p: publish.write_transcript_txt(p, segments)),
        (f"{base}.srt", "Captions (SRT)", "application/x-subrip", lambda p: publish.write_srt(p, segments)),
        (f"{base}.vtt", "Captions (WebVTT)", "text/vtt", lambda p: publish.write_vtt(p, segments)),
        (f"{base}-chapters.txt", "Chapter markers", "text/plain", lambda p: publish.write_chapters(p, job.show_notes.chapters)),
        (f"{base}-show-notes.md", "Show notes", "text/markdown", lambda p: publish.write_show_notes(p, job)),
        (f"{base}-metadata.json", "Episode metadata", "application/json", lambda p: publish.write_metadata(p, job)),
        (f"{base}-edit-list.json", "Edit decision list", "application/json", lambda p: publish.write_edit_list(p, job)),
        (f"{base}-rss-item.xml", "RSS item snippet", "application/xml", lambda p: publish.write_rss_item(p, job, mp3.name)),
    ]
    if job.verification.checks:
        writers.append((f"{base}-fact-check.md", "Fact check report", "text/markdown", lambda p: publish.write_fact_check(p, job)))
    files = [
        OutputFile(name=mp3.name, label="Episode (MP3)", size_bytes=mp3.stat().st_size, content_type="audio/mpeg"),
        OutputFile(name=master_wav.name, label="Master (WAV)", size_bytes=master_wav.stat().st_size, content_type="audio/wav"),
    ]
    for name, label, content_type, writer in writers:
        path = output_dir / name
        writer(path)
        files.append(OutputFile(name=name, label=label, size_bytes=path.stat().st_size, content_type=content_type))
    return files


def _synthesise(settings: AppSettings, segments, job_dir: Path, target: Path) -> Path:
    from .text_ingest import strip_speaker_labels

    provider = speech.build_speech_provider(settings)
    text = strip_speaker_labels(segments)
    parts: list[Path] = []
    for index, chunk in enumerate(speech.chunk_text(text)):
        parts.append(provider.synthesize(chunk, job_dir / f"tts-{index:03d}.mp3"))
    return audio.concat_files(parts, target)


def _retime_synthetic(segments, final_duration: int):
    """Spread segments proportionally over the synthetic timeline (approximation)."""
    total_chars = sum(len(s.text) for s in segments) or 1
    cursor = 0
    out = []
    for segment in segments:
        length = int(final_duration * len(segment.text) / total_chars)
        out.append(segment.model_copy(update={"start_ms": cursor, "end_ms": cursor + max(length, 1), "words": []}))
        cursor += length
    return out


def _retime_chapters(chapters: list[dict], keep: list[tuple[int, int]], mode: VoiceMode) -> list[dict]:
    if mode == VoiceMode.SYNTHETIC or not chapters:
        return chapters
    offsets = []
    cursor = 0
    for start, end in keep:
        offsets.append((start, end, cursor))
        cursor += end - start
    out = []
    for chapter in chapters:
        ms = int(chapter["start_ms"])
        new = cursor
        for start, end, new_start in offsets:
            if ms <= end:
                new = new_start + max(0, ms - start)
                break
        out.append({**chapter, "start_ms": new})
    return out


def submit(job_id: UUID, stage: str) -> bool:
    """Queue analysis or render on the worker pool; returns False if already running."""
    with _active_lock:
        if job_id in _active:
            return False
        _active.add(job_id)

    def task() -> None:
        try:
            (run_analysis if stage == "analysis" else run_render)(job_id)
        finally:
            with _active_lock:
                _active.discard(job_id)

    _executor.submit(task)
    return True


def is_active(job_id: UUID) -> bool:
    with _active_lock:
        return job_id in _active


def kinds_summary(job: ProcessingJob) -> dict[str, int]:
    summary = {kind.value: 0 for kind in EditKind}
    for proposal in job.proposals:
        summary[proposal.kind.value] += 1
    return summary
