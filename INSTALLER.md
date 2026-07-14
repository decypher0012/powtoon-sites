# Work Launcher Installer Guide

This guide explains how to build, test, and publish the Work Launcher Windows installer.

## Requirements

Use Windows 10 or Windows 11 with:

- Python 3.12
- Git
- Inno Setup 6.7.3

Install the required Inno Setup compiler from PowerShell:

```powershell
winget install --id JRSoftware.InnoSetup --exact --version 6.7.3 --scope user
```

Verify that the compiler is installed:

```powershell
Test-Path "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
```

The expected result is `True`.

## Set the application version

Do not run `version.py`. Open `src\work_launcher\version.py` in a text editor and update the canonical version:

```python
__version__ = "1.0.1"
```

Use semantic versions such as:

```text
1.0.1
1.1.0
2.0.0
1.1.0-beta.1
```

Do not enter the version separately in the Inno Setup script. The build derives the application, installer, metadata, and numeric Windows file versions from this Python value.

Optionally verify the version from the project root:

```powershell
$env:PYTHONPATH = "src"
python -c "from work_launcher.version import __version__; print(__version__)"
```

## Build the installer

Open PowerShell in the repository:

```powershell
cd X:\powtoon-sites
```

Run:

```powershell
.\build.bat
```

The build process:

1. Creates or reuses `.venv`.
2. Installs the pinned test and build dependencies.
3. Runs the complete automated test suite.
4. Builds `WorkLauncher.exe`.
5. Builds `Updater.exe`.
6. Compiles `WorkLauncher-Setup.exe` with Inno Setup.
7. Audits the installer definition and packaged release files.
8. Generates SHA-256 checksums and `release.json`.

The build stops if any test, compiler, metadata, or audit step fails.

## Build output

A successful build creates these files under `dist\`:

```text
WorkLauncher.exe
Updater.exe
WorkLauncher-Setup.exe
SHA256SUMS.txt
release.json
```

The file to distribute to normal users is:

```text
dist\WorkLauncher-Setup.exe
```

List the output and file sizes with:

```powershell
Get-ChildItem .\dist
```

## Test a normal installation

Start the installer:

```powershell
.\dist\WorkLauncher-Setup.exe
```

Confirm that:

- No administrator prompt appears.
- The default directory is `%LOCALAPPDATA%\Programs\WorkLauncher`.
- A Start-menu shortcut is created.
- The desktop shortcut is optional and unchecked by default.
- Work Launcher opens when installation completes.
- The installed directory contains `WorkLauncher.exe`, `Updater.exe`, and `install-mode.json`.
- Existing websites, browser profiles, and preferences remain intact.
- A clean installation contains no hardcoded local Chrome profile directory; first-run setup remaps the logical `chrome-work` profile to the selected local profile.

The installer does not package, overwrite, or remove data under:

```text
%APPDATA%\WorkLauncher
%LOCALAPPDATA%\WorkLauncher
```

## Silent installation

Install without user interaction:

```powershell
.\dist\WorkLauncher-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER
```

Prevent the application from opening afterward:

```powershell
.\dist\WorkLauncher-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /NOLAUNCH
```

Prevent shortcuts from being created:

```powershell
.\dist\WorkLauncher-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /NOLAUNCH /NOICONS
```

## Test an upgrade

1. Install the current version.
2. Change `__version__` in `src\work_launcher\version.py` to a higher version.
3. Run `.\build.bat` again.
4. Run the newly generated `WorkLauncher-Setup.exe` over the existing installation.
5. Confirm the application reports the new version.
6. Confirm websites, selections, browser profiles, setup state, and update preferences were preserved.

The permanent installer AppId must not be changed. Inno Setup uses it to recognize existing installations and upgrades.

## Uninstall

Use **Windows Settings > Apps > Installed apps > Work Launcher > Uninstall**, or run:

```powershell
& "$env:LOCALAPPDATA\Programs\WorkLauncher\unins000.exe"
```

Silent uninstall:

```powershell
& "$env:LOCALAPPDATA\Programs\WorkLauncher\unins000.exe" /VERYSILENT /NORESTART
```

Uninstall removes the program files and shortcuts. It deliberately retains Work Launcher configuration and logs so they remain available after reinstalling.

## Publish a GitHub release

After setting the new version, commit and push it:

```powershell
git add .
git commit -m "Release Work Launcher 1.0.1"
git push origin main
```

Create and push a matching version tag:

```powershell
git tag v1.0.1
git push origin v1.0.1
```

The tag must exactly match the canonical version with a leading `v`:

```text
version.py: 1.0.1
Git tag:    v1.0.1
```

The GitHub Actions workflow builds the tagged commit and publishes:

```text
WorkLauncher.exe
Updater.exe
WorkLauncher-Setup.exe
SHA256SUMS.txt
release.json
```

Never replace assets under an existing release. Publish a correction using a higher patch version.

The repository must be public for Work Launcher's credential-free GitHub update checks. Do not embed a GitHub token in the application or installer.

## Code signing and SmartScreen

The current executables and installer are unsigned. Windows SmartScreen may display an unrecognized-application warning.

For public production distribution, obtain an appropriate Authenticode signing identity and sign in this order:

1. `WorkLauncher.exe`
2. `Updater.exe`
3. The generated Inno Setup uninstaller
4. `WorkLauncher-Setup.exe`

Generate `SHA256SUMS.txt` and `release.json` only after signing, because signing changes the executable bytes and hashes.

## Troubleshooting

- **Inno Setup not found:** install version 6.7.3 or put `ISCC.exe` on `PATH`.
- **Tests fail:** fix the failing test before attempting to package a release.
- **Installer missing:** review the Inno Setup compiler output from `build.bat`.
- **Metadata audit fails:** rebuild all assets together; do not copy executables from another build.
- **Version/tag mismatch:** make the Git tag exactly `v` followed by the value in `version.py`.
- **SmartScreen warning:** expected while the installer remains unsigned.
- **Private repository update failure:** make the release repository public or disable update checks; never distribute embedded GitHub credentials.
