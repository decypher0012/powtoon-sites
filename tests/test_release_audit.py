import hashlib
import json
from pathlib import Path

import pytest

from tools.audit_release import audit
from tools.audit_installer import audit_installer_definition


def make_release(path: Path, app=b"app", updater=b"updater", setup=b"setup"):
    (path/"WorkLauncher.exe").write_bytes(app);(path/"Updater.exe").write_bytes(updater);(path/"WorkLauncher-Setup.exe").write_bytes(setup)
    app_hash=hashlib.sha256(app).hexdigest();updater_hash=hashlib.sha256(updater).hexdigest();setup_hash=hashlib.sha256(setup).hexdigest()
    (path/"SHA256SUMS.txt").write_text(f"{app_hash}  WorkLauncher.exe\n{updater_hash}  Updater.exe\n{setup_hash}  WorkLauncher-Setup.exe\n",encoding="utf-8")
    metadata={"version":"1.0.0","release_date":"2026-07-15","channel":"stable","minimum_supported_version":"1.0.0","mandatory":False,
              "download":{"portable":"WorkLauncher.exe","installer":"WorkLauncher-Setup.exe"},"size":{"portable":len(app),"installer":len(setup)},
              "sha256":{"portable":app_hash,"installer":setup_hash},"release_notes":["Ready"]}
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


def test_installer_definition_has_fixed_identity_and_safe_payload():
    audit_installer_definition()


def test_installer_definition_rejects_configuration_payload(tmp_path):
    script=tmp_path/"WorkLauncher.iss";marker=tmp_path/"install-mode.json"
    source=(Path(__file__).parents[1]/"installer"/"WorkLauncher.iss").read_text(encoding="utf-8")
    script.write_text(source+'\nSource: "config.json"; DestDir: "{app}"\n',encoding="utf-8")
    marker.write_text('{"mode":"inno-user"}',encoding="utf-8")
    with pytest.raises(RuntimeError):audit_installer_definition(script,marker)
