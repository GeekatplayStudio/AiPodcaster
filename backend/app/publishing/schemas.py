"""Publishing targets (hosting services, websites) and their catalog."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ..schemas import utc_now

SECRET_MASK = "••••••••"


@dataclass(frozen=True)
class TargetField:
    name: str
    label: str
    secret: bool = False
    placeholder: str = ""
    required: bool = True


@dataclass(frozen=True)
class TargetKind:
    id: str
    label: str
    mode: str  # api | manual
    fields: list[TargetField] = field(default_factory=list)
    notes: str = ""
    docs_url: str = ""


CATALOG: list[TargetKind] = [
    TargetKind(
        "generic_webhook",
        "Own website / webhook",
        "api",
        [TargetField("url", "Receiver URL", placeholder="https://example.com/aipodcaster-receiver.php"), TargetField("secret", "Shared secret", secret=True, placeholder="sent as X-AiPodcaster-Secret")],
        "Pushes the MP3, thumbnail and a JSON manifest (title, description, chapters, transcript, hashtags) to your site. A drop-in PHP receiver is in docs/website-connector.",
        "docs/website-connector/README.md",
    ),
    TargetKind(
        "wordpress",
        "WordPress (REST API)",
        "api",
        [TargetField("site_url", "Site URL", placeholder="https://blog.example.com"), TargetField("username", "Username"), TargetField("app_password", "Application password", secret=True), TargetField("status", "Post status", placeholder="draft", required=False)],
        "Uploads the audio and thumbnail to the media library and creates a post with an audio player, show notes and chapters. Create an application password under Users → Profile.",
        "https://developer.wordpress.org/rest-api/",
    ),
    TargetKind(
        "buzzsprout",
        "Buzzsprout",
        "api",
        [TargetField("podcast_id", "Podcast ID"), TargetField("api_token", "API token", secret=True)],
        "Creates an episode via the Buzzsprout API with the publish kit metadata and uploads the audio.",
        "https://github.com/buzzsprout/buzzsprout-api",
    ),
    TargetKind(
        "transistor",
        "Transistor.fm",
        "api",
        [TargetField("show_id", "Show ID"), TargetField("api_key", "API key", secret=True)],
        "Creates an episode on Transistor with the audio uploaded through their authorised upload flow.",
        "https://developers.transistor.fm/",
    ),
    TargetKind("spotify_for_creators", "Spotify for Creators", "manual", [], "No public upload API. AiPodcaster prepares a package (audio, cover, description, chapters) and a checklist to paste into the dashboard.", "https://creators.spotify.com/"),
    TargetKind("apple_podcasts", "Apple Podcasts Connect", "manual", [], "Distributed through your RSS host; this target prepares Apple-formatted metadata and the 3000×3000 artwork check.", "https://podcastsconnect.apple.com/"),
    TargetKind("youtube", "YouTube", "manual", [], "Prepares the YouTube description with chapters and hashtags plus a 1280×720 thumbnail; upload the audio as a video or use a static-image video.", "https://studio.youtube.com/"),
    TargetKind("rss", "Generic RSS host", "manual", [], "Prepares an RSS <item> snippet and metadata for any host (Libsyn, Podbean, Captivate, Anchor…).", ""),
]


class PublishTarget(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(pattern="^(" + "|".join(k.id for k in CATALOG) + ")$")
    config: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_result: str = ""

    def masked(self) -> dict:
        kind = kind_by_id(self.kind)
        secrets = {f.name for f in kind.fields if f.secret} if kind else set()
        data = self.model_dump(mode="json")
        data["config"] = {k: (SECRET_MASK if k in secrets and v else v) for k, v in self.config.items()}
        return data


class PublishTargetUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str
    config: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class PublishRequest(BaseModel):
    target_id: UUID


def kind_by_id(kind_id: str) -> TargetKind | None:
    return next((k for k in CATALOG if k.id == kind_id), None)
