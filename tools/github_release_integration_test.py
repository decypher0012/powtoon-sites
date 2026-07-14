from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date,datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from work_launcher.github_updates import GitHubReleaseClient
from work_launcher.update_download import download_release,verify_download
from work_launcher.update_models import UpdateMetadataError


def digest(path: Path) -> str:return hashlib.sha256(path.read_bytes()).hexdigest()
def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True)


def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--repository",required=True,help="owner/repository confirmation")
    args=parser.parse_args();owner,repository=args.repository.split("/",1)
    version=f"9000.0.0-beta.{int(datetime.now(timezone.utc).timestamp())}";tag=f"v{version}";dist=ROOT/"dist"
    with tempfile.TemporaryDirectory() as temporary:
        work=Path(temporary)
        for name in ("WorkLauncher.exe","Updater.exe"):shutil.copy2(dist/name,work/name)
        app_hash=digest(work/"WorkLauncher.exe");updater_hash=digest(work/"Updater.exe")
        sums=f"{app_hash}  WorkLauncher.exe\n{updater_hash}  Updater.exe\n";(work/"SHA256SUMS.txt").write_text(sums,encoding="utf-8")
        metadata={"version":version,"release_date":date.today().isoformat(),"channel":"beta","minimum_supported_version":"1.0.0","mandatory":False,
                  "download":{"portable":"WorkLauncher.exe"},"size":{"portable":(work/"WorkLauncher.exe").stat().st_size},"sha256":{"portable":app_hash},
                  "release_notes":["Controlled updater integration test","Temporary prerelease; safe to delete"]}
        (work/"release.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
        created=False
        try:
            run("gh","release","create",tag,"--repo",args.repository,"--target","main","--prerelease","--title",f"Temporary updater test {tag}",
                "--notes","Controlled temporary updater integration test.",*[str(work/name) for name in ("WorkLauncher.exe","Updater.exe","SHA256SUMS.txt","release.json")]);created=True
            client=GitHubReleaseClient();release=client.check(owner,repository,"beta","portable")
            if release.version!=version or "Controlled updater integration test" not in release.release_notes:raise RuntimeError("Temporary release was not discovered correctly.")
            progress=[];download=download_release(release,work/"downloaded.exe",lambda done,total:progress.append((done,total)));verify_download(download,release.sha256,release.size)
            run("gh","release","delete-asset",tag,"SHA256SUMS.txt","--repo",args.repository,"--yes")
            (work/"SHA256SUMS.txt").write_text(f"{'0'*64}  WorkLauncher.exe\n{updater_hash}  Updater.exe\n",encoding="utf-8")
            run("gh","release","upload",tag,str(work/"SHA256SUMS.txt"),"--repo",args.repository)
            try:client.check(owner,repository,"beta","portable")
            except UpdateMetadataError:invalid_blocked=True
            else:invalid_blocked=False
            if not invalid_blocked:raise RuntimeError("Invalid checksum release was not blocked.")
            print(f"GITHUB_INTEGRATION version={version} notes=True progress_events={len(progress)} integrity=True invalid_checksum_blocked=True secrets_printed=False")
        finally:
            if created:subprocess.run(["gh","release","delete",tag,"--repo",args.repository,"--yes","--cleanup-tag"],capture_output=True,text=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
