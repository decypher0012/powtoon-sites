from __future__ import annotations

import logging
import os
import subprocess
import shutil
import time
from pathlib import Path
from typing import Callable

from .update_download import verify_download
from .update_models import UpdateError


def validate_process_executable(pid: int, expected: Path) -> None:
    if pid<=0: return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32=ctypes.WinDLL("kernel32",use_last_error=True); kernel32.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD); kernel32.OpenProcess.restype=wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes=(wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)); kernel32.QueryFullProcessImageNameW.restype=wintypes.BOOL
        kernel32.CloseHandle.argtypes=(wintypes.HANDLE,); kernel32.CloseHandle.restype=wintypes.BOOL
        handle=kernel32.OpenProcess(0x1000,False,pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle: raise UpdateError("Unable to verify the Work Launcher process.")
        size=ctypes.c_ulong(32768); buffer=ctypes.create_unicode_buffer(size.value)
        ok=kernel32.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)); kernel32.CloseHandle(handle)
        if not ok or Path(buffer.value).resolve()!=expected.resolve(): raise UpdateError("Parent process is not the intended WorkLauncher.exe.")
    except AttributeError: return


def validate_update_path(path: Path, root: Path) -> Path:
    if not path.is_absolute() or not root.is_absolute(): raise UpdateError("Updater paths must be absolute.")
    resolved=path.resolve(); allowed=root.resolve()
    if resolved.parent!=allowed or resolved.suffix.lower()!=".exe": raise UpdateError("Downloaded update path is outside the Work Launcher Updates directory.")
    return resolved


def wait_for_process_exit(pid: int, timeout_seconds: float = 60.0) -> None:
    if pid <= 0: return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32=ctypes.WinDLL("kernel32",use_last_error=True); kernel32.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD); kernel32.OpenProcess.restype=wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes=(wintypes.HANDLE,wintypes.DWORD); kernel32.WaitForSingleObject.restype=wintypes.DWORD
        kernel32.CloseHandle.argtypes=(wintypes.HANDLE,); kernel32.CloseHandle.restype=wintypes.BOOL
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
        if not handle: return
        result = kernel32.WaitForSingleObject(handle,int(timeout_seconds*1000)); kernel32.CloseHandle(handle)
        if result == 0x102: raise UpdateError("Timed out waiting for Work Launcher to close.")
    except AttributeError:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try: os.kill(pid, 0)
            except OSError: return
            time.sleep(0.2)
        raise UpdateError("Timed out waiting for Work Launcher to close.")


def install_update(current_executable: Path, downloaded_executable: Path, expected_sha256: str, expected_size: int,
                   parent_pid: int = 0, restart: bool = True, waiter: Callable[[int, float], None] = wait_for_process_exit,
                   launcher: Callable = subprocess.Popen, process_validator: Callable[[int,Path],None] = validate_process_executable,
                   status_callback: Callable[[str,bool],None] | None = None, ready_callback: Callable[[],None] | None = None) -> None:
    if not current_executable.is_absolute() or not downloaded_executable.is_absolute(): raise UpdateError("Updater paths must be absolute.")
    current_executable = current_executable.resolve(); downloaded_executable = downloaded_executable.resolve()
    if current_executable==downloaded_executable or current_executable.name.lower() != "worklauncher.exe" or downloaded_executable.suffix.lower() != ".exe":
        raise UpdateError("Updater only replaces WorkLauncher.exe with a verified executable asset.")
    verify_download(downloaded_executable, expected_sha256, expected_size)
    process_validator(parent_pid,current_executable)
    if ready_callback: ready_callback()
    waiter(parent_pid,60.0); backup=current_executable.with_suffix(current_executable.suffix+".bak"); staging=current_executable.with_suffix(current_executable.suffix+".new")
    staging.unlink(missing_ok=True)
    try:
        shutil.copy2(downloaded_executable,staging); verify_download(staging,expected_sha256,expected_size)
    except Exception as exc:
        staging.unlink(missing_ok=True); raise UpdateError(f"Update staging failed; the current version was not changed ({type(exc).__name__}).") from exc
    backup.unlink(missing_ok=True)
    try:
        os.replace(current_executable, backup)
        os.replace(staging,current_executable)
        verify_download(current_executable,expected_sha256,expected_size)
        downloaded_executable.unlink(missing_ok=True)
        logging.info("Update installation succeeded: %s", current_executable.name)
    except Exception as exc:
        logging.error("Update installation failed; attempting rollback: %s", type(exc).__name__)
        try:
            staging.unlink(missing_ok=True)
            if backup.exists():
                current_executable.unlink(missing_ok=True); os.replace(backup, current_executable); logging.warning("Update rollback succeeded")
        except Exception as rollback_exc: raise UpdateError(f"Update failed and rollback failed ({type(rollback_exc).__name__}).") from exc
        if status_callback: status_callback("install_failed_previous_version_restored",True)
        raise UpdateError(f"Update installation failed; the previous executable was restored ({type(exc).__name__}).") from exc
    if restart:
        try:
            if status_callback: status_callback("update_installed",False)
            launcher([str(current_executable)],shell=False)
        except Exception as exc:
            logging.error("Updated application restart failed; restoring backup")
            try:
                current_executable.unlink(missing_ok=True); os.replace(backup,current_executable)
                if status_callback: status_callback("restart_failed_previous_version_restored",True)
                launcher([str(current_executable)],shell=False)
            except Exception as rollback_exc: raise UpdateError(f"Restart failed and rollback failed ({type(rollback_exc).__name__}).") from exc
            raise UpdateError("Updated application could not restart; the previous version was restored and restarted.") from exc


def install_with_installer(installer: Path, expected_sha256: str, expected_size: int, parent_pid: int = 0,
                           waiter: Callable[[int, float], None] = wait_for_process_exit, launcher: Callable = subprocess.Popen,
                           process_validator: Callable[[int,Path],None] | None = None, current_executable: Path | None = None,
                           ready_callback: Callable[[],None] | None = None) -> None:
    if not installer.is_absolute(): raise UpdateError("Updater paths must be absolute.")
    installer = installer.resolve()
    if installer.suffix.lower() != ".exe": raise UpdateError("Installer update asset must be an executable.")
    verify_download(installer, expected_sha256, expected_size)
    if process_validator and current_executable: process_validator(parent_pid,current_executable)
    if ready_callback: ready_callback()
    waiter(parent_pid, 60.0)
    arguments=[str(installer),"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/CLOSEAPPLICATIONS"]
    logging.info("Starting verified installer update: %s", installer.name); launcher(arguments, shell=False)
