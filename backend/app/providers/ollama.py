"""Ollama management: detect the server, pick the best model for our workload,
pull it if missing, warm it up and save it in settings."""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field

from ..config import OLLAMA_URL, AppSettings, settings_store

log = logging.getLogger("aipodcaster.ollama")

# Ordered by how well they handle our tasks (strict JSON, summarising, fact judging)
# within a VRAM budget. (name, approx GB of VRAM needed, quality score 0-100)
CANDIDATES: list[tuple[str, float, int]] = [
    ("qwen3:32b", 22.0, 96),
    ("gemma3:27b", 18.0, 94),
    ("qwen3:14b", 10.5, 90),
    ("gemma3:12b", 9.0, 88),
    ("qwen2.5:14b-instruct", 10.0, 87),
    ("llama3.1:8b", 6.0, 80),
    ("qwen3:8b", 6.0, 82),
    ("mistral-nemo:12b", 8.5, 81),
    ("gemma3:4b", 3.5, 70),
    ("qwen3:4b", 3.5, 72),
    ("llama3.2:3b", 2.5, 60),
    ("qwen2.5:3b-instruct", 2.5, 58),
]
FAMILY_SCORE = {"qwen3": 90, "gemma3": 88, "qwen2.5": 85, "llama3.1": 80, "mistral-nemo": 80, "llama3.3": 92, "llama3": 70, "mistral": 72, "phi4": 78, "deepseek-r1": 75, "qwen3-vl": 84, "llama3.2": 60}
EXCLUDE = re.compile(r"embed|embedding|vision-only|whisper|bge|nomic|clip", re.I)


@dataclass
class ModelInfo:
    name: str
    size_gb: float
    parameter_size: str
    family: str
    score: int


@dataclass
class PullProgress:
    model: str = ""
    status: str = "idle"  # idle | pulling | done | failed
    completed: int = 0
    total: int = 0
    message: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    log: list[str] = field(default_factory=list)


_progress = PullProgress()
_pull_lock = threading.Lock()


def base_url(settings: AppSettings | None = None) -> str:
    url = settings.language_model.base_url if settings and settings.language_model.provider == "ollama" and settings.language_model.base_url else OLLAMA_URL
    return url.rstrip("/")


def is_running(url: str | None = None) -> bool:
    import httpx

    try:
        return httpx.get(f"{url or base_url()}/api/version", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def try_start_server(url: str | None = None, wait_seconds: float = 12) -> bool:
    """Launch `ollama serve` if the binary exists and the server is down."""
    if is_running(url):
        return True
    binary = shutil.which("ollama")
    if not binary:
        return False
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([binary, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=creationflags)  # noqa: S603
    except OSError as error:
        log.warning("Could not start ollama: %s", error)
        return False
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if is_running(url):
            return True
        time.sleep(0.5)
    return False


def _family(name: str) -> str:
    return re.split(r"[:/]", name)[0].lower()


def _score(name: str, parameter_size: str) -> int:
    family = _family(name)
    base = FAMILY_SCORE.get(family, 50)
    match = re.search(r"([\d.]+)B", parameter_size or "", re.I)
    params = float(match.group(1)) if match else 0.0
    size_bonus = min(int(params), 32) // 2  # bigger is better, capped
    for candidate, _, score in CANDIDATES:
        if candidate == name:
            return score
    return min(99, base + size_bonus - 8)


def list_models(url: str | None = None) -> list[ModelInfo]:
    import httpx

    try:
        data = httpx.get(f"{url or base_url()}/api/tags", timeout=10).json()
    except (httpx.HTTPError, ValueError):
        return []
    models: list[ModelInfo] = []
    for item in data.get("models", []):
        name = str(item.get("name", ""))
        if not name or EXCLUDE.search(name):
            continue
        details = item.get("details", {}) or {}
        parameter_size = str(details.get("parameter_size", ""))
        models.append(ModelInfo(name=name, size_gb=round(int(item.get("size", 0)) / 2**30, 1), parameter_size=parameter_size, family=_family(name), score=_score(name, parameter_size)))
    return sorted(models, key=lambda m: m.score, reverse=True)


def gpu_memory_gb() -> float | None:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return None
    try:
        output = subprocess.run([binary, "--query-gpu=memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10, check=False).stdout  # noqa: S603
        values = [float(line.strip()) for line in output.splitlines() if line.strip()]
        return round(max(values) / 1024, 1) if values else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def system_memory_gb() -> float:
    try:
        import psutil

        return round(psutil.virtual_memory().total / 2**30, 1)
    except ImportError:
        return 16.0


def budget_gb() -> float:
    gpu = gpu_memory_gb()
    if gpu:
        return gpu * 0.9
    return min(system_memory_gb() * 0.5, 24.0)


def recommend(installed: list[ModelInfo], budget: float | None = None) -> tuple[str, bool, str]:
    """Return (model, needs_pull, reason)."""
    budget = budget or budget_gb()
    fitting = [c for c in CANDIDATES if c[1] <= budget]
    best_download = fitting[0] if fitting else CANDIDATES[-1]
    installed_fit = [m for m in installed if m.size_gb * 1.15 <= budget]
    if installed_fit:
        top = installed_fit[0]
        # Keep an installed model unless the best downloadable one is clearly better.
        if top.score >= best_download[2] - 6:
            return top.name, False, f"{top.name} is already installed and fits in {budget:.0f} GB"
        return best_download[0], True, f"{best_download[0]} (score {best_download[2]}) beats installed {top.name} (score {top.score}) for JSON/fact-check work"
    return best_download[0], True, f"No suitable local model yet; {best_download[0]} fits in {budget:.0f} GB"


def pull_progress() -> dict:
    return asdict(_progress)


def pull(model: str, url: str | None = None) -> bool:
    """Start a background pull; returns False if one is already running."""
    with _pull_lock:
        if _progress.status == "pulling":
            return False
        _progress.__init__(model=model, status="pulling", started_at=time.time())

    def task() -> None:
        import httpx

        try:
            with httpx.stream("POST", f"{url or base_url()}/api/pull", json={"name": model, "stream": True}, timeout=httpx.Timeout(30.0, read=None)) as response:
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    _progress.message = str(event.get("status", ""))
                    _progress.completed = int(event.get("completed", _progress.completed) or 0)
                    _progress.total = int(event.get("total", _progress.total) or 0)
                    if event.get("error"):
                        raise RuntimeError(str(event["error"]))
            _progress.status, _progress.message = "done", "Model downloaded"
        except Exception as error:  # noqa: BLE001
            _progress.status, _progress.message = "failed", str(error)[:300]
        finally:
            _progress.finished_at = time.time()

    threading.Thread(target=task, name="ollama-pull", daemon=True).start()
    return True


def warm_up(model: str, url: str | None = None) -> bool:
    import httpx

    try:
        response = httpx.post(f"{url or base_url()}/api/generate", json={"model": model, "prompt": "ok", "stream": False, "keep_alive": "30m", "options": {"num_predict": 1}}, timeout=300)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def status(settings: AppSettings | None = None) -> dict:
    url = base_url(settings)
    running = is_running(url)
    installed = list_models(url) if running else []
    recommended, needs_pull, reason = recommend(installed) if running else ("", False, "Ollama is not running")
    current = settings.language_model.model if settings and settings.language_model.provider == "ollama" else ""
    return {
        "url": url,
        "installed_binary": shutil.which("ollama") is not None,
        "running": running,
        "models": [asdict(m) for m in installed],
        "recommended": recommended,
        "needs_pull": needs_pull,
        "reason": reason,
        "budget_gb": round(budget_gb(), 1),
        "gpu_gb": gpu_memory_gb(),
        "current_model": current,
        "current_loaded": bool(current) and any(m.name == current for m in installed),
        "pull": pull_progress(),
    }


def setup(model: str | None = None, start_server: bool = True) -> dict:
    """Ensure Ollama runs, choose (or accept) a model, pull it if needed, warm it and persist."""
    settings = settings_store.get()
    url = base_url(settings)
    if not is_running(url) and (not start_server or not try_start_server(url)):
        return {"ok": False, "step": "server", "message": "Ollama is not running and could not be started. Install it from https://ollama.com and run `ollama serve`."}
    installed = list_models(url)
    chosen, needs_pull, reason = (model, all(m.name != model for m in installed), "Selected manually") if model else recommend(installed)

    def apply(current: AppSettings) -> None:
        current.language_model.provider = "ollama"
        current.language_model.model = chosen
        if not current.language_model.base_url:
            current.language_model.base_url = url

    settings_store.mutate(apply)
    if needs_pull:
        started = pull(chosen, url)
        return {"ok": True, "step": "pulling", "model": chosen, "reason": reason, "message": f"Downloading {chosen}. Progress is available at /v1/providers/ollama/status." if started else "A download is already in progress."}
    warmed = warm_up(chosen, url)
    return {"ok": True, "step": "ready", "model": chosen, "reason": reason, "message": f"{chosen} is {'loaded and ' if warmed else ''}set as the language model."}
