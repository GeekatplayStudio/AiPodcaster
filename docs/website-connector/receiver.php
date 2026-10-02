<?php
/**
 * AiPodcaster website connector — drop-in receiver.
 *
 * Upload this file to your website (e.g. https://example.com/aipodcaster-receiver.php),
 * set $SECRET to the same value as the "Shared secret" of the "Own website / webhook"
 * target in AiPodcaster → Settings → Publishing services, and make sure the
 * $STORAGE directory is writable by the web server.
 *
 * Every publish sends a multipart POST with:
 *   manifest  (JSON) title, description, hashtags, chapters, transcript, duration…
 *   audio     (MP3)  the produced episode
 *   thumbnail (PNG)  optional artwork
 * The receiver stores the files, appends the episode to episodes.json and returns
 * {"message": "...", "url": "<public page or audio url>"}.
 * Adapt saveEpisode() to insert into your CMS instead.
 */

$SECRET  = getenv('AIPODCASTER_SECRET') ?: 'change-me';
$STORAGE = __DIR__ . '/podcast';           // files are written here
$PUBLIC  = rtrim((isset($_SERVER['HTTPS']) ? 'https' : 'http') . '://' . $_SERVER['HTTP_HOST'] . dirname($_SERVER['SCRIPT_NAME']), '/') . '/podcast';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['detail' => 'POST only']);
    exit;
}
$presented = $_SERVER['HTTP_X_AIPODCASTER_SECRET'] ?? '';
if ($SECRET === '' || !hash_equals($SECRET, $presented)) {
    http_response_code(401);
    echo json_encode(['detail' => 'Invalid secret']);
    exit;
}
if (!isset($_FILES['manifest'])) {
    http_response_code(422);
    echo json_encode(['detail' => 'manifest is required']);
    exit;
}
$manifest = json_decode(file_get_contents($_FILES['manifest']['tmp_name']), true);
if (!is_array($manifest) || empty($manifest['episode_id'])) {
    http_response_code(422);
    echo json_encode(['detail' => 'manifest is not valid JSON']);
    exit;
}

if (!is_dir($STORAGE) && !mkdir($STORAGE, 0755, true)) {
    http_response_code(500);
    echo json_encode(['detail' => 'storage directory is not writable']);
    exit;
}
$id   = preg_replace('/[^a-f0-9-]/', '', $manifest['episode_id']);
$slug = trim(preg_replace('/[^a-z0-9]+/', '-', strtolower($manifest['title'] ?? 'episode')), '-') ?: 'episode';
$base = $STORAGE . '/' . $slug . '-' . substr($id, 0, 8);

$audioUrl = null;
if (isset($_FILES['audio']) && $_FILES['audio']['error'] === UPLOAD_ERR_OK) {
    move_uploaded_file($_FILES['audio']['tmp_name'], $base . '.mp3');
    $audioUrl = $PUBLIC . '/' . basename($base) . '.mp3';
}
$imageUrl = null;
if (isset($_FILES['thumbnail']) && $_FILES['thumbnail']['error'] === UPLOAD_ERR_OK) {
    move_uploaded_file($_FILES['thumbnail']['tmp_name'], $base . '.png');
    $imageUrl = $PUBLIC . '/' . basename($base) . '.png';
}
file_put_contents($base . '.json', json_encode($manifest, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

$episode = saveEpisode($manifest, $audioUrl, $imageUrl, $STORAGE);
echo json_encode(['message' => 'Episode stored on website', 'url' => $episode['page_url'] ?? $audioUrl]);

/**
 * Replace this with your CMS logic (WordPress wp_insert_post, Laravel model, …).
 * The default keeps a simple episodes.json index that a static page can render.
 */
function saveEpisode(array $manifest, ?string $audioUrl, ?string $imageUrl, string $storage): array
{
    $indexFile = $storage . '/episodes.json';
    $index = file_exists($indexFile) ? (json_decode(file_get_contents($indexFile), true) ?: []) : [];
    $entry = [
        'episode_id'   => $manifest['episode_id'],
        'title'        => $manifest['title'] ?? '',
        'description'  => $manifest['description'] ?? '',
        'hashtags'     => $manifest['hashtags'] ?? [],
        'chapters'     => $manifest['chapters'] ?? [],
        'duration'     => $manifest['duration_seconds'] ?? null,
        'audio_url'    => $audioUrl,
        'image_url'    => $imageUrl,
        'published_at' => gmdate('c'),
    ];
    $index = array_values(array_filter($index, fn($e) => ($e['episode_id'] ?? '') !== $entry['episode_id']));
    array_unshift($index, $entry);
    file_put_contents($indexFile, json_encode($index, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
    return $entry;
}
