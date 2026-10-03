"""Turn a word-level transcript into reviewable edit proposals.

Every proposal is explicit, time-stamped, explained and reversible. Nothing is
cut until the user approves.
"""
from __future__ import annotations

from ..config import CleanupSettings
from ..schemas import EditKind, EditProposal, TranscriptSegment, Word
from . import languages

DEFAULT_BAD_WORDS = languages.PROFANITY["en"]
DEFAULT_FILLERS = set(languages.strong_fillers("en")) | set(languages.light_fillers("en"))
LIGHT_FILLERS = set(languages.light_fillers("en"))
FILLER_PHRASES = tuple(languages.FILLER_PHRASES["en"])


def normalise(token: str) -> str:
    return languages.normalise(token)


def _flat_words(segments: list[TranscriptSegment]) -> list[Word]:
    return [word for segment in segments for word in segment.words]


def find_profanity(words: list[Word], extra: list[str], language: str | None = None) -> list[EditProposal]:
    bad = languages.profanity_words(language) | {normalise(item) for item in extra if normalise(item)}
    prefixes = [item for item in bad if len(item) >= 4]
    proposals: list[EditProposal] = []
    for word in words:
        core = normalise(word.text)
        if not core:
            continue
        hit = core in bad or any(core.startswith(item) and len(core) - len(item) <= 3 for item in prefixes) or languages.is_profane_stem(core, language)
        if hit:
            proposals.append(EditProposal(kind=EditKind.PROFANITY, start_ms=word.start_ms, end_ms=max(word.end_ms, word.start_ms + 1), text=word.text, reason="Profanity", confidence=0.95))
    return proposals


def find_fillers(words: list[Word], extra: list[str], language: str | None = None) -> list[EditProposal]:
    strong = set(languages.strong_fillers(language)) | {normalise(item) for item in extra if normalise(item)}
    light = set(languages.light_fillers(language)) - strong
    phrases = languages.filler_phrases(language)
    proposals: list[EditProposal] = []

    def add(start: Word, end: Word, text: str, reason: str, confidence: float, accepted: bool) -> None:
        proposals.append(EditProposal(kind=EditKind.FILLER, start_ms=start.start_ms, end_ms=max(end.end_ms, start.start_ms + 1), text=text, reason=reason, confidence=confidence, accepted=accepted))

    index = 0
    while index < len(words):
        word = words[index]
        core = normalise(word.text)
        if index + 2 < len(words):
            triple = f"{core} {normalise(words[index + 1].text)} {normalise(words[index + 2].text)}"
            if triple in phrases:
                add(word, words[index + 2], " ".join(w.text for w in words[index:index + 3]), "Filler phrase", 0.7, False)
                index += 3
                continue
        if index + 1 < len(words):
            pair = f"{core} {normalise(words[index + 1].text)}"
            if pair in phrases:
                add(word, words[index + 1], f"{word.text} {words[index + 1].text}", "Filler phrase", 0.7, False)
                index += 2
                continue
        stretched = languages.elongation_kind(word.text)
        if core in strong or stretched == "strong":
            add(word, word, word.text, "Hesitation sound" if stretched else "Verbal filler", 0.93 if stretched else 0.92, True)
        elif core in light or stretched == "light":
            add(word, word, word.text, "Drawn-out filler word" if stretched else "Possible filler (context dependent)", 0.75 if stretched else 0.6, bool(stretched))
        index += 1
    return proposals


def find_repeats(words: list[Word], max_ngram: int = 4) -> list[EditProposal]:
    """Detect immediate repetitions such as "I think, I think" or stutters."""
    proposals: list[EditProposal] = []
    cores = [normalise(word.text) for word in words]
    index = 0
    while index < len(words):
        matched = 0
        for size in range(max_ngram, 0, -1):
            if index + 2 * size <= len(words) and cores[index:index + size] == cores[index + size:index + 2 * size] and all(cores[index:index + size]):
                matched = size
                break
        if matched:
            first, last = words[index], words[index + matched - 1]
            phrase = " ".join(word.text for word in words[index:index + matched])
            proposals.append(EditProposal(kind=EditKind.REPEAT, start_ms=first.start_ms, end_ms=max(last.end_ms, first.start_ms + 1), text=phrase, reason="Repeated phrase" if matched > 1 else "Repeated word", confidence=0.9 if matched > 1 else 0.8))
            index += matched
        else:
            index += 1
    return proposals


def find_long_pauses(silences: list[tuple[int, int]], words: list[Word], config: CleanupSettings, duration_ms: int) -> list[EditProposal]:
    proposals: list[EditProposal] = []
    first_word = words[0].start_ms if words else 0
    last_word = words[-1].end_ms if words else duration_ms
    for start, end in silences:
        length = end - start
        if length < config.max_pause_ms:
            continue
        if end <= first_word + 50:  # leading silence: keep only a short lead-in
            cut_start, cut_end, reason = start, max(start, end - config.keep_pause_ms), "Leading silence"
        elif start >= last_word - 50:
            cut_start, cut_end, reason = min(end, start + config.keep_pause_ms), end, "Trailing silence"
        else:
            keep = config.keep_pause_ms
            cut_start, cut_end, reason = start + keep // 2, end - (keep - keep // 2), f"Long pause ({length / 1000:.1f}s); keep {keep} ms"
        if cut_end - cut_start >= 200:
            proposals.append(EditProposal(kind=EditKind.SILENCE, start_ms=cut_start, end_ms=cut_end, text="", reason=reason, confidence=0.88))
    return proposals


def build_proposals(segments: list[TranscriptSegment], silences: list[tuple[int, int]], config: CleanupSettings, duration_ms: int, language: str | None = None) -> list[EditProposal]:
    words = _flat_words(segments)
    proposals: list[EditProposal] = []
    if config.remove_profanity:
        proposals += find_profanity(words, config.extra_bad_words, language)
    if config.remove_repeats:
        proposals += find_repeats(words)
    if config.remove_fillers:
        proposals += find_fillers(words, config.extra_filler_words, language)
    if config.tighten_silence:
        proposals += find_long_pauses(silences, words, config, duration_ms)
    return _dedupe(sorted(proposals, key=lambda item: (item.start_ms, -item.end_ms)))


def _dedupe(proposals: list[EditProposal]) -> list[EditProposal]:
    """Drop proposals fully contained in an earlier, wider one of higher priority."""
    priority = {EditKind.PROFANITY: 0, EditKind.REPEAT: 1, EditKind.FILLER: 2, EditKind.SILENCE: 3, EditKind.NOISE: 4}
    kept: list[EditProposal] = []
    for proposal in proposals:
        covered = any(p.start_ms <= proposal.start_ms and p.end_ms >= proposal.end_ms and priority[p.kind] <= priority[proposal.kind] and p.kind != EditKind.SILENCE for p in kept)
        if not covered:
            kept.append(proposal)
    return kept


def keep_ranges(duration_ms: int, cuts: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Invert accepted cut ranges into the ranges that survive."""
    merged: list[list[int]] = []
    for start, end in sorted(cuts):
        start, end = max(0, start), min(duration_ms, end)
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    keep: list[tuple[int, int]] = []
    cursor = 0
    for start, end in merged:
        if start - cursor >= 20:
            keep.append((cursor, start))
        cursor = end
    if duration_ms - cursor >= 20:
        keep.append((cursor, duration_ms))
    return keep


def apply_cuts_to_text(segments: list[TranscriptSegment], proposals: list[EditProposal]) -> list[TranscriptSegment]:
    """Produce the transcript as it will sound after accepted word cuts."""
    cuts = [(p.start_ms, p.end_ms) for p in proposals if p.accepted and p.kind != EditKind.SILENCE]
    result: list[TranscriptSegment] = []
    for segment in segments:
        if not segment.words:
            result.append(segment)
            continue
        kept = [w for w in segment.words if not any(start <= w.start_ms and w.end_ms <= end + 1 for start, end in cuts)]
        text = " ".join(w.text for w in kept).strip()
        result.append(segment.model_copy(update={"words": kept, "text": text}))
    return [segment for segment in result if segment.text]
