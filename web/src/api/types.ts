export type JobStage =
  | "uploaded"
  | "ingest"
  | "transcribe"
  | "propose_edits"
  | "waiting_for_approval"
  | "render"
  | "complete"
  | "failed";

export type EditKind = "profanity" | "filler" | "repeat" | "silence" | "noise";
export type VoiceMode = "original" | "synthetic";

export interface Word {
  text: string;
  start_ms: number;
  end_ms: number;
  confidence: number;
}

export interface TranscriptSegment {
  id: number;
  start_ms: number;
  end_ms: number;
  text: string;
  words: Word[];
}

export interface EditProposal {
  id: string;
  kind: EditKind;
  start_ms: number;
  end_ms: number;
  text: string;
  reason: string;
  confidence: number;
  accepted: boolean;
}

export interface MediaInfo {
  duration_ms: number;
  sample_rate: number;
  channels: number;
  codec: string;
  size_bytes: number;
}

export interface OutputFile {
  name: string;
  label: string;
  size_bytes: number;
  content_type: string;
}

export interface QualityReport {
  input_lufs: number | null;
  output_lufs: number | null;
  true_peak_dbtp: number | null;
  removed_ms: number;
  accepted_edits: number;
  rejected_edits: number;
  original_duration_ms: number;
  final_duration_ms: number;
}

export interface Chapter {
  start_ms: number;
  title: string;
}

export interface ShowNotes {
  title: string;
  summary: string;
  chapters: Chapter[];
  keywords: string[];
  generated_by: string;
}

export interface ProcessingJob {
  id: string;
  project_id: string | null;
  asset_name: string;
  display_name: string;
  source_kind: SourceKind;
  archived: boolean;
  order: number;
  tags: string[];
  notes: string;
  text_edits: number;
  publish_kit: PublishKit;
  publish_history: PublishRecord[];
  stage: JobStage;
  progress: number;
  message: string;
  error: string | null;
  created_at: string;
  updated_at: string;
  media: MediaInfo;
  transcription_provider: string;
  language: string | null;
  segments: TranscriptSegment[];
  proposals: EditProposal[];
  voice_mode: VoiceMode;
  show_notes: ShowNotes;
  quality: QualityReport;
  outputs: OutputFile[];
  verification: VerificationReport;
}

export interface JobSummary {
  id: string;
  project_id: string | null;
  asset_name: string;
  display_name: string;
  source_kind: SourceKind;
  archived: boolean;
  order: number;
  tags: string[];
  stage: JobStage;
  progress: number;
  message: string;
  created_at: string;
  updated_at: string;
  duration_ms: number;
  final_duration_ms: number;
  word_count: number;
  proposal_count: number;
  accepted_edits: number;
  flagged_claims: number;
  output_count: number;
  published: number;
  language: string | null;
}

export interface AppSettings {
  transcription: { provider: "faster_whisper" | "openai" | "fake"; model: string; language: string | null };
  language_model: { provider: LlmProviderId; model: string; base_url: string; temperature: number };
  speech: { provider: SpeechProviderId; voice: string; model: string; base_url: string; custom_body_template: string; custom_auth_header: string };
  cleanup: {
    remove_profanity: boolean;
    remove_fillers: boolean;
    remove_repeats: boolean;
    tighten_silence: boolean;
    max_pause_ms: number;
    keep_pause_ms: number;
    extra_bad_words: string[];
    extra_filler_words: string[];
    target_lufs: number;
  };
  fact_check: {
    embedding_provider: "local" | "openai";
    embedding_model: string;
    online_enabled: boolean;
    wikipedia_language: string;
    max_claims: number;
    evidence_per_claim: number;
    min_similarity: number;
  };
  api: { keys: string[]; require_for_ui: boolean };
  images: { provider: "none" | "openai"; model: string };
  keys: { openai_api_key: string; anthropic_api_key: string; gemini_api_key: string; elevenlabs_api_key: string; descript_api_key: string; custom_llm_api_key: string; custom_tts_api_key: string };
}

export type LlmProviderId = "none" | "openai" | "anthropic" | "gemini" | "ollama" | "openai_compatible";
export type SpeechProviderId = "none" | "openai" | "elevenlabs" | "descript" | "custom_http";

export interface LlmProviderInfo {
  id: LlmProviderId;
  label: string;
  needs_key: boolean;
  key_field: string;
  default_model: string;
  default_base_url: string;
  notes: string;
  configured: boolean;
}

export interface SpeechProviderInfo {
  id: SpeechProviderId;
  label: string;
  key_field: string;
  default_model: string;
  default_base_url: string;
  supports_cloning: boolean;
  notes: string;
  configured: boolean;
}

export interface ProviderCatalog {
  llm: LlmProviderInfo[];
  speech: SpeechProviderInfo[];
  current_llm: { provider: LlmProviderId; model: string; configured: boolean };
  current_speech: SpeechProviderId;
}

export interface LlmTestResult {
  ok: boolean;
  provider: string;
  model: string;
  latency_ms: number;
  reply: string;
}

export interface OllamaModel {
  name: string;
  size_gb: number;
  parameter_size: string;
  family: string;
  score: number;
}

export interface OllamaStatus {
  url: string;
  installed_binary: boolean;
  running: boolean;
  models: OllamaModel[];
  recommended: string;
  needs_pull: boolean;
  reason: string;
  budget_gb: number;
  gpu_gb: number | null;
  current_model: string;
  current_loaded: boolean;
  pull: { model: string; status: "idle" | "pulling" | "done" | "failed"; completed: number; total: number; message: string };
}

export interface OllamaSetupResult {
  ok: boolean;
  step: "ready" | "pulling" | "server";
  model?: string;
  reason?: string;
  message: string;
}

export interface ApiKeyInfo {
  prefix: string;
  hint: string;
}

export interface ApiKeyCreated {
  key: string;
  prefix: string;
  label: string;
  header: string;
}

export interface ProviderStatus {
  name: string;
  available: boolean;
  detail: string;
}

export interface ApprovalRequest {
  decisions: { id: string; accepted: boolean }[];
  segments: { id: number; text: string }[];
  voice_mode: VoiceMode;
  title: string;
}

export type Verdict = "supported" | "contradicted" | "unsupported" | "uncertain";
export type VerificationStatus = "not_run" | "running" | "complete" | "failed";

export interface Evidence {
  source_kind: "library" | "online";
  source: string;
  url: string | null;
  excerpt: string;
  score: number;
  library_id: string | null;
  document_id: string | null;
}

export interface FactCheck {
  id: string;
  segment_id: number;
  start_ms: number;
  claim: string;
  verdict: Verdict;
  flagged: boolean;
  confidence: number;
  explanation: string;
  suggested_correction: string;
  evidence: Evidence[];
  dismissed: boolean;
}

export interface VerificationReport {
  status: VerificationStatus;
  message: string;
  error: string | null;
  used_libraries: string[];
  used_online: boolean;
  judge: string;
  claims_checked: number;
  flagged: number;
  checks: FactCheck[];
  finished_at: string | null;
}

export type DocumentStatus = "queued" | "indexing" | "ready" | "failed";

export interface Document {
  id: string;
  library_id: string;
  name: string;
  kind: "file" | "url";
  source_url: string | null;
  content_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error: string | null;
  chunk_count: number;
  characters: number;
  created_at: string;
  updated_at: string;
}

export interface Library {
  id: string;
  name: string;
  description: string;
  embedding: string;
  created_at: string;
  updated_at: string;
  documents: Document[];
}

export interface LibrarySummary {
  id: string;
  name: string;
  description: string;
  embedding: string;
  document_count: number;
  ready_count: number;
  chunk_count: number;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  library_ids: string[];
  linked_project_ids: string[];
  online_fact_check: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectUpsert {
  name: string;
  description: string;
  library_ids: string[];
  linked_project_ids: string[];
  online_fact_check: boolean;
}

export interface SearchHit {
  library_id: string;
  library_name: string;
  document_id: string;
  document_name: string;
  source_url: string | null;
  chunk_index: number;
  text: string;
  score: number;
}

export interface VerifyRequest {
  use_libraries: boolean;
  use_online: boolean;
  library_ids?: string[] | null;
}

export type SourceKind = "audio" | "text";

export interface PublishKit {
  title: string;
  subtitle: string;
  short_description: string;
  long_description: string;
  hashtags: string[];
  keywords: string[];
  social_posts: Record<string, string>;
  youtube_description: string;
  episode_number: number | null;
  season_number: number | null;
  explicit: boolean;
  category: string;
  language: string;
  thumbnail_prompt: string;
  thumbnail_file: string;
  generated_by: string;
  updated_at: string | null;
}

export interface PublishRecord {
  id: string;
  target_id: string;
  target_name: string;
  target_kind: string;
  status: "pending" | "success" | "failed" | "manual";
  message: string;
  url: string | null;
  created_at: string;
}

export interface TargetField {
  name: string;
  label: string;
  secret: boolean;
  placeholder: string;
  required: boolean;
}

export interface TargetKind {
  id: string;
  label: string;
  mode: "api" | "manual";
  fields: TargetField[];
  notes: string;
  docs_url: string;
}

export interface PublishTarget {
  id: string;
  name: string;
  kind: string;
  config: Record<string, string>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  last_result: string;
}

export interface JobStats {
  overview: Record<string, number | string | null | Record<string, number>>;
  edits_by_kind: Record<EditKind, { proposed: number; accepted: number; rejected: number; removed_ms: number; avg_confidence: number | null }>;
  timeline: { bucket_ms: number; labels: string[]; words: number[]; removed_ms: number[]; edits: Record<EditKind, number[]> };
  top_words: { word: string; count: number }[];
  filler_terms: { word: string; count: number }[];
  profanity_terms: { word: string; count: number }[];
  segment_length_histogram: { label: string; count: number }[];
  pause_histogram: { label: string; count: number }[];
  fact_check: { verdicts: Record<string, number>; judge: string; sources: string[] };
  proposals_confidence: { label: string; count: number }[];
}
