import hashlib
import io
import json
import tempfile
import urllib.error
import ssl
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from work_launcher.config import default_config,load_config,save_config
from work_launcher.github_updates import GitHubReleaseClient
from work_launcher.installation import installation_kind
from work_launcher.update_download import download_release, verify_download
from work_launcher.update_manager import UpdateManager
from work_launcher.update_models import (ReleaseInfo, UpdateCancelled, UpdateIntegrityError, UpdateMetadataError,
    UpdateNetworkError, is_newer, parse_version, version_tuple)
from work_launcher.updater import install_update, install_with_installer, validate_update_path


class Response:
    def __init__(self, data, headers=None, final_url=None): self.data=data; self.headers=headers or {}; self.final_url=final_url
    def read(self, size=-1):
        if not hasattr(self,"stream"): self.stream=io.BytesIO(self.data)
        return self.stream.read(size)
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def geturl(self): return self.final_url or "https://github.com/o/r/releases/download/v1.2.0/asset"


def github_payload(binary=b"new executable", version="1.2.0"):
    digest=hashlib.sha256(binary).hexdigest(); base="https://github.com/o/r/releases/download/v1.2.0/"
    release={"tag_name":f"v{version}","draft":False,"prerelease":"-" in version,"html_url":f"https://github.com/o/r/releases/tag/v{version}","assets":[
        {"name":"release.json","browser_download_url":base+"release.json","size":200},
        {"name":"SHA256SUMS.txt","browser_download_url":base+"SHA256SUMS.txt","size":100},
        {"name":"WorkLauncher.exe","browser_download_url":base+"WorkLauncher.exe","size":len(binary)}]}
    metadata={"version":version,"release_date":"2026-07-15","channel":"beta" if "-" in version else "stable","minimum_supported_version":"1.0.0","mandatory":False,
              "download":{"portable":"WorkLauncher.exe"},"size":{"portable":len(binary)},"sha256":{"portable":digest},"release_notes":["Feature","Fix"]}
    return release,metadata,digest,base


def test_semantic_versions():
    assert version_tuple("v1.2.3")== (1,2,3); assert version_tuple("v1.0.1")==version_tuple("1.0.1"); assert is_newer("1.2.0","1.0.0"); assert not is_newer("1.0.0","1.0.0")
    with pytest.raises(UpdateMetadataError): version_tuple("one")
    assert is_newer("1.0.1","1.0.0"); assert is_newer("1.1.0","1.0.99"); assert is_newer("2.0.0","1.99.99")
    assert is_newer("1.0.0","1.0.0-beta.2"); assert is_newer("1.0.0-beta.2","1.0.0-beta.1")
    assert not is_newer("1.0.0-beta.1","1.0.0"); assert not is_newer("1.0.0","2.0.0")
    for invalid in ("1.0","1.0.0-01","01.0.0","1.0.0-"):
        with pytest.raises(UpdateMetadataError): parse_version(invalid)


def test_github_release_check_stable_and_beta():
    release,metadata,digest,base=github_payload()
    mapping={"https://api.github.com/repos/o/r/releases/latest":json.dumps(release).encode(),
             "https://api.github.com/repos/o/r/releases?per_page=100&page=1":json.dumps([dict(release,draft=False)]).encode(),
             base+"release.json":json.dumps(metadata).encode(),base+"SHA256SUMS.txt":f"{digest}  WorkLauncher.exe\n".encode()}
    opener=lambda request,timeout=0: Response(mapping[request.full_url])
    stable=GitHubReleaseClient(opener).check("o","r","stable"); beta=GitHubReleaseClient(opener).check("o","r","beta")
    assert stable.version==beta.version=="1.2.0"; assert stable.release_notes==("Feature","Fix")


def test_installer_asset_selection_when_published():
    release,metadata,digest,base=github_payload();installer=b"verified setup";installer_hash=hashlib.sha256(installer).hexdigest()
    metadata["download"]["installer"]="WorkLauncher-Setup.exe";metadata["sha256"]["installer"]=installer_hash
    metadata["size"]["installer"]=len(installer)
    release["assets"].append({"name":"WorkLauncher-Setup.exe","browser_download_url":base+"WorkLauncher-Setup.exe","size":len(installer)})
    mapping={"https://api.github.com/repos/o/r/releases/latest":json.dumps(release).encode(),base+"release.json":json.dumps(metadata).encode(),
             base+"SHA256SUMS.txt":f"{digest}  WorkLauncher.exe\n{installer_hash}  WorkLauncher-Setup.exe\n".encode()}
    result=GitHubReleaseClient(lambda req,timeout=0:Response(mapping[req.full_url])).check("o","r","stable","installer")
    assert result.asset_kind=="installer";assert result.asset_name=="WorkLauncher-Setup.exe"


def test_installed_mode_requires_installer_asset_without_portable_fallback():
    release,metadata,digest,base=github_payload()
    mapping={"https://api.github.com/repos/o/r/releases/latest":json.dumps(release).encode(),base+"release.json":json.dumps(metadata).encode(),
             base+"SHA256SUMS.txt":f"{digest}  WorkLauncher.exe\n".encode()}
    with pytest.raises(UpdateMetadataError,match="required installer"):
        GitHubReleaseClient(lambda req,timeout=0:Response(mapping[req.full_url])).check("o","r","stable","installer")


def test_installation_kind_uses_only_exact_local_marker(tmp_path):
    executable=tmp_path/"WorkLauncher.exe";executable.write_bytes(b"app")
    assert installation_kind(executable)=="portable"
    (tmp_path/"install-mode.json").write_text('{"mode":"wrong"}',encoding="utf-8")
    assert installation_kind(executable)=="portable"
    (tmp_path/"install-mode.json").write_text('{"mode":"inno-user"}',encoding="utf-8")
    assert installation_kind(executable)=="installer"


@pytest.mark.parametrize("mutation",["missing_metadata","missing_asset","bad_sha","mismatched_sums"])
def test_invalid_or_missing_release_metadata(mutation):
    release,metadata,digest,base=github_payload()
    if mutation=="missing_metadata": release["assets"]=release["assets"][1:]
    if mutation=="missing_asset": release["assets"]=release["assets"][:2]
    if mutation=="bad_sha": metadata["sha256"]["portable"]="bad"
    sums=("0"*64 if mutation=="mismatched_sums" else digest)+"  WorkLauncher.exe\n"
    mapping={"https://api.github.com/repos/o/r/releases/latest":json.dumps(release).encode(),base+"release.json":json.dumps(metadata).encode(),base+"SHA256SUMS.txt":sums.encode()}
    with pytest.raises(UpdateMetadataError): GitHubReleaseClient(lambda req,timeout=0:Response(mapping[req.full_url])).check("o","r")


def test_invalid_json_offline_and_rate_limit():
    client=GitHubReleaseClient(lambda req,timeout=0:Response(b"not json"))
    with pytest.raises(UpdateMetadataError): client.check("o","r")
    with pytest.raises(UpdateNetworkError): GitHubReleaseClient(lambda *a,**k:(_ for _ in()).throw(urllib.error.URLError("offline"))).check("o","r")
    error=urllib.error.HTTPError("x",403,"rate",{},None)
    with pytest.raises(UpdateNetworkError,match="rate limit"): GitHubReleaseClient(lambda *a,**k:(_ for _ in()).throw(error)).check("o","r")
    with pytest.raises(UpdateNetworkError): GitHubReleaseClient(lambda *a,**k:(_ for _ in()).throw(TimeoutError())).check("o","r")
    with pytest.raises(UpdateNetworkError): GitHubReleaseClient(lambda *a,**k:(_ for _ in()).throw(ssl.SSLError())).check("o","r")


def test_draft_rejected_duplicate_assets_and_unsafe_repository_redirects():
    release,metadata,digest,base=github_payload();release["draft"]=True
    mapping={"https://api.github.com/repos/o/r/releases/latest":json.dumps(release).encode()}
    with pytest.raises(UpdateMetadataError,match="Draft"): GitHubReleaseClient(lambda req,timeout=0:Response(mapping[req.full_url])).check("o","r")
    release["draft"]=False;release["assets"].append(dict(release["assets"][0]))
    mapping["https://api.github.com/repos/o/r/releases/latest"]=json.dumps(release).encode()
    with pytest.raises(UpdateMetadataError,match="duplicate"): GitHubReleaseClient(lambda req,timeout=0:Response(mapping[req.full_url])).check("o","r")
    release["assets"]=release["assets"][:-1];release["assets"][0]["browser_download_url"]="https://github.com/other/repo/releases/download/v1/release.json"
    mapping["https://api.github.com/repos/o/r/releases/latest"]=json.dumps(release).encode()
    with pytest.raises(UpdateMetadataError,match="configured repository"): GitHubReleaseClient(lambda req,timeout=0:Response(mapping[req.full_url])).check("o","r")
    with pytest.raises(UpdateNetworkError,match="redirected"): GitHubReleaseClient(lambda req,timeout=0:Response(mapping.get(req.full_url,b"{}"),final_url="http://github.com/unsafe")).check("o","r")


@pytest.mark.parametrize("mutation",["extra","bad_date","wrong_channel","wrong_tag","unsafe_name","wrong_size","bad_type"])
def test_explicit_release_schema_rejects_dangerous_metadata(mutation):
    release,metadata,digest,base=github_payload()
    if mutation=="extra": metadata["script"]="run-me.ps1"
    elif mutation=="bad_date": metadata["release_date"]="tomorrow"
    elif mutation=="wrong_channel": metadata["channel"]="beta"
    elif mutation=="wrong_tag": release["tag_name"]="v9.9.9"
    elif mutation=="unsafe_name": metadata["download"]["portable"]="../evil.exe"
    elif mutation=="wrong_size": metadata["size"]["portable"]+=1
    elif mutation=="bad_type": metadata["mandatory"]="false"
    mapping={"https://api.github.com/repos/o/r/releases/latest":json.dumps(release).encode(),base+"release.json":json.dumps(metadata).encode(),base+"SHA256SUMS.txt":f"{digest}  WorkLauncher.exe\n".encode()}
    with pytest.raises(UpdateMetadataError): GitHubReleaseClient(lambda req,timeout=0:Response(mapping[req.full_url])).check("o","r")


def test_beta_selects_highest_non_draft_prerelease_and_stable_channel_rejects_prerelease():
    low,_,_,_=github_payload(version="1.1.0-beta.1"); high,metadata,digest,base=github_payload(version="1.1.0-beta.2"); draft,_,_,_=github_payload(version="9.0.0-beta.1");draft["draft"]=True
    mapping={"https://api.github.com/repos/o/r/releases?per_page=100&page=1":json.dumps([low,draft,high]).encode(),base+"release.json":json.dumps(metadata).encode(),base+"SHA256SUMS.txt":f"{digest}  WorkLauncher.exe\n".encode()}
    assert GitHubReleaseClient(lambda req,timeout=0:Response(mapping[req.full_url])).check("o","r","beta").version=="1.1.0-beta.2"


def release_info(data=b"payload"):
    return ReleaseInfo("2.0.0","2026-07-15","1.0.0",False,"WorkLauncher.exe","https://github.com/o/r/WorkLauncher.exe",hashlib.sha256(data).hexdigest(),len(data),("Notes",))


def test_download_progress_size_and_sha_verification():
    data=b"payload"*100; release=release_info(data); calls=[]
    with tempfile.TemporaryDirectory() as tmp:
        path=download_release(release,Path(tmp)/"update.exe",lambda done,total:calls.append((done,total)),opener=lambda req,timeout=0:Response(data,{"Content-Length":str(len(data))}))
        assert path.read_bytes()==data; assert calls[-1][0]==len(data); verify_download(path,release.sha256,len(data))


def test_corrupt_download_and_cancel_rejected():
    release=release_info(b"expected")
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(UpdateIntegrityError): download_release(release,Path(tmp)/"bad.exe",opener=lambda req,timeout=0:Response(b"corrupt"))
        event=Mock();event.is_set.return_value=True
        with pytest.raises(UpdateCancelled): download_release(release,Path(tmp)/"cancel.exe",cancel_event=event,opener=lambda req,timeout=0:Response(b"expected"))
        assert not list(Path(tmp).glob("*.part"))


def test_partial_download_and_insecure_redirect_cleanup():
    release=release_info(b"expected payload")
    class Partial(Response):
        def read(self,size=-1):
            if hasattr(self,"read_once"): raise urllib.error.URLError("interrupted")
            self.read_once=True; return b"partial"
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/"partial.exe"
        with pytest.raises(UpdateNetworkError): download_release(release,target,opener=lambda *a,**k:Partial(b""))
        assert not target.with_suffix(".exe.part").exists()
        with pytest.raises(UpdateNetworkError,match="redirected"): download_release(release,target,opener=lambda *a,**k:Response(b"expected payload",{"Content-Length":str(len(b"expected payload"))},"http://evil.test/file"))
        assert not target.with_suffix(".exe.part").exists()


def test_correct_size_wrong_sha_and_wrong_content_length_are_blocked():
    data=b"same-size"; release=ReleaseInfo("2.0.0","2026-07-15","1.0.0",False,"WorkLauncher.exe","https://github.com/o/r/releases/download/v2/WorkLauncher.exe","0"*64,len(data),())
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(UpdateIntegrityError): download_release(release,Path(tmp)/"x.exe",opener=lambda *a,**k:Response(data,{"Content-Length":str(len(data))}))
        good=release_info(data)
        with pytest.raises(UpdateIntegrityError,match="Content-Length"): download_release(good,Path(tmp)/"y.exe",opener=lambda *a,**k:Response(data,{"Content-Length":str(len(data)+1)}))


def test_update_manager_24_hours_session_and_persistence():
    config=default_config();config.updates.owner="o";config.updates.repository="r";client=Mock();client.check.return_value=release_info()
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"config.json";manager=UpdateManager(config,path,client)
        assert manager.due();assert manager.check().version=="2.0.0";assert not manager.due();assert manager.check() is manager.latest;assert client.check.call_count==1
        config.updates.last_checked=(datetime.now(timezone.utc)-timedelta(hours=25)).isoformat();manager.checked_this_session=False;assert manager.due()


def test_manual_policy_disables_due_check():
    config=default_config();config.updates.policy="manual";assert not UpdateManager(config,Path("unused")).due()


def test_mandatory_failure_does_not_lock_app_and_skip_version_persists():
    config=default_config();config.updates.owner="o";config.updates.repository="r";client=Mock();client.check.side_effect=UpdateNetworkError("offline")
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"config.json";save_config(path,config);manager=UpdateManager(config,path,client)
        with pytest.raises(UpdateNetworkError):manager.check()
        assert not manager.checked_this_session;assert config.updates.last_checked=="";assert path.exists()
        config.updates.skipped_version="1.2.3";save_config(path,config);loaded,_=load_config(path);assert loaded.updates.skipped_version=="1.2.3"


def test_current_newer_than_release_never_downgrades_and_minimum_marks_mandatory():
    config=default_config();config.updates.owner="o";config.updates.repository="r";client=Mock();client.check.return_value=ReleaseInfo("0.9.0","2026-01-01","0.8.0",False,"WorkLauncher.exe","https://github.com/o/r/releases/download/v/WorkLauncher.exe","0"*64,1,())
    with patch("work_launcher.update_manager.__version__","1.0.0"):
        with tempfile.TemporaryDirectory() as tmp:
            assert UpdateManager(config,Path(tmp)/"config.json",client).check() is None
        client.check.return_value=ReleaseInfo("1.1.0","2026-01-01","1.0.1",False,"WorkLauncher.exe","https://github.com/o/r/releases/download/v/WorkLauncher.exe","0"*64,1,())
        with tempfile.TemporaryDirectory() as tmp:
            assert UpdateManager(config,Path(tmp)/"config.json",client).check(force=True).mandatory


def test_install_replaces_backs_up_and_restarts_without_touching_config():
    old=b"old";new=b"new verified executable";digest=hashlib.sha256(new).hexdigest();launcher=Mock();waiter=Mock()
    with tempfile.TemporaryDirectory() as tmp:
        current=Path(tmp)/"WorkLauncher.exe";download=Path(tmp)/"download.exe";config=Path(tmp)/"config.json"
        current.write_bytes(old);download.write_bytes(new);config.write_text("preserve")
        install_update(current,download,digest,len(new),123,waiter=waiter,launcher=launcher,process_validator=lambda *a:None)
        assert current.read_bytes()==new;assert current.with_suffix(".exe.bak").read_bytes()==old;assert config.read_text()=="preserve"
        waiter.assert_called_once_with(123,60.0);assert launcher.call_args.kwargs["shell"] is False


def test_install_failure_rolls_back():
    old=b"old";new=b"new";digest=hashlib.sha256(new).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        current=Path(tmp)/"WorkLauncher.exe";download=Path(tmp)/"download.exe";current.write_bytes(old);download.write_bytes(new)
        real_replace=__import__("os").replace;calls=0
        def failing(source,target):
            nonlocal calls;calls+=1
            if calls==2: raise OSError("locked")
            return real_replace(source,target)
        with patch("work_launcher.updater.os.replace",side_effect=failing),pytest.raises(Exception):
            install_update(current,download,digest,len(new),waiter=lambda *a:None,restart=False)
        assert current.read_bytes()==old


@pytest.mark.parametrize("failure",[OSError("locked"),OSError("disk full"),PermissionError("quarantined")])
def test_locked_disk_full_and_antivirus_access_failures_restore_backup(failure):
    old=b"old";new=b"new";digest=hashlib.sha256(new).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        current=Path(tmp)/"WorkLauncher.exe";download=Path(tmp)/"download.exe";current.write_bytes(old);download.write_bytes(new);real_replace=os.replace;calls=0
        def fail_second(source,target):
            nonlocal calls;calls+=1
            if calls==2: raise failure
            return real_replace(source,target)
        with patch("work_launcher.updater.os.replace",side_effect=fail_second),pytest.raises(Exception):install_update(current,download,digest,len(new),waiter=lambda *a:None,restart=False)
        assert current.read_bytes()==old


def test_parent_process_validation_blocks_wrong_process_before_waiting():
    data=b"new";digest=hashlib.sha256(data).hexdigest();waiter=Mock()
    with tempfile.TemporaryDirectory() as tmp:
        current=Path(tmp)/"WorkLauncher.exe";download=Path(tmp)/"download.exe";current.write_bytes(b"old");download.write_bytes(data)
        with pytest.raises(Exception,match="wrong process"): install_update(current,download,digest,len(data),123,waiter=waiter,restart=False,process_validator=Mock(side_effect=Exception("wrong process")))
        waiter.assert_not_called();assert current.read_bytes()==b"old"


def test_ready_signal_follows_parent_validation_and_precedes_waiting():
    data=b"new";digest=hashlib.sha256(data).hexdigest();events=[]
    with tempfile.TemporaryDirectory() as tmp:
        current=Path(tmp)/"WorkLauncher.exe";download=Path(tmp)/"download.exe";current.write_bytes(b"old");download.write_bytes(data)
        install_update(current,download,digest,len(data),123,restart=False,
                       process_validator=lambda *_:events.append("validated"),
                       ready_callback=lambda:events.append("ready"),
                       waiter=lambda *_:events.append("waited"))
    assert events==["validated","ready","waited"]


def test_replacement_verification_failure_rolls_back_and_restart_failure_restores_old():
    old=b"old";new=b"new";digest=hashlib.sha256(new).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        current=Path(tmp)/"WorkLauncher.exe";download=Path(tmp)/"download.exe";current.write_bytes(old);download.write_bytes(new)
        real_verify=verify_download;calls=0
        def fail_second(path,sha,size):
            nonlocal calls;calls+=1
            if calls==3: raise UpdateIntegrityError("quarantined")
            return real_verify(path,sha,size)
        with patch("work_launcher.updater.verify_download",side_effect=fail_second),pytest.raises(Exception): install_update(current,download,digest,len(new),waiter=lambda *a:None,restart=False)
        assert current.read_bytes()==old
    with tempfile.TemporaryDirectory() as tmp:
        current=Path(tmp)/"WorkLauncher.exe";download=Path(tmp)/"download.exe";current.write_bytes(old);download.write_bytes(new);launcher=Mock(side_effect=[OSError("blocked"),None])
        with pytest.raises(Exception,match="previous version was restored"): install_update(current,download,digest,len(new),waiter=lambda *a:None,launcher=launcher)
        assert current.read_bytes()==old;assert launcher.call_count==2


def test_rollback_failure_is_reported_and_paths_are_confined():
    old=b"old";new=b"new";digest=hashlib.sha256(new).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        current=Path(tmp)/"WorkLauncher.exe";download=Path(tmp)/"download.exe";current.write_bytes(old);download.write_bytes(new)
        real_replace=os.replace;calls=0
        def fail_install_and_rollback(source,target):
            nonlocal calls;calls+=1
            if calls in {2,3}: raise OSError("denied")
            return real_replace(source,target)
        with patch("work_launcher.updater.os.replace",side_effect=fail_install_and_rollback),pytest.raises(Exception,match="rollback failed"):
            install_update(current,download,digest,len(new),waiter=lambda *a:None,restart=False)
        root=Path(tmp).resolve();safe=root/"WorkLauncher-2.0.0.exe";safe.write_bytes(new)
        assert validate_update_path(safe,root)==safe
        with pytest.raises(Exception): validate_update_path(root/".."/"evil.exe",root)


def test_updater_rejects_unverified_or_wrong_target():
    with tempfile.TemporaryDirectory() as tmp:
        current=Path(tmp)/"Other.exe";download=Path(tmp)/"download.exe";current.write_bytes(b"old");download.write_bytes(b"new")
        with pytest.raises(Exception): install_update(current,download,"0"*64,3,waiter=lambda *a:None,restart=False)


def test_verified_installer_mode_waits_and_launches_without_shell():
    data=b"setup executable";digest=hashlib.sha256(data).hexdigest();waiter=Mock();launcher=Mock()
    with tempfile.TemporaryDirectory() as tmp:
        setup=Path(tmp)/"WorkLauncher-Setup.exe";setup.write_bytes(data)
        install_with_installer(setup,digest,len(data),42,waiter=waiter,launcher=launcher)
        waiter.assert_called_once_with(42,60.0)
        assert launcher.call_args.args[0]==[str(setup.resolve()),"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/CLOSEAPPLICATIONS"]
        assert launcher.call_args.kwargs["shell"] is False
