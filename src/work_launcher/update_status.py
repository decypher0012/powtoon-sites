from __future__ import annotations

import json
import os
from pathlib import Path


def status_path() -> Path:
    path=Path(os.environ.get("LOCALAPPDATA",Path.home()/"AppData"/"Local"))/"WorkLauncher"/"Updates"/"update-status.json"
    path.parent.mkdir(parents=True,exist_ok=True); return path


def write_update_status(status: str, rollback: bool=False) -> None:
    path=status_path(); temporary=path.with_suffix(".tmp"); temporary.write_text(json.dumps({"status":status,"rollback":rollback}),encoding="utf-8"); os.replace(temporary,path)


def consume_update_status() -> dict | None:
    path=status_path()
    if not path.is_file(): return None
    try:
        data=json.loads(path.read_text(encoding="utf-8")); return data if isinstance(data,dict) else None
    except (OSError,json.JSONDecodeError): return None
    finally:
        try:path.unlink(missing_ok=True)
        except OSError:pass
