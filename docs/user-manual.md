# AiPodcaster User Manual

AiPodcaster turns a raw voice recording into a publish-ready podcast episode. It transcribes the audio, finds profanity, filler words, stutters and long pauses, lets you review and edit every suggestion, and then renders a mastered episode together with the files you need to publish it.

Nothing is ever cut without your approval, and the original recording is never modified.

## 1. Requirements

| Component | Version | Notes |
| --- | --- | --- |
| Node.js | 22.12 or newer | https://nodejs.org |
| Python | 3.12 or newer | https://python.org |
| FFmpeg + FFprobe | 6 or newer | https://ffmpeg.org/download.html, must be on `PATH` |
| GPU (optional) | NVIDIA with CUDA | Speeds up local transcription 5-10x |

Local transcription uses faster-whisper. The first run downloads the selected Whisper model (about 500 MB for `small`). If you prefer not to run a model locally, configure the OpenAI transcription provider in Settings instead.

## 2. Install and start

Windows (PowerShell):

```powershell
.\scripts\install.ps1
.\scripts\start.ps1
```

macOS / Linux:

```bash
chmod +x scripts/*.sh
./scripts/install.sh
./scripts/start.sh
```

Then open http://localhost:5173. The API documentation is at http://127.0.0.1:8000/docs. Stop everything with `scripts\stop.ps1` or `./scripts/stop.sh`.

## 3. Configure AI services (Settings page)

Open **Settings** in the top navigation.

- **Service status** shows which providers are usable right now (FFmpeg, local Whisper, GPU, and any API keys you have saved).
- **Transcription**: choose *Local Whisper* (private, free) or *OpenAI transcription API*. Pick a model size; `small` is a good default, `large-v3` is the most accurate. Optionally force a language code such as `en`.
- **Cleanup rules**: turn each detector on or off, set how long a pause must be before it is tightened and what it is shortened to, add your own banned words or filler words, and choose the target loudness (-16 LUFS is the usual podcast target).
- **Show notes & chapters**: the built-in heuristics work offline. Choose OpenAI or Anthropic to get a written summary, better chapter titles and keywords.
- **Synthetic voice**: optional. If you enable OpenAI or ElevenLabs text-to-speech, you can produce an episode where the approved transcript is read by a synthetic voice instead of cutting your recording.
- **API keys** are stored only on the server in `data/settings.json`. The browser only ever receives a mask. Leave a field untouched to keep a key; clear it to delete the key.

Click **Save settings**. New uploads use the new settings immediately; existing episodes can be re-analysed from their page.

## 4. Upload a recording

On the **Episodes** page drop a file onto the upload area or click it to browse. Supported formats: WAV, MP3, M4A, AAC, FLAC, OGG, OPUS, WEBM, MP4, MOV, WMA, AIFF. The default limit is 500 MB and 4 hours.

The episode page opens automatically and shows progress through *Preparing audio → Transcribing → Analysing*. You can leave the page; processing continues on the server.

## 5. Review and edit

When analysis finishes the page shows:

- **Player and timeline**. Coloured markers show every proposed cut (red profanity, orange filler, purple repeat, blue pause). Click a marker to hear it with a second of context on each side.
- **Transcript**. Flagged words are underlined and coloured. Click a word to toggle it between *remove* (struck through) and *keep*. Click a timestamp to jump the player there. Double-click a sentence, or press **Edit**, to change the text itself. Edited text is saved immediately and will be used for captions, show notes and the synthetic voice.
- **Suggested edits**. A checklist of every proposal with its reason and confidence. Use **All / None** per category to accept or reject a whole group. The counters show how much time will be removed.

Light fillers such as "like" or "you know" are suggested but not pre-selected because they are often part of normal speech.

## 6. Approve and produce

In the **Approve & produce** panel:

1. Set the episode title.
2. Choose the voice: **Original voice** cuts the accepted edits from your recording and masters it. **Synthetic voice** reads the approved transcript using the configured speech provider.
3. Click **Approve transcript & produce episode**.

Rendering typically takes a few seconds per minute of audio. If you change your mind, adjust the edits and press **Re-render with these choices**. **Re-run analysis** repeats transcription and detection with the current settings.

## 7. Download the publish kit

When the stage reads **Complete** the page shows a preview player, the quality report (final length, time removed, integrated loudness, true peak) and the download list:

| File | Purpose |
| --- | --- |
| `episode.mp3` | Delivery file, 128 kbps with ID3 title |
| `episode-master.wav` | Mastered lossless master for archiving or re-encoding |
| `episode-transcript.txt` | Readable transcript with timestamps |
| `episode.srt`, `episode.vtt` | Captions for YouTube, Spotify, players |
| `episode-chapters.txt` | Chapter markers in the common `HH:MM:SS Title` format |
| `episode-show-notes.md` | Title, summary, chapters, keywords, production notes |
| `episode-metadata.json` | Machine-readable episode metadata and quality report |
| `episode-edit-list.json` | Every proposal with accept/reject decision, for audit |
| `episode-rss-item.xml` | RSS `<item>` snippet to paste into your feed |
| `episode-publish-kit.zip` | All of the above in one archive |

## 8. Troubleshooting

- **HTTP 404 at http://localhost:5173**: another program (often a Vite dev server from a different project) owns the IPv6 side of port 5173. The start script now refuses to start and names the offending process; stop it (`Stop-Process -Id <pid>` or `kill <pid>`) and run the start script again.
- **"API offline" in the header**: the backend is not running. Run the start script and check `.run/api.error.log`.
- **"FFmpeg is not installed"**: install FFmpeg and make sure `ffmpeg` and `ffprobe` are on `PATH`, then restart.
- **Transcription is slow**: pick a smaller model, or install a CUDA build of PyTorch/CTranslate2 to use the GPU, or switch to the OpenAI provider.
- **"No speech was detected"**: the file may be silent, the wrong channel, or in a language you forced incorrectly. Clear the language field and re-run analysis.
- **Synthetic voice fails**: confirm a speech provider and its API key are set in Settings.
- **Delete an episode**: use **Delete** on the Episodes page. This removes the uploaded file and all outputs from `data/jobs/`.

## 9. Privacy

All audio stays on your machine unless you choose a cloud provider. With local Whisper and the heuristic show notes, no data leaves the computer. When you enable OpenAI, Anthropic or ElevenLabs, the transcript audio or text is sent to that provider under its terms.

## 10. Fact checking with knowledge libraries (RAG)

AiPodcaster can verify what is said in an episode against your own reference material and, optionally, against Wikipedia.

### 10.1 Build a library

1. Open **Libraries** and create a library (for example "Habits research").
2. Add documents: PDF, Word (.docx), EPUB, Markdown, plain text, HTML, CSV or JSON. You can select many files at once. You can also paste the URL of a web page or online PDF.
3. Each document is parsed, split into overlapping passages and embedded into a local vector database (ChromaDB with the MiniLM model). Status moves from *queued* to *indexing* to *ready*. Failed documents show the reason (for example a scanned PDF without text) and can be retried.
4. Use **Test a search** to confirm the library answers the kind of questions your episodes raise.

Embeddings run locally by default. In **Settings, Fact checking** you can switch new libraries to OpenAI embeddings.

### 10.2 Organise with projects

A **project** represents a podcast or series. In **Projects** create one and tick the libraries it should use. A project can also inherit the libraries of other projects, so a spin-off show can reuse the main show's research without copying it.

When uploading a recording choose the project in the **Project for new uploads** selector. You can change an episode's project later from the Fact check panel on its page.

### 10.3 Run a fact check

On the episode page, after transcription:

1. In the **Fact check** card choose the sources: *project libraries* and/or *Wikipedia (online)*.
2. Click **Run fact check**. The system extracts checkable statements (numbers, dates, names, assertions), retrieves the most relevant passages from each source and judges every claim.
3. Results are sorted with problems first. Each item shows the verdict (*Supported*, *Contradicted*, *No evidence*, *Uncertain*), a confidence, an explanation, the evidence passages with their source (and a link for web sources), and a suggested correction when a language model is configured.
4. Flagged statements are also marked with a red flag beside the transcript passage. Click the timestamp to listen, fix the text with **Edit**, or **Dismiss** the flag if it is a false alarm.
5. The report is included in the publish kit as `episode-fact-check.md`.

### 10.4 How verdicts are produced

- With a language model configured under **Settings, Show notes & chapters** (OpenAI or Anthropic), the model extracts claims and judges each one strictly against the retrieved evidence.
- Without a language model a transparent heuristic is used: it compares numbers and units (days, metres, years, percent, ...) and keywords between the claim and the evidence. It only flags a claim as contradicted when the same topic is discussed with different figures, and it never claims certainty beyond that. The panel tells you which mode produced the report.

Online checks query the public Wikipedia API only; nothing else is sent anywhere unless you enabled a cloud provider.

## 11. AI providers: cloud, local Ollama, voice cloning

Open **Settings**. The **Language model** card lists every supported backend:

| Provider | Needs | Notes |
| --- | --- | --- |
| Ollama (local) | Ollama installed | Fully private. AiPodcaster manages the model for you (see below). |
| Anthropic Claude | API key | Default model `claude-sonnet-5-5`. |
| OpenAI (ChatGPT models) | API key | Default `gpt-4o-mini`; the same key also enables OpenAI transcription and TTS. |
| Google Gemini | API key | Default `gemini-2.5-flash`. |
| OpenAI-compatible server | Base URL + model | LM Studio, vLLM, Groq, OpenRouter, Mistral, DeepSeek and others. |

Choose a provider, enter the model (or leave the default), save, then press **Test connection**. The badge shows the model, latency and whether it returned valid JSON. The selected model is used for show notes, chapters, claim extraction and fact-check verdicts.

### 11.1 Ollama auto-setup

When you select *Ollama* an **Ollama** card appears:

- It shows whether the server is running, the memory budget (GPU memory if present, otherwise half of RAM) and every installed chat model with a *fit score* for our workload (strict JSON, summarising, judging claims). Embedding and vision-only models are hidden.
- **Prepare best model & use it** starts the server if needed, picks the best model that fits your memory budget (installed models are preferred unless a downloadable one is clearly better; candidates include Qwen 3, Gemma 3, Llama 3.1 and Mistral Nemo), downloads it if missing with a progress bar, loads it into memory and saves it as the language model.
- **Use** next to an installed model selects that model instead.

Model downloads continue in the background; the card polls the progress. The same actions are available to agents through the MCP tools `ollama_status` and `ollama_setup`.

### 11.2 Synthetic voice and voice cloning

The **Synthetic voice & voice cloning** card supports OpenAI TTS, ElevenLabs, Descript Overdub and any custom HTTP endpoint.

- **ElevenLabs**: on an episode page press **Clone my voice from this recording**. The cleaned recording is uploaded as a sample, an instant voice clone is created and its voice id becomes the default synthetic voice. Produce the episode with *Synthetic voice* to have your own cloned voice read the approved transcript.
- **Descript**: requires Descript API access. Enter the base URL Descript provides, your Overdub voice id and the API key.
- **Custom HTTP endpoint**: give the URL, a JSON body template with `{text}`, `{voice}`, `{model}` placeholders and an auth header template. The endpoint must return audio bytes (MP3 or WAV). This covers Play.ht, Resemble, Cartesia, local XTTS servers and similar services.

Always disclose synthetic or cloned voices to listeners and only clone voices you have the right to use.

## 12. API keys and the MCP server

### 12.1 REST API

The complete API is documented at http://127.0.0.1:8000/docs. In **Settings, API & MCP access** press **Generate key**. The key is shown once. From then on external clients must send it:

```
X-API-Key: apk_...      (or Authorization: Bearer apk_...)
```

The browser UI on the configured origin keeps working without a key unless you tick *Also require a key for this web UI*; in that case paste the key into *Key used by this browser*. Keys can be revoked at any time. Keys can also be supplied with the `AIPODCASTER_API_KEYS` environment variable (comma separated).

### 12.2 MCP server

AiPodcaster ships a Model Context Protocol server so MCP-capable assistants and IDE agents can operate the app: upload recordings, read transcripts, approve and render, run fact checks, manage libraries and projects, and set up Ollama.

1. Start the app (`scripts\start.ps1` or `./scripts/start.sh`) and generate an API key.
2. Run the server over stdio for desktop clients:

```powershell
$env:AIPODCASTER_API_KEY = "apk_..."
.\scripts\mcp.ps1               # stdio
.\scripts\mcp.ps1 -Http -Port 8765   # streamable HTTP for remote agents
.\scripts\mcp.ps1 -PrintConfig       # prints a Claude Desktop config snippet
```

3. Add the printed snippet to your assistant's MCP server configuration. The Settings page also shows the snippet.

Available tools: `status`, `list_jobs`, `get_job`, `upload_recording`, `edit_transcript`, `approve_and_render`, `run_fact_check`, `get_fact_check`, `list_outputs`, `download_output`, `list_libraries`, `create_library`, `add_documents`, `add_url`, `search_library`, `list_projects`, `create_project`, `get_providers`, `ollama_status`, `ollama_setup`, `test_language_model`.

## 12a. Large files, video and links

**Video files** (MP4, MOV, WEBM) are accepted everywhere a recording is: the audio track is extracted automatically and the video itself is kept untouched as the source.

**Large files.** The browser upload limit defaults to 8 GB (`AIPODCASTER_MAX_UPLOAD_MB`) and recordings up to 10 hours (`AIPODCASTER_MAX_DURATION_MIN`). For multi-gigabyte videos use **Episodes → Link or large file → Large file already on this computer** and paste the absolute path (for example `D:\Recordings\episode-14.mp4`). The server reads the file directly from disk, so nothing passes through the browser. Set `AIPODCASTER_ALLOW_LOCAL_IMPORT=0` to disable this on shared installations.

**Links.** On the same tab paste a URL to YouTube, Vimeo, SoundCloud, a podcast page or a direct MP3/MP4 link. AiPodcaster resolves the title and author, downloads only the audio stream where available (with progress shown on the episode page), and then runs the normal pipeline. The episode keeps a “source link” next to its details. Only publicly reachable http(s) links are accepted; links to private or local addresses are refused. Respect the rights of the content you import.

## 13. Episodes from text, transcripts and documents

You do not need a recording. On the Episodes page choose the **Transcript / text** tab and either drop a file (TXT, Markdown, SRT, VTT, PDF, Word, HTML, EPUB) or paste text. AiPodcaster detects the format automatically:

| Detected as | Example | Timing |
| --- | --- | --- |
| SRT / WebVTT captions | `00:00:01,000 --> 00:00:04,000` | taken from the captions |
| Timestamped transcript | `[00:12] HOST: Today we…` | taken from the timestamps |
| Speaker dialogue | `HOST: … / GUEST: …` | estimated from the speaking pace |
| Plain text / script | paragraphs | estimated from the speaking pace |

Set the **speaking pace** (words per minute) for text without timestamps. The episode opens in the normal review workspace: fillers, repeats and profanity are flagged, the text is editable, fact checking works, and the statistics page is available. Because there is no original audio, the voice is always **synthetic**: configure a speech provider (Settings → Synthetic voice) and press *Approve & produce* to render the MP3 and publish kit. Speaker labels are kept for review but are not read aloud.

## 14. Managing the episode library

The Episodes page is the library of all podcasts:

- **Search** by name, file, tag or language; **filter** by status (needs review, produced, failed), source (audio or text), project, fact-check flags and archived state.
- **Sort** by manual order, recently updated, newest, name, length or word count. In manual order, drag rows or use the arrows to reorder; the order is saved.
- **Group by project** to see each show separately.
- **Rename** inline with the pencil icon; change the project from the dropdown in the row.
- **Select** several episodes for bulk **Archive**, **Unarchive**, **Download kits** or **Delete**. Archived episodes are hidden unless *Show archived* is on.
- Every row links to **Open** (edit and review), **Stats** and **Publish**.

## 15. Statistics page

Each episode has a **Statistics** tab with the full quality picture: original and final length, words spoken and kept, speaking pace, vocabulary richness, fillers per 100 words, accepted and rejected edits, text edits, long pauses, fact-check flags, loudness and true peak, outputs and publishes. Charts show speaking pace per minute, where edits cluster, suggestions by type with confidence, time removed per minute, the most used words, filler and flagged words, sentence-length and pause-length distributions, fact-check verdicts and segments per speaker. Hover any chart for exact values.

## 16. Publish & export

The **Publish & export** tab prepares everything a hosting service or social network needs.

1. **Generate with AI** writes a title, subtitle, short and long descriptions, hashtags, keywords, social posts for X, LinkedIn, Instagram and Threads, a YouTube description with chapters, and an artwork prompt. It uses the configured language model, or built-in templates offline. Edit anything and **Save copy**. Season, episode number, category and the explicit flag live here too.
2. **Episode artwork**: generate a square (1400×1400) or 16:9 (1280×720) cover from the prompt. With *Settings → Episode artwork* set to OpenAI an AI image is created; otherwise a clean title cover is rendered locally. You can also upload your own PNG/JPEG.
3. **Publish to** lists the services connected under *Settings → Publishing services*:
   - **Own website / webhook**: pushes MP3, artwork and a JSON manifest to a URL you control. A ready-made PHP receiver and the contract are in `docs/website-connector/`.
   - **WordPress**: uploads media and creates a post (draft by default) with player, show notes and chapters via the REST API and an application password.
   - **Buzzsprout** and **Transistor.fm**: create the episode through their APIs.
   - **Spotify for Creators, Apple Podcasts, YouTube, generic RSS hosts**: these have no upload API, so *Prepare* builds the package and shows a checklist.
4. **Download publish package** gives a zip with the audio, artwork, manifest, descriptions, hashtags and one text file per social network for manual uploads.
5. **Publishing history** records every attempt with status, message and link.

## 17. Themes

Use the **Theme** button in the header to choose light, dark or system mode and one of six accent palettes (Studio blue, Violet, Teal, Sunset, Forest, Monochrome). The choice is stored in the browser.
