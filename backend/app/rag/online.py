"""Online evidence from trusted public sources (Wikipedia via its public API)."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import AppSettings
from .claims import keywords
from .index import cosine, embed_texts
from .parsing import chunk_text

USER_AGENT = "AiPodcasterFactCheck/1.0 (self-hosted podcast tool; https://github.com/aipodcaster/aipodcaster; mailto:factcheck@aipodcaster.local) python-httpx"


@dataclass
class OnlinePassage:
    title: str
    url: str
    text: str
    score: float


def _wikipedia_search(language: str, query: str, limit: int = 3) -> list[str]:
    import httpx

    response = httpx.get(
        f"https://{language}.wikipedia.org/w/api.php",
        params={"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json", "utf8": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    return [item["title"] for item in response.json().get("query", {}).get("search", [])]


def _wikipedia_extract(language: str, title: str, max_chars: int = 12_000) -> tuple[str, str]:
    import httpx

    response = httpx.get(
        f"https://{language}.wikipedia.org/w/api.php",
        params={"action": "query", "prop": "extracts|info", "explaintext": 1, "titles": title, "format": "json", "inprop": "url", "redirects": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    for page in pages.values():
        return str(page.get("extract", ""))[:max_chars], str(page.get("fullurl") or f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}")
    return "", ""


def wikipedia_evidence(settings: AppSettings, claim: str, limit: int = 3, language: str | None = None) -> list[OnlinePassage]:
    """Search Wikipedia for the claim, then rank passages with the local embedder."""
    configured = settings.fact_check.wikipedia_language or "auto"
    language = (language or "en").split("-")[0] if configured == "auto" else configured
    query = " ".join(keywords(claim, 6)) or claim[:100]
    try:
        titles = _wikipedia_search(language, query)
    except Exception:  # noqa: BLE001 - network problems are not fatal
        return []
    passages: list[tuple[str, str, str]] = []
    for title in titles[:2]:
        try:
            extract, url = _wikipedia_extract(language, title)
        except Exception:  # noqa: BLE001
            continue
        for chunk in chunk_text(extract, size=700, overlap=80)[:40]:
            passages.append((title, url, chunk))
    if not passages:
        return []
    vectors = embed_texts("local", settings, [claim] + [p[2] for p in passages])
    query_vector, chunk_vectors = vectors[0], vectors[1:]
    ranked = sorted(((cosine(query_vector, v), p) for v, p in zip(chunk_vectors, passages, strict=False)), key=lambda item: item[0], reverse=True)
    return [OnlinePassage(title=p[0], url=p[1], text=p[2], score=max(0.0, min(1.0, s))) for s, p in ranked[:limit]]
