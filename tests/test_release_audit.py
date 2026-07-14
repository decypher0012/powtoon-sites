import hashlib
import json
from pathlib import Path

import pytest

from tools.audit_release import audit


def make_release(path: Path, app=b"app", updater=b"updater"):
    (path/"WorkLauncher.exe").write_bytes(app);(path/"Updater.exe").write_bytes(updater)
    app_hash=hashlib.sha256(app).hexdigest();updater_hash=hashlib.sha256(updater).hexdigest()
    (path/"SHA256SUMS.txt").write_text(f"{app_hash}  WorkLauncher.exe\n{updater_hash}  Updater.exe\n",encoding="utf-8")
    metadata={"version":"1.0.0","release_date":"2026-07-15","channel":"stable","minimum_supported_version":"1.0.0","mandatory":False,
              "download":{"portable":"WorkLauncher.exe"},"size":{"portable":len(app)},"sha256":{"portable":app_hash},"release_notes":["Ready"]}
    (path/"release.json").write_text(json.dumps(metadata),encoding="utf-8")


def test_release_content_audit_accepts_exact_assets(tmp_path):
    make_release(tmp_path);audit(tmp_path)


@pytest.mark.parametrize("bad_file",["config.json","work_launcher.log","unrelated.exe",".env"])
def test_release_content_audit_rejects_extra_or_prohibited_files(tmp_path,bad_file):
    make_release(tmp_path);(tmp_path/bad_file).write_text("unexpected",encoding="utf-8")
    with pytest.raises(RuntimeError):audit(tmp_path)


@pytest.mark.parametrize("personal",[b"C:\\Users\\decyp\\secret",b"X:\\powtoon-sites",b"ghp_abcdefghijklmnopqrstuvwxyz123456"])
def test_release_content_audit_rejects_personal_paths_and_tokens(tmp_path,personal):
    make_release(tmp_path,app=personal)
    with pytest.raises(RuntimeError):audit(tmp_path)
