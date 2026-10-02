from app.schemas import ProcessingJob, QualityReport, ShowNotes, TranscriptSegment, Word
from app.services import publish
from app.services.speech import chunk_text


def seg(idx: int, start: int, end: int, text: str) -> TranscriptSegment:
    return TranscriptSegment(id=idx, start_ms=start, end_ms=end, text=text, words=[Word(text=text, start_ms=start, end_ms=end)])


def test_retime_segments_shifts_after_cut():
    keep = [(0, 1000), (3000, 5000)]
    segments = [seg(0, 0, 900, "a"), seg(1, 3500, 4500, "b")]
    out = publish.retime_segments(segments, keep)
    assert (out[0].start_ms, out[0].end_ms) == (0, 900)
    assert (out[1].start_ms, out[1].end_ms) == (1500, 2500)


def test_srt_vtt_and_chapters_format(tmp_path):
    segments = [seg(0, 0, 1500, "Hello"), seg(1, 61_000, 62_250, "World")]
    publish.write_srt(tmp_path / "a.srt", segments)
    publish.write_vtt(tmp_path / "a.vtt", segments)
    publish.write_chapters(tmp_path / "c.txt", [{"start_ms": 0, "title": "Intro"}, {"start_ms": 3_661_000, "title": "Late"}])
    assert "00:00:00,000 --> 00:00:01,500\nHello" in (tmp_path / "a.srt").read_text()
    assert (tmp_path / "a.vtt").read_text().startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500")
    assert (tmp_path / "c.txt").read_text() == "00:00 Intro\n01:01:01 Late\n"


def test_show_notes_and_metadata_are_written(tmp_path):
    job = ProcessingJob(asset_name="x.wav", show_notes=ShowNotes(title="T & Co", summary="S", chapters=[{"start_ms": 0, "title": "A"}], keywords=["k"]), quality=QualityReport(final_duration_ms=65_000))
    publish.write_show_notes(tmp_path / "n.md", job)
    publish.write_metadata(tmp_path / "m.json", job)
    publish.write_rss_item(tmp_path / "r.xml", job, "x.mp3")
    assert (tmp_path / "n.md").read_text().startswith("# T & Co")
    assert '"duration_seconds": 65.0' in (tmp_path / "m.json").read_text()
    assert "<title>T &amp; Co</title>" in (tmp_path / "r.xml").read_text()


def test_slug_and_chunking():
    assert publish.slug("  Hello, World! Episode #1 ") == "hello-world-episode-1"
    assert publish.slug("***") == "episode"
    chunks = chunk_text("One. Two. Three.", limit=12)
    assert chunks == ["One. Two.", "Three."]
