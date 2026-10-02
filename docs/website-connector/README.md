# Website connector

AiPodcaster can push finished episodes to any website you control. The contract is deliberately small so it can be implemented in PHP, Node, Python, a serverless function or a CMS plugin.

## Request

`POST <your receiver URL>` as `multipart/form-data` with headers:

| Header | Value |
| --- | --- |
| `X-AiPodcaster-Secret` | the shared secret configured for the target |
| `X-AiPodcaster-Event` | `episode.publish` |

Parts:

| Part | Type | Content |
| --- | --- | --- |
| `manifest` | `application/json` | episode metadata (below) |
| `audio` | `audio/mpeg` | the produced MP3 (present when the episode was produced) |
| `thumbnail` | `image/png` | artwork, when one exists |

Manifest fields: `episode_id`, `title`, `subtitle`, `description`, `short_description`, `hashtags[]`, `keywords[]`, `chapters[{start_ms,title}]`, `duration_seconds`, `language`, `explicit`, `episode_number`, `season_number`, `category`, `transcript[{start_ms,text}]`, `outputs[{name,label,url}]`, `generator`.

## Response

Return HTTP 200 with JSON. `message` is shown in AiPodcaster's publishing history; `url` becomes the "Open" link.

```json
{ "message": "Episode stored", "url": "https://example.com/podcast/my-episode" }
```

Any 4xx/5xx marks the publish as failed and shows the response body.

## Reference receiver

`receiver.php` is a complete implementation for shared hosting: it validates the secret, stores the MP3, artwork and manifest under `/podcast`, and maintains `episodes.json` that a page or theme can render. Replace `saveEpisode()` with your CMS logic (for WordPress use the dedicated WordPress target instead, which creates posts through the REST API).

Security notes: keep the secret long and random, serve the receiver over HTTPS, limit upload size in your web server config, and do not expose `episodes.json` if it should stay private.
