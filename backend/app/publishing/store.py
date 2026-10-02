"""JSON-backed store for publishing targets; secrets are kept server-side only."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

from ..config import DATA_DIR
from ..schemas import utc_now
from .schemas import SECRET_MASK, PublishTarget, PublishTargetUpsert, kind_by_id


class TargetStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _read(self) -> list[PublishTarget]:
        if not self._path.exists():
            return []
        try:
            return [PublishTarget.model_validate(item) for item in json.loads(self._path.read_text("utf-8"))]
        except (ValueError, OSError):
            return []

    def _write(self, targets: list[PublishTarget]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps([t.model_dump(mode="json") for t in targets], indent=2), "utf-8")
        tmp.replace(self._path)

    def list(self) -> list[PublishTarget]:
        with self._lock:
            return self._read()

    def get(self, target_id: UUID) -> PublishTarget:
        target = next((t for t in self.list() if t.id == target_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Publishing target not found")
        return target

    def create(self, body: PublishTargetUpsert) -> PublishTarget:
        kind = kind_by_id(body.kind)
        if kind is None:
            raise HTTPException(status_code=422, detail="Unknown target kind")
        target = PublishTarget(name=body.name.strip(), kind=body.kind, config=_clean(body.config), enabled=body.enabled)
        _validate(target)
        with self._lock:
            targets = self._read()
            targets.append(target)
            self._write(targets)
        return target

    def update(self, target_id: UUID, body: PublishTargetUpsert) -> PublishTarget:
        with self._lock:
            targets = self._read()
            current = next((t for t in targets if t.id == target_id), None)
            if current is None:
                raise HTTPException(status_code=404, detail="Publishing target not found")
            merged = dict(current.config)
            for key, value in _clean(body.config).items():
                if value == SECRET_MASK:
                    continue
                merged[key] = value
            updated = current.model_copy(update={"name": body.name.strip(), "kind": body.kind, "config": merged, "enabled": body.enabled, "updated_at": utc_now()})
            _validate(updated)
            self._write([updated if t.id == target_id else t for t in targets])
            return updated

    def record_result(self, target_id: UUID, message: str) -> None:
        with self._lock:
            targets = self._read()
            for target in targets:
                if target.id == target_id:
                    target.last_result = message[:300]
            self._write(targets)

    def delete(self, target_id: UUID) -> None:
        with self._lock:
            targets = self._read()
            if not any(t.id == target_id for t in targets):
                raise HTTPException(status_code=404, detail="Publishing target not found")
            self._write([t for t in targets if t.id != target_id])

    def clear(self) -> None:
        with self._lock:
            self._path.unlink(missing_ok=True)


def _clean(config: dict[str, str]) -> dict[str, str]:
    return {str(k)[:60]: str(v).strip()[:2000] for k, v in config.items()}


def _validate(target: PublishTarget) -> None:
    kind = kind_by_id(target.kind)
    if kind is None:
        raise HTTPException(status_code=422, detail="Unknown target kind")
    missing = [f.label for f in kind.fields if f.required and not target.config.get(f.name)]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing fields: {', '.join(missing)}")
    for name in ("url", "site_url"):
        value = target.config.get(name)
        if value and not value.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail=f"{name} must start with http:// or https://")


target_store = TargetStore(DATA_DIR / "publish_targets.json")
