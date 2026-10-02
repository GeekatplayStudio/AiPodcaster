import os
import subprocess
import sys
from pathlib import Path

import pytest

TMP_ROOT = Path(__file__).resolve().parent / ".tmp-data"
os.environ["AIPODCASTER_DATA_DIR"] = str(TMP_ROOT)
os.environ["AIPODCASTER_TRANSCRIBER"] = "fake"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.publishing.store import target_store  # noqa: E402
from app.rag import index  # noqa: E402
from app.rag.store import library_store, project_store  # noqa: E402
from app.storage import job_store  # noqa: E402


@pytest.fixture(autouse=True)
def clean_store():
    job_store.clear()
    library_store.clear()
    project_store.clear()
    target_store.clear()
    index.reset_for_tests()
    yield
    job_store.clear()
    library_store.clear()
    project_store.clear()
    index.reset_for_tests()


@pytest.fixture(scope="session")
def sample_wav(tmp_path_factory) -> Path:
    """Synthesise a 12 s test tone with a 3 s gap so silence detection has work to do."""
    path = tmp_path_factory.mktemp("media") / "sample.wav"
    expr = r"sin(440*2*PI*t)*0.4*lt(mod(t\,8)\,5)"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc={expr}:s=16000:d=12", "-c:a", "pcm_s16le", str(path)], check=True)
    return path


@pytest.fixture(autouse=True)
def reset_settings():
    """Restore defaults (plus env overrides such as the fake transcriber) around every test."""
    from app.config import settings_store

    def restore() -> None:
        settings_store._path.unlink(missing_ok=True)
        fresh = settings_store._load()
        settings_store.mutate(lambda s: s.__dict__.update(fresh.__dict__))

    restore()
    yield
    restore()
