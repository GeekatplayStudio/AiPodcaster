"""Pydantic models shared by the API, pipeline and persistence layer."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class JobStage(StrEnum):
    UPLOADED = "uploaded"
    INGEST = "ingest"
    TRANSCRIBE = "transcribe"
    PROPOSE_EDITS = "propose_edits"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RENDER = "render"
    COMPLETE = "complete"
    FAILED = "failed"


class EditKind(StrEnum):
    PROFANITY = "profanity"
    FILLER = "filler"
    REPEAT = "repeat"
    SILENCE = "silence"
    NOISE = "noise"


class VoiceMode(StrEnum):
    ORIGINAL = "original"
    SYNTHETIC = "synthetic"


class Word(BaseModel):
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float = Field(default=1.0, ge=0, le=1)


class TranscriptSegment(BaseModel):
    id: int
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str = Field(max_length=5_000)
    words: list[Word] = Field(default_factory=list)


class EditProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: EditKind
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(default="", max_length=500)
    reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    accepted: bool = True


class MediaInfo(BaseModel):
    duration_ms: int = 0
    sample_rate: int = 0
    channels: int = 0
    codec: str = ""
    size_bytes: int = 0


class OutputFile(BaseModel):
    name: str
    label: str
    size_bytes: int = 0
    content_type: str = "application/octet-stream"


class QualityReport(BaseModel):
    input_lufs: float | None = None
    output_lufs: float | None = None
    true_peak_dbtp: float | None = None
    removed_ms: int = 0
    accepted_edits: int = 0
    rejected_edits: int = 0
    original_duration_ms: int = 0
    final_duration_ms: int = 0


class ShowNotes(BaseModel):
    title: str = ""
    summary: str = ""
    chapters: list[dict] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    generated_by: str = "heuristic"


class Verdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"


class Evidence(BaseModel):
    source_kind: str = Field(pattern="^(library|online)$")
    source: str = Field(max_length=300)
    url: str | None = None
    excerpt: str = Field(max_length=1_500)
    score: float = Field(ge=0, le=1)
    library_id: UUID | None = None
    document_id: UUID | None = None


class FactCheck(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    segment_id: int
    start_ms: int = Field(ge=0)
    claim: str = Field(max_length=1_000)
    verdict: Verdict = Verdict.UNCERTAIN
    flagged: bool = False
    confidence: float = Field(default=0, ge=0, le=1)
    explanation: str = Field(default="", max_length=2_000)
    suggested_correction: str = Field(default="", max_length=1_000)
    evidence: list[Evidence] = Field(default_factory=list)
    dismissed: bool = False


class VerificationStatus(StrEnum):
    NOT_RUN = "not_run"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class VerificationReport(BaseModel):
    status: VerificationStatus = VerificationStatus.NOT_RUN
    message: str = ""
    error: str | None = None
    used_libraries: list[str] = Field(default_factory=list)
    used_online: bool = False
    judge: str = ""
    claims_checked: int = 0
    flagged: int = 0
    checks: list[FactCheck] = Field(default_factory=list)
    finished_at: datetime | None = None


class SourceKind(StrEnum):
    AUDIO = "audio"
    TEXT = "text"


class PublishKit(BaseModel):
    """Marketing / distribution copy for one episode, editable by the user."""

    title: str = Field(default="", max_length=200)
    subtitle: str = Field(default="", max_length=300)
    short_description: str = Field(default="", max_length=600)
    long_description: str = Field(default="", max_length=8_000)
    hashtags: list[str] = Field(default_factory=list, max_length=40)
    keywords: list[str] = Field(default_factory=list, max_length=40)
    social_posts: dict[str, str] = Field(default_factory=dict)
    youtube_description: str = Field(default="", max_length=5_000)
    episode_number: int | None = Field(default=None, ge=0)
    season_number: int | None = Field(default=None, ge=0)
    explicit: bool = False
    category: str = Field(default="", max_length=100)
    language: str = Field(default="", max_length=10)
    thumbnail_prompt: str = Field(default="", max_length=1_500)
    thumbnail_file: str = Field(default="", max_length=200)
    generated_by: str = ""
    updated_at: datetime | None = None


class PublishRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    target_id: UUID
    target_name: str
    target_kind: str
    status: str = Field(default="pending", pattern="^(pending|success|failed|manual)$")
    message: str = ""
    url: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ProcessingJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID | None = None
    asset_name: str
    display_name: str = Field(default="", max_length=200)
    source_kind: SourceKind = SourceKind.AUDIO
    source_url: str | None = None
    archived: bool = False
    order: int = 0
    tags: list[str] = Field(default_factory=list, max_length=30)
    notes: str = Field(default="", max_length=4_000)
    text_edits: int = 0
    publish_kit: PublishKit = Field(default_factory=PublishKit)
    publish_history: list[PublishRecord] = Field(default_factory=list)
    stage: JobStage = JobStage.UPLOADED
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    media: MediaInfo = Field(default_factory=MediaInfo)
    transcription_provider: str = ""
    language: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)
    proposals: list[EditProposal] = Field(default_factory=list)
    voice_mode: VoiceMode = VoiceMode.ORIGINAL
    show_notes: ShowNotes = Field(default_factory=ShowNotes)
    quality: QualityReport = Field(default_factory=QualityReport)
    outputs: list[OutputFile] = Field(default_factory=list)
    verification: VerificationReport = Field(default_factory=VerificationReport)


class JobSummary(BaseModel):
    id: UUID
    project_id: UUID | None = None
    asset_name: str
    display_name: str = ""
    source_kind: SourceKind = SourceKind.AUDIO
    source_url: str | None = None
    archived: bool = False
    order: int = 0
    tags: list[str] = Field(default_factory=list)
    stage: JobStage
    progress: int
    message: str
    created_at: datetime
    updated_at: datetime
    duration_ms: int
    final_duration_ms: int = 0
    word_count: int = 0
    proposal_count: int = 0
    accepted_edits: int = 0
    flagged_claims: int = 0
    output_count: int = 0
    published: int = 0
    language: str | None = None


class JobMetaUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    archived: bool | None = None
    project_id: UUID | None = None
    clear_project: bool = False
    tags: list[str] | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=4_000)


class ReorderRequest(BaseModel):
    ids: list[UUID] = Field(max_length=5_000)


class BulkRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(archive|unarchive|delete)$")


class TextIngest(BaseModel):
    text: str = Field(min_length=20, max_length=400_000)
    name: str = Field(default="Pasted transcript", max_length=180)
    project_id: UUID | None = None
    words_per_minute: int = Field(default=150, ge=80, le=260)


class SegmentEdit(BaseModel):
    id: int
    text: str = Field(max_length=5_000)


class TranscriptUpdate(BaseModel):
    segments: list[SegmentEdit] = Field(max_length=10_000)


class ProposalDecision(BaseModel):
    id: UUID
    accepted: bool


class ApprovalRequest(BaseModel):
    decisions: list[ProposalDecision] = Field(default_factory=list, max_length=10_000)
    segments: list[SegmentEdit] = Field(default_factory=list, max_length=10_000)
    voice_mode: VoiceMode = VoiceMode.ORIGINAL
    title: str = Field(default="", max_length=200)


class ProviderStatus(BaseModel):
    name: str
    available: bool
    detail: str


class VerifyRequest(BaseModel):
    use_libraries: bool = True
    use_online: bool = False
    library_ids: list[UUID] | None = Field(default=None, max_length=50)


class FactCheckDecision(BaseModel):
    id: UUID
    dismissed: bool


class UrlImport(BaseModel):
    url: str = Field(min_length=8, max_length=2_000)
    project_id: UUID | None = None


class LocalPathImport(BaseModel):
    path: str = Field(min_length=3, max_length=1_000)
    project_id: UUID | None = None
    copy_file: bool = True
