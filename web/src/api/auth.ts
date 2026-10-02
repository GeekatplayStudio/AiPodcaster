/** Optional API key the browser sends when the server requires one for UI access. */
const STORAGE_KEY = "aipodcaster.apiKey";

export function getUiApiKey(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setUiApiKey(value: string): void {
  try {
    if (value) window.localStorage.setItem(STORAGE_KEY, value);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable */
  }
}

export function authHeaders(): Record<string, string> {
  const key = getUiApiKey();
  return key ? { "X-API-Key": key } : {};
}
