from __future__ import annotations

import argparse
import logging
from pathlib import Path

from work_launcher.logging_config import configure_logging
from work_launcher.updater import install_update, install_with_installer, validate_process_executable, validate_update_path
from work_launcher.update_download import updates_dir
from work_launcher.version import __version__
from work_launcher.update_status import status_path, write_update_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Work Launcher verified update installer")
    parser.add_argument("--current", required=True); parser.add_argument("--download", required=True)
    parser.add_argument("--sha256", required=True); parser.add_argument("--size", required=True, type=int); parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--installer", action="store_true")
    parser.add_argument("--ready-file",required=True)
    args = parser.parse_args(); configure_logging(); logging.info("Starting Work Launcher Updater version %s",__version__)
    try: status_path().unlink(missing_ok=True)
    except OSError: pass
    try:
        if args.parent_pid<=0: raise ValueError("A running Work Launcher parent process is required.")
        root=updates_dir().resolve(); current=Path(args.current); download=validate_update_path(Path(args.download),root); ready=Path(args.ready_file)
        if not ready.is_absolute() or ready.resolve().parent!=root or ready.suffix!=".ready": raise ValueError("Invalid updater handshake path.")
        def signal_ready(): ready.write_text("ready",encoding="ascii")
        if args.installer: install_with_installer(download,args.sha256,args.size,args.parent_pid,process_validator=validate_process_executable,current_executable=current,ready_callback=signal_ready)
        else: install_update(current,download,args.sha256,args.size,args.parent_pid,status_callback=write_update_status,ready_callback=signal_ready)
        return 0
    except Exception as exc:
        try:
            if not status_path().exists(): write_update_status("update_failed",False)
        except OSError: pass
        logging.error("Updater failed: %s",type(exc).__name__); return 1
    finally:
        try:
            if 'ready' in locals(): ready.unlink(missing_ok=True)
        except OSError: pass


raise SystemExit(main())
