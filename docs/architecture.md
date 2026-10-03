# Architecture

## Overview

```
┌──────────────────────┐   /api (Vite proxy)   ┌──────────────────────────────┐
│ web/ (Vite+React+TS) │ ────────────────────▶ │ backend/ (FastAPI, Python)   │
│  Library · Review ·  │ ◀──────────────────── │  routers/  jobs, settings    │
│  Settings            │   JSON + file streams │  services/ pipeline, audio,  │
└──────────────────────┘                       │   transcription, analysis,   │
                                               │   llm, speech, publish       │
                                               │  storage/ data/jobs/<uuid>/  │
                                               └───────┬──────────────────────┘
                                                       │ subprocess (fixed argv)
                                               ┌───────▼──────────┐  ┌──────────────────┐
                                               │ FFmpeg / FFprobe │  │ faster-whisper   │
                                               └──────────────────┘  │ OpenAI / Claude  │
                                                                     │ ElevenLabs       │
                                                                     └──────────────────┘
```

## Pipeline

| Stage | Module | What happens |
| --- | --- | --- |
| upload | `routers/jobs.py` | Streams the multipart body to `data/jobs/<uuid>/source.bin` with a hard byte limit; file name is sanitised and never used in a path. |
| ingest | `services/audio.py` | Magic-byte check, FFprobe metadata, duration limit, canonical mono 48 kHz WAV plus a 16 kHz WAV for ASR, input loudness. |
| transcribe | `services/transcription.py` | Provider interface. Local faster-whisper (CUDA → CPU fallback, VAD, word timestamps) or OpenAI. Words are grouped into sentence segments. |
| propose_edits | `services/analysis.py` | Profanity list (+ user words), filler words and phrases, immediate n-gram repeats, long pauses from FFmpeg `silencedetect`. Produces sorted, de-duplicated `EditProposal`s with reason and confidence. `services/llm.py` adds title/summary/chapters (heuristic or LLM). |
| waiting_for_approval | `routers/jobs.py` | User toggles proposals, edits segment text (`PUT /transcript` keeps word timing), chooses voice mode and title. |
| render | `services/pipeline.py` | Accepted cuts → keep-ranges → single FFmpeg `atrim/concat` graph with 5 ms fades; or TTS chunks concatenated. Then high-pass + compressor + `loudnorm` mastering, MP3 export. |
| publish | `services/publish.py` | Timestamps re-mapped to the new timeline; TXT/SRT/VTT, chapters, show notes, metadata JSON, edit decision list, RSS item, ZIP. |

Jobs run on a two-worker thread pool and persist `job.json` after every stage, so the UI can poll and the server can restart without losing work.

## Fact checking (RAG)

```
Libraries page --upload--> routers/libraries.py --> rag/ingest.py (worker)
                                                   |- rag/parsing.py   PDF/DOCX/EPUB/HTML/text -> chunks (1000 chars, 150 overlap)
                                                   '- rag/index.py     ChromaDB collection per library (cosine), local MiniLM or OpenAI embeddings
Projects page --> routers/projects.py  (library_ids + linked_project_ids -> resolve_library_ids, one hop)
Episode page --> POST /v1/jobs/{id}/verify --> services/verification.py (worker)
                                                   '- rag/verify.py
                                                        |- rag/claims.py     heuristic or LLM claim extraction
                                                        |- rag/index.search  top-k passages from every effective library
                                                        |- rag/online.py     Wikipedia search + extract, re-ranked with local embeddings
                                                        '- judge: LLM (strict JSON verdicts) or figure/keyword heuristic
```

Design points:

- The embedding provider is pinned per library at creation time so vectors and queries always match.
- Verification never mutates the transcript; it stores a `VerificationReport` on the job with claim, verdict, confidence, explanation, evidence and a dismissible flag. Flags appear on transcript segments and in the publish kit.
- The heuristic judge is deliberately conservative: it reports *contradicted* only when the same unit (days, metres, years, ...) appears with a different value in otherwise overlapping text, and it labels itself in the UI.
- Online lookups go to the public Wikipedia API with an identifying user agent; results are re-ranked locally so no transcript text is sent to a third party unless an LLM is configured.

## Provider layer and external access

```
app/providers/llm.py     complete(settings, prompt, json_mode) -> OpenAI | Anthropic | Gemini | Ollama | OpenAI-compatible (httpx only)
app/providers/ollama.py  is_running / try_start_server / list_models / recommend(budget) / pull (background, progress) / warm_up / setup
app/providers/voice.py   build_speech_provider -> OpenAI | ElevenLabs | Descript | CustomHttp ; clone_voice_elevenlabs(sample.wav)
app/security.py          X-API-Key / Bearer middleware; open when no keys exist; UI origin exempt unless api.require_for_ui
app/routers/providers.py /v1/providers/* (catalog, llm/test, ollama/*, voice/clone) and /v1/api-keys
backend/mcp_server.py    MCP (stdio or streamable HTTP) -> calls the REST API with the configured key
```

- `services/llm.py`, `rag/claims.py` and `rag/verify.py` only call `providers.llm.complete`, so adding a backend is one function in `providers/llm.py` plus a catalog entry.
- Ollama model choice: a ranked candidate table (Qwen 3, Gemma 3, Llama 3.1, Mistral Nemo ...) filtered by a memory budget (90 % of GPU memory, else half of RAM). An installed model is kept unless the best downloadable one scores clearly higher. Embedding/vision-only models are excluded.
- The MCP server is a thin client of the REST API; it never touches the file system of the data directory directly, so API-key rules and validation apply to agents too.

## Text episodes, statistics and publishing

```
services/text_ingest.py   detect_format (srt|vtt|timestamped|dialogue|prose) -> TranscriptSegment[] with real or estimated timing
routers/episodes.py       /v1/jobs/text, /text/upload, /{id}/meta, /reorder, /bulk, /{id}/stats
services/stats.py         compute_stats(job): overview, per-minute timelines, edits by kind, histograms, top words, verdicts
publishing/kit.py         generate_kit (LLM JSON or heuristic) · generate_thumbnail (OpenAI images or Pillow cover)
publishing/schemas.py     CATALOG of target kinds (fields, api|manual) · PublishTarget (masked config)
publishing/store.py       data/publish_targets.json
publishing/connectors.py  Package(audio, thumbnail, manifest) -> generic_webhook | wordpress | buzzsprout | transistor | manual checklists
routers/publishing.py     /v1/publish/*, /v1/jobs/{id}/kit*, /publish, /publish/package
```

- A text job is a normal `ProcessingJob` with `source_kind=text`, `voice_mode=synthetic`, estimated `media.duration_ms` and no canonical WAV; the render stage refuses the original-voice path for it.
- `build_manifest` is the single contract shared by all connectors and by the downloadable package; the website receiver in `docs/website-connector` consumes exactly that manifest.
- Charts in the client are dependency-free SVG components (`web/src/components/charts/Charts.tsx`) using the dataviz reference palette as CSS tokens (`--chart-1..6`, status colors), validated for colour-vision separation on both surfaces.
- Themes are CSS custom properties switched by `data-theme` (light/dark/system) and `data-accent` on `<html>`; see `web/src/lib/theme.ts`.

## Workflow, persistence and languages

```
services/workflow.py   LangGraph StateGraph + SqliteSaver (data/checkpoints.sqlite), thread id = "<job>#<run>"
  START ─┬─▶ download ─▶ ingest ─▶ transcribe ─▶ propose ─▶ ⏸ interrupt_before(render) ─▶ render ─▶ END
         ├─▶ ingest   (source already on disk)
         └─▶ render   (re-render of an approved episode)
services/pipeline.py   node bodies: ingest_step, transcribe_step, propose_step, render_step; submit()/submit_resume()
                       with a pending queue so an approval arriving while the worker finishes is never dropped
main.py lifespan       workflow.resume_incomplete(): resumes jobs that were processing when the server stopped
services/languages.py  per-language strong/light fillers, phrases, elongation detection, profanity (anchored stems
                       for ru/uk), stopwords, Whisper verbatim prompts, text language detection
services/estimates.py  real-time factors per device/model → eta_seconds on jobs, /v1/info for the client
services/naming.py     date-based names for generic or missing names
PUT /v1/jobs/{id}/draft  autosave of review decisions, title and voice without rendering
```

- The approval step is a genuine LangGraph human-in-the-loop interrupt; the approval endpoint resumes the paused thread instead of starting a new pipeline.
- Each node persists the job JSON as well as the checkpoint, so the UI keeps polling one source of truth.
- UI translations use i18next with English source strings as keys (`web/src/i18n`), namespaces per app area and a `common` fallback; `npm run i18n:check` (scripts/check-i18n.mjs) verifies every key exists in every locale and that placeholders match.

## Abstraction layers

- `TranscriptionProvider`, `SpeechProvider` protocols and the `generate_show_notes` function isolate vendors. Adding a provider means one class and one entry in `build_provider`.
- `JobStore` is the only code that builds file-system paths. Everything is keyed by UUID.
- `SettingsStore` persists provider configuration and keys; the API only ever returns `masked()` views and `merge_keys` keeps secrets when the client sends the mask back.
- The React client talks to the API only through `src/api/client.ts`, with types in `src/api/types.ts` mirroring the Pydantic schemas.

## Security

- No shell interpolation: every FFmpeg call is an argv list. Filenames are sanitised, extension allow-listed, and never used for paths.
- Uploads: size limit enforced while streaming, magic-byte sniff before FFprobe, duration limit, empty-file rejection.
- Output downloads are served only for names recorded in the job's `outputs` list; path segments are rejected.
- CORS restricted to the Vite origin; security headers (`nosniff`, `DENY` framing, `no-referrer`, `no-store`).
- Provider keys live server-side only; environment variables are supported as a fallback.
- Pydantic bounds on every input (lengths, ranges, list sizes).
- Generic 500 handler so stack traces never reach the client.

For a multi-user deployment add authentication, per-workspace authorisation on every job route, object storage with signed URLs, a durable queue instead of the in-process pool, rate limiting, and antivirus scanning of uploads.

## Code size rule

Every source file is under 500 lines (largest: `pipeline.py` at ~235 lines, `JobPage.tsx` at ~215 lines). Checked by `scripts/test.*` via a simple `wc -l`.

## Directory layout

```
backend/app/config.py          settings models + store
backend/app/schemas.py         Pydantic API models
backend/app/storage.py         JobStore, safe_asset_name
backend/app/routers/           jobs.py, settings.py
backend/app/services/          audio, transcription, analysis, llm, speech, publish, pipeline, verification
backend/app/rag/               schemas, store, parsing, index (Chroma), claims, online (Wikipedia), verify, ingest
backend/app/routers/           jobs.py, settings.py, libraries.py, projects.py
backend/tests/                 unit + API integration tests (pytest)
web/src/api/                   client + types
web/src/lib/                   pure helpers (tested)
web/src/components/            UploadPanel, AudioPlayer, TranscriptEditor, ProposalPanel, OutputsPanel, StageBadge
web/src/pages/                 LibraryPage, JobPage, SettingsPage
web/e2e/                       Playwright workflow tests
docs/                          this folder
scripts/                       install / start / stop / test for Windows and POSIX
```
