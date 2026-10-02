# Testing strategy

Run everything with `scripts\test.ps1` (Windows) or `./scripts/test.sh` (POSIX). Add `-E2E` / `--e2e` for browser tests and `-Mutation` / `--mutation` for mutation testing.

| Layer | Tool | Location | What it covers |
| --- | --- | --- | --- |
| Lint (Python) | ruff (`E F I B UP S`) | `backend/pyproject.toml` | Style, import order, bug-prone patterns, security rules (bandit subset) |
| Lint (TypeScript) | ESLint 9 flat config, typescript-eslint, react-hooks, react-refresh | `web/eslint.config.js` | Type-aware lint, hook rules |
| Type check | `tsc -b` strict, `noUnchecked*` | `web/tsconfig.app.json` | Whole client |
| Unit (Python) | pytest | `backend/tests/test_analysis.py`, `test_publish.py` | Detectors, keep-range inversion, text re-flow, SRT/VTT/chapters formatting, slug, TTS chunking |
| Integration (API) | pytest + FastAPI TestClient + real FFmpeg | `backend/tests/test_api.py` | Upload validation, full pipeline with the deterministic `fake` transcriber, transcript editing, approval, render, downloads, path traversal rejection, settings masking, security headers |
| Unit (RAG) | pytest | `backend/tests/test_rag_units.py` | Chunking, HTML/Markdown/DOCX extraction, claim scoring, figure comparison, heuristic verdicts |
| Integration (RAG) | pytest + real ChromaDB + local embeddings | `backend/tests/test_rag_api.py` | Library CRUD, multi-file upload and indexing, semantic search, project linking and inheritance, full fact check that flags a contradicted figure, dismissals, fact-check report in the publish kit |
| Unit (providers) | pytest + monkeypatched httpx | `backend/tests/test_providers.py` | LLM dispatch for every backend, OpenAI-compatible validation, error mapping, Ollama recommendation and setup (select / pull / persist), provider catalog, speech registry and custom template, API-key middleware, MCP tool registration |
| Integration (episodes) | pytest | `backend/tests/test_episodes.py` | Format detection for SRT/VTT/timestamped/dialogue/prose, text episodes from paste and upload, metadata, search, archive, reorder, bulk delete, render guard for text jobs, statistics endpoint |
| Integration (publishing) | pytest + monkeypatched httpx | `backend/tests/test_publishing.py` | Kit generation and editing, thumbnail generation (size check) and upload validation, package zip, target CRUD with secret masking, webhook publish success/failure, manual targets, WordPress connector payload |
| Integration (imports) | pytest + monkeypatched yt-dlp | `backend/tests/test_remote_media.py` | URL validation (private hosts refused), local-path import without upload, link import with download progress and failure reporting |
| Unit (web) | Vitest + Testing Library + jsdom | `web/src/**/*.test.ts(x)` | Pure helpers, proposal panel interactions, routing, API status |
| End-to-end | Playwright (Chromium) | `web/e2e/workflow.spec.ts`, `web/e2e/factcheck.spec.ts`, `web/e2e/providers.spec.ts`, `web/e2e/episodes.spec.ts` | Boots real API (fake transcriber) and Vite; uploads a generated WAV, rejects an edit, edits text, approves, downloads MP3, settings round-trip |
| Mutation | mutmut | `backend/pyproject.toml` | Restricted to deterministic modules `analysis.py` and `publish.py` |
| Coverage | pytest-cov, vitest v8 | – | Printed by the test scripts |

## End-to-end ports

Playwright boots its own API on port 8010 and its own Vite server on 5174 (see `web/playwright.config.ts`), so browser tests can run while the development stack on 8000/5173 is up. Each run starts from an empty `backend/tests/.e2e-data` directory.

## Deterministic transcriber

Setting `AIPODCASTER_TRANSCRIBER=fake` swaps the ASR provider for a scripted transcript containing a filler, a stutter and a profanity. This keeps CI free of model downloads and GPUs while still exercising FFmpeg, silence detection, cutting, mastering and the publish kit on real audio generated with `aevalsrc`.

## Manual verification

- Real speech sample (Windows SAPI generated) transcribed with faster-whisper `small` on CUDA in ~4 s; detections: filler "Um", repeat "we", profanity "Damn", phrase "you know" (suggested, not pre-accepted); render removed 1.0 s, output -17.2 LUFS / -1.5 dBTP, 11 output files.
- UI reviewed at desktop and phone widths: review layout collapses to one column below 960 px, long file names truncate with ellipsis, tables scroll horizontally.

## Manual verification (providers)

- Real Ollama 0.34 on a 24 GB GPU: status reported running, recommended the installed `gemma3:12b` (fit score 88) over downloading, warm-up 14.5 s, JSON round trip 8.5 s.
- MCP server started over streamable HTTP and answered an `initialize` request; `--print-config` produced a Claude Desktop snippet.

## Current results

```
backend: ruff clean, 55 tests passed
web:     eslint clean, tsc clean, 28 unit tests passed, 6 e2e tests passed
```
