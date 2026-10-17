"""Read/write the JSON files the website reads.

Every dataset is wrapped in an envelope:
  {"_meta": {"source", "fetched_at", "status": "ok"|"error", "error", "last_success"}, "data": ...}
On failure the previous numbers are NOT kept in "data": the site must show
"data unavailable" with the error and the time of the last successful update.
"""
import json
import math
import os
import tempfile
import traceback
from datetime import datetime, timezone

DATA_DIR = os.environ.get("ATLAS_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "site", "data"))


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(o):
    """Make data JSON-safe: NaN/inf -> None, numpy scalars -> python."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            o = o.item()
        except Exception:
            pass
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def path(name):
    return os.path.join(DATA_DIR, name)


def read(name, default=None):
    try:
        with open(path(name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write(name, obj):
    full = path(name)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(full), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(_clean(obj), f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    os.replace(tmp, full)


def envelope_ok(source, data, extra=None):
    meta = {"source": source, "fetched_at": now_iso(), "status": "ok", "error": None}
    meta["last_success"] = meta["fetched_at"]
    if extra:
        meta.update(extra)
    return {"_meta": meta, "data": data}


def envelope_error(source, err, previous=None):
    last = (previous or {}).get("_meta", {}).get("last_success") if previous else None
    return {"_meta": {"source": source, "fetched_at": now_iso(), "status": "error",
                      "error": f"{type(err).__name__}: {err}"[:500], "last_success": last},
            "data": None}


def run_dataset(name, source, fn):
    """Run fn() -> data; write ok/error envelope. Returns True on success."""
    previous = read(name)
    try:
        data = fn()
        write(name, envelope_ok(source, data))
        return True
    except Exception as e:  # noqa: BLE001 - any failure must surface as "data unavailable"
        traceback.print_exc()
        write(name, envelope_error(source, e, previous))
        return False
