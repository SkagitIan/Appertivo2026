import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from flask import current_app


def capture_path():
    value = current_app.config.get("EMAIL_CAPTURE_PATH")
    return Path(value) if value else None


def write_capture(record):
    path = capture_path()
    if not path:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    capture_id = f"capture-{uuid4().hex}"
    payload = {
        "id": capture_id,
        "timestamp": datetime.now(UTC).isoformat(),
        **record,
    }
    with path.open("a", encoding="utf-8") as capture_file:
        capture_file.write(json.dumps(payload, sort_keys=True) + "\n")
    return capture_id

