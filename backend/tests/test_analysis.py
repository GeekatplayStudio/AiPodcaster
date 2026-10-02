from app.config import CleanupSettings
from app.schemas import EditKind, EditProposal, TranscriptSegment, Word
from app.services import analysis
from app.services.transcription import FakeTranscriptionProvider


def words(*tokens: str) -> list[Word]:
    out, cursor = [], 0
    for token in tokens:
        out.append(Word(text=token, start_ms=cursor, end_ms=cursor + 300))
        cursor += 400
    return out


def segment(ws: list[Word]) -> TranscriptSegment:
    return TranscriptSegment(id=0, start_ms=ws[0].start_ms, end_ms=ws[-1].end_ms, text=" ".join(w.text for w in ws), words=ws)


def test_profanity_detection_handles_punctuation_and_extra_words():
    found = analysis.find_profanity(words("Well,", "damn!", "that", "Frick"), ["frick"])
    assert [p.text for p in found] == ["damn!", "Frick"]
    assert all(p.kind == EditKind.PROFANITY for p in found)


def test_filler_words_and_phrases():
    found = analysis.find_fillers(words("Um,", "you", "know,", "it", "is", "like", "fine"), [])
    kinds = {(p.text, p.accepted) for p in found}
    assert ("Um,", True) in kinds
    assert ("you know,", False) in kinds
    assert ("like", False) in kinds  # light filler is suggested but not pre-accepted


def test_repeat_detection_finds_phrase_and_word_repeats():
    found = analysis.find_repeats(words("I", "think,", "I", "think", "the", "the", "point"))
    assert [p.text for p in found] == ["I think,", "the"]
    assert found[0].reason == "Repeated phrase"


def test_long_pause_keeps_breathing_room():
    config = CleanupSettings(max_pause_ms=1500, keep_pause_ms=400)
    ws = words("hello", "world")
    ws[1].start_ms, ws[1].end_ms = 5000, 5300
    found = analysis.find_long_pauses([(300, 5000)], ws, config, 6000)
    assert len(found) == 1
    cut = found[0]
    assert cut.start_ms == 500 and cut.end_ms == 4800
    assert (5000 - 300) - (cut.end_ms - cut.start_ms) == 400


def test_leading_and_trailing_silence_are_trimmed():
    config = CleanupSettings(max_pause_ms=1000, keep_pause_ms=300)
    ws = words("hi")
    ws[0].start_ms, ws[0].end_ms = 3000, 3300
    found = analysis.find_long_pauses([(0, 3000), (3300, 9000)], ws, config, 9000)
    reasons = [p.reason for p in found]
    assert reasons == ["Leading silence", "Trailing silence"]
    assert found[0].end_ms == 2700 and found[1].start_ms == 3600


def test_keep_ranges_inverts_and_merges_cuts():
    assert analysis.keep_ranges(10_000, [(1000, 2000), (1500, 2500), (9990, 20_000)]) == [(0, 1000), (2500, 9990)]
    assert analysis.keep_ranges(1000, []) == [(0, 1000)]


def test_apply_cuts_to_text_removes_accepted_words_only():
    ws = words("um", "hello", "damn", "world")
    seg = segment(ws)
    proposals = [
        EditProposal(kind=EditKind.FILLER, start_ms=0, end_ms=300, text="um", reason="f", confidence=1, accepted=True),
        EditProposal(kind=EditKind.PROFANITY, start_ms=800, end_ms=1100, text="damn", reason="p", confidence=1, accepted=False),
    ]
    result = analysis.apply_cuts_to_text([seg], proposals)
    assert result[0].text == "hello damn world"


def test_build_proposals_on_fake_transcript_dedupes_and_sorts():
    result = FakeTranscriptionProvider().transcribe(None)  # type: ignore[arg-type]
    proposals = analysis.build_proposals(result.segments, [], CleanupSettings(), 60_000)
    kinds = [p.kind for p in proposals]
    assert EditKind.PROFANITY in kinds and EditKind.FILLER in kinds and EditKind.REPEAT in kinds
    assert proposals == sorted(proposals, key=lambda p: (p.start_ms, -p.end_ms))
