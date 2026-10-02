from app.rag import claims, parsing
from app.rag.verify import heuristic_judge
from app.schemas import Evidence, TranscriptSegment, Verdict


def seg(idx: int, text: str) -> TranscriptSegment:
    return TranscriptSegment(id=idx, start_ms=idx * 1000, end_ms=idx * 1000 + 900, text=text)


def test_chunking_respects_size_and_overlap():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(12))
    chunks = parsing.chunk_text(text, size=600, overlap=100)
    assert len(chunks) > 3
    assert all(len(chunk) <= 700 for chunk in chunks)
    assert "Paragraph 0." in chunks[0]
    assert "Paragraph 11." in chunks[-1]


def test_html_to_text_drops_scripts_and_keeps_paragraphs():
    html = "<html><head><style>p{}</style><script>var x=1;</script></head><body><h1>Title</h1><p>Hello <b>world</b>.</p><nav>skip</nav></body></html>"
    text = parsing.html_to_text(html)
    assert "Title" in text and "Hello world." in text
    assert "var x" not in text and "skip" not in text


def test_extract_text_rejects_unknown_types(tmp_path):
    path = tmp_path / "x.exe"
    path.write_bytes(b"MZ....")
    try:
        parsing.extract_text(path, "x.exe")
    except parsing.ParseError as error:
        assert "Unsupported" in str(error)
    else:
        raise AssertionError("expected ParseError")


def test_extract_text_reads_markdown_and_docx(tmp_path):
    md = tmp_path / "notes.md"
    md.write_text("# Facts\n\nThe Eiffel Tower is 330 metres tall and was completed in 1889.\n", "utf-8")
    assert "330 metres" in parsing.extract_text(md, "notes.md")
    import docx

    document = docx.Document()
    document.add_paragraph("Mount Everest is 8,849 metres high according to the 2020 survey.")
    path = tmp_path / "facts.docx"
    document.save(str(path))
    assert "8,849 metres" in parsing.extract_text(path, "facts.docx")


def test_heuristic_claim_extraction_prefers_factual_sentences():
    segments = [
        seg(0, "Welcome back to the show, thanks for joining us."),
        seg(1, "I think this is probably the best episode yet."),
        seg(2, "The Eiffel Tower is 330 metres tall and was completed in 1889."),
        seg(3, "Marie Curie won two Nobel Prizes in physics and chemistry."),
    ]
    found = claims.heuristic_claims(segments, limit=10)
    texts = [c.text for c in found]
    assert "The Eiffel Tower is 330 metres tall and was completed in 1889." in texts
    assert any("Marie Curie" in t for t in texts)
    assert not any("Welcome" in t or "I think" in t for t in texts)
    assert claims.numbers_in("costs 1,200 dollars in 2019") == {"1200dollars", "2019"}


def test_heuristic_judge_detects_number_mismatch_and_support():
    claim = "The Eiffel Tower is 330 metres tall and was completed in 1889."
    agree = Evidence(source_kind="library", source="Guide", excerpt="The Eiffel Tower, completed in 1889, stands 330 metres tall in Paris.", score=0.8)
    disagree = Evidence(source_kind="library", source="Guide", excerpt="The Eiffel Tower was completed in 1887 and is 300 metres tall; the tower is in Paris.", score=0.8)
    verdict, confidence, _, flagged = heuristic_judge(claim, [agree], 0.35)
    assert verdict == Verdict.SUPPORTED and not flagged and confidence > 0.5
    verdict, _, explanation, flagged = heuristic_judge(claim, [disagree], 0.35)
    assert verdict == Verdict.CONTRADICTED and flagged and "different figures" in explanation
    verdict, _, _, flagged = heuristic_judge(claim, [], 0.35)
    assert verdict == Verdict.UNSUPPORTED and not flagged
    low = Evidence(source_kind="library", source="x", excerpt="unrelated text about cooking", score=0.1)
    assert heuristic_judge(claim, [low], 0.35)[0] == Verdict.UNSUPPORTED
