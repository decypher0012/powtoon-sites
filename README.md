# Work Launcher

Work Launcher is a lightweight Windows Tkinter app that opens six work websites in configured browser profiles. It stores configuration at `%APPDATA%\WorkLauncher\config.json`, rotating logs at `%LOCALAPPDATA%\WorkLauncher\logs\`, and never reads or modifies browser data or credentials.

## GitHub Releases and updates

Work Launcher has a native two-process updater. `WorkLauncher.exe` checks the configured GitHub repository through the GitHub Releases API; it never scrapes release pages. A verified update downloads in the background to `%LOCALAPPDATA%\WorkLauncher\Updates\`, then launches the separate `Updater.exe` and exits. The updater waits for Work Launcher, re-verifies file size and SHA-256, renames the current executable to `WorkLauncher.exe.bak`, installs the new executable, and restarts it. If replacement fails, the backup is restored automatically. Configuration, logs, websites, and browser profiles are not replaced.

Configure the GitHub owner, repository, stable/beta channel, and policy under **Settings > Updates**. The installation type is detected automatically from a minimal marker beside installed executables; copies without that exact marker are portable. Users cannot silently switch update types in Settings. Policies are Notify, Automatic, and Manual; Notify is the default. Automatic checks are limited to once per session and at most every 24 hours, based on the last successful check. Offline errors, API rate limits, absent releases, invalid JSON, and missing assets are reported without interrupting normal use. The About dialog, Settings, logs, and update dialog all use the canonical version from `src/work_launcher/version.py`.

For this project, configure `owner` as `decypher0012` and `repository` as `powtoon-sites`. Remind Me Later closes the dialog and allows the normal 24-hour schedule to apply; a manual Check Now remains available. Skip suppresses only that exact version and can be cleared in Settings. Mandatory releases disable Skip but never block offline startup or lock the application when download/installation fails. Automatic Download downloads and verifies without installing; the Automatic policy installs after verification. Work Launcher never automatically downgrades, including when moving from beta back to stable.

The configured GitHub repository must be public for credential-free client updates. Work Launcher deliberately does not store or transmit GitHub tokens. A private repository returns 404 to unauthenticated clients even when the user who built the app has repository access. Make the release repository public before enabling production update checks, or leave update checks disabled; do not embed a personal access token in the executable or configuration.

Every release must contain:

```text
WorkLauncher.exe
Updater.exe
WorkLauncher-Setup.exe
SHA256SUMS.txt
release.json
```

`release.json` uses this strict schema; unknown top-level fields, unsafe asset names, incorrect types, or disagreement with GitHub asset size are rejected:

```json
{
  "version": "1.0.1",
  "release_date": "2026-07-15",
  "channel": "stable",
  "minimum_supported_version": "1.0.0",
  "mandatory": false,
  "download": {"portable": "WorkLauncher.exe", "installer": "WorkLauncher-Setup.exe"},
  "size": {"portable": 12345678, "installer": 15000000},
  "sha256": {"portable": "64-lowercase-hex-characters", "installer": "64-lowercase-hex-characters"},
  "release_notes": ["Description of the release"]
}
```

Stable publishing uses a stable SemVer tag such as `v1.0.1`; beta publishing uses a prerelease canonical version/tag such as `1.1.0-beta.1` / `v1.1.0-beta.1`. The workflow derives the channel from that version. Work Launcher accepts only exact asset names and HTTPS release URLs belonging to the configured GitHub repository. Duplicate assets are rejected rather than choosing one. Metadata and `SHA256SUMS.txt` must agree; final downloaded bytes must match the GitHub size and SHA-256 before execution. No downloaded scripts or arbitrary asset names are executed.

This integrity model detects corruption and inconsistent release assets, but it does not establish publisher identity equivalent to Authenticode or independently signed metadata. Current binaries are unsigned and Windows SmartScreen may warn on first use. A future signing path is to obtain an organization-controlled Authenticode certificate, protect signing credentials in a restricted release environment, sign both executables before checksum generation, and verify signatures in the updater. Do not add signing claims until that pipeline exists and is validated.

Installed copies require the `WorkLauncher-Setup.exe` metadata entries. The standalone updater verifies the installer, waits for the authenticated Work Launcher process to exit, and launches it silently with `shell=False`. It never falls back to the portable asset when the required installer asset is missing. Portable copies continue to use the built-in executable backup and rollback transaction.

## Windows installer

`WorkLauncher-Setup.exe` is a per-user Inno Setup package. It requires no administrator privileges and installs only:

```text
%LOCALAPPDATA%\Programs\WorkLauncher\WorkLauncher.exe
%LOCALAPPDATA%\Programs\WorkLauncher\Updater.exe
%LOCALAPPDATA%\Programs\WorkLauncher\install-mode.json
```

It creates a Start-menu shortcut and offers an unchecked desktop shortcut. Its permanent AppId is `7A07E62F-0C3A-45D2-91E8-4E5BE929A8D9`; do not change this identity between releases. Upgrades retain the previous installation directory and use Windows Restart Manager for locked application files.

The installer never packages or deletes `%APPDATA%\WorkLauncher` configuration or `%LOCALAPPDATA%\WorkLauncher` logs and update downloads. Uninstall therefore retains user configuration for recovery or reinstallation.

Unattended per-user installation is supported:

```bat
WorkLauncher-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER
```

Add `/NOLAUNCH` when deployment tooling should not start Work Launcher after installation, and `/NOICONS` when no shortcuts should be created. The generated uninstaller accepts `/VERYSILENT /NORESTART`; it removes program files and shortcuts but retains Work Launcher user data.

### Publishing a release

1. Update the single `__version__` value using semantic versioning (`major.minor.patch`).
2. Commit and push the change.
3. Create and push a matching tag, for example `v1.2.0`.
4. The Windows GitHub Actions workflow verifies the tag, obtains verified Inno Setup 6.7.3 from its immutable upstream release, runs every test, builds both application executables and the installer, then uploads all five release assets.

The workflow runs only on pushed version-like tags, builds the tagged commit, pins third-party actions by commit SHA, refuses an existing release, and performs a release-content audit before publication. To revoke a bad release, disable automatic publication first if needed, delete the GitHub Release, delete the associated tag only after confirming no corrected release will reuse it, increment the patch version, and publish a new tag. Do not replace assets under an existing version.

To roll back a bad portable release locally, close Work Launcher, confirm `WorkLauncher.exe.bak` is present beside it, rename the faulty executable out of the way, rename the `.bak` file to `WorkLauncher.exe`, and launch it. For an installed copy, rerun the previous known-good installer locally, then publish the correction as a new higher patch version. Preserve `%APPDATA%\WorkLauncher\config.json`; configuration migrations already create their own backup. Never publish an automatic downgrade.

For a local release build, install Inno Setup 6.7.3 and run `build.bat`. It locates `ISCC.exe` on `PATH` or in standard per-user/system locations, derives both the displayed SemVer and numeric Windows file version from `src/work_launcher/version.py`, builds all three executables, audits the installer definition and release contents, and generates `SHA256SUMS.txt` and `release.json` in `dist\`.

Troubleshooting:

- **Offline or rate limited:** retry later or choose Manual updates; the application remains usable.
- **Missing assets/invalid metadata:** republish the release with all five generated files from the same build.
- **Checksum or size failure:** delete the partial update and retry; Work Launcher will not install it.
- **Replacement or restart failure:** check free disk space, antivirus quarantine, folder permissions, and file locks. The updater restores `WorkLauncher.exe.bak` automatically when its transaction fails.
- **Portable location is read-only:** move both executables to a user-writable folder or install `WorkLauncher-Setup.exe`.
- **Updater missing:** keep `Updater.exe` beside `WorkLauncher.exe`.
- **Installer compiler missing:** install Inno Setup 6.7.3 or place `ISCC.exe` on `PATH`.

## First-run setup and browser scanner

On a clean configuration, Work Launcher opens a six-step setup wizard. It scans installed browsers on a background thread, lets the user select one detected work profile, assigns all or selected websites to it, offers a clearly labeled Google test-page launch, and records `setup.completed` so the wizard does not reopen. Cancelling keeps setup incomplete and assigns websites to the safe Windows Default Browser. The wizard can be launched again from **Settings > Browser Profiles > Run Setup Wizard Again**.

Automatic installation and profile detection is implemented for Google Chrome, Microsoft Edge, Brave, Chromium, Vivaldi, and Mozilla Firefox. Settings provides **Scan Browsers**, **Rescan Profiles**, and **Import Detected Profile**. Detected profiles are never imported automatically; select one or more in the Detected Browser Profiles dialog and choose **Add Selected**. Already-imported profiles are identified by browser type, executable, user-data location, and profile identifier.

Chromium-family installations are checked in standard `%PROGRAMFILES%`, `%PROGRAMFILES(X86)%`, and `%LOCALAPPDATA%` locations, with Windows App Paths registry lookup as a fallback. Profile scanning is bounded to each browser's known User Data directory. Only `Default`, numbered `Profile N`, and `Guest Profile` folders with preference metadata are listed. Friendly names and the last-used/default indication are read from the non-sensitive profile index in `Local State`; the scanner falls back to the folder name if metadata is missing or damaged.

Firefox installation detection uses the same standard locations and registry fallback. Firefox profiles come only from `%APPDATA%\Mozilla\Firefox\profiles.ini`; the scanner reads name, path, relative/absolute status, and default status, then checks that the directory exists. Firefox launches with `-P <ProfileName> -no-remote`. If Firefox is already running, its profile locking and `-no-remote` behavior may prevent a second instance; close Firefox and retry, or configure a supported alternative profile.

The scanner is strictly read-only. It detects installation paths, profile directory names, friendly profile names, and default markers. It does not open or process passwords, cookies, browsing history, autofill/payment data, tokens, sessions, tabs, bookmarks, extensions, downloads, cache, or page content, and it never copies or modifies browser files.

Portable browsers, enterprise custom paths, and unsupported browsers can be added using **Configure Manually** in the detected-profiles dialog or the existing **Add** browser-profile action. Select the executable, User Data directory, and profile directory/name. Custom installations that are not in standard locations will not be automatically discovered. Use **Rescan Profiles** after installing, removing, or renaming a browser profile.

Before every launch, Work Launcher validates that the configured executable, User Data directory, and profile still exist. A stale or removed profile produces an actionable error. It never silently changes profiles; Windows-default fallback is used only when explicitly enabled.

## Website Manager

Open **Settings** to manage websites without editing JSON. The Website Manager supports adding, editing, duplicating, deleting, enabling/disabling, reordering, testing, searching, importing, and exporting websites. Multi-select rows to enable, disable, delete, move, or assign a browser profile in bulk. Changes are saved to `config.json` and the main window refreshes immediately.

**Add Website** and **Edit Website** provide Display Name, validated HTTP/HTTPS URL, Browser Profile, Enabled, Selected by Default, and optional Launch Group fields. Duplicate names and URLs produce warnings; duplicate URLs remain allowed. Delete asks for confirmation, and Duplicate creates a neighboring `(Copy)` entry.

Import accepts a websites-only export, a websites list, or a current Work Launcher configuration. A preview appears before choosing replace or merge and whether to skip duplicate names or URLs. Export can write websites only or the entire configuration as JSON.

Destructive and bulk operations create timestamped files such as `config-2026-07-14-143500-000000.json` beside the active configuration. The newest ten are retained. Delete, bulk delete, and import replace/merge can be undone while the same Settings window remains open; its undo history is intentionally cleared on close.

Websites can have one optional Launch Group, such as Daily Work, Google, Admin, Meetings, or a custom value. The main-window **Launch Group** selector is generated from the current configuration and launches only enabled websites in that group.

All main-window rows and buttons are generated dynamically from `config.json`. Adding, removing, renaming, reordering, enabling, or disabling a website requires neither source changes nor rebuilding the executable.

## Browser profiles

Each website references a named entry in `browser_profiles`. A new configuration contains **Windows Default Browser** and the logical placeholder **Chrome Work (configure during setup)**. The placeholder contains no machine-specific browser path or profile directory. During first-run setup, selecting a detected work profile remaps the existing `chrome-work` logical ID and preserves all website assignments instead of creating a duplicate profile.

For an existing machine that uses Chrome `Profile 4`, the resulting local mapping may be:

```text
User Data directory: `%LOCALAPPDATA%\Google\Chrome\User Data`
Profile Directory: Profile 4
Fallback to Windows default browser: disabled
```

These values are deliberately separate and are examples, not cross-machine defaults. Chrome receives `--user-data-dir=<User Data>` and `--profile-directory=<folder>`; the combined profile path is not a browser executable or a substitute for those two arguments.

To identify another profile, open `chrome://version` in that profile and inspect **Profile Path**. Its parent is the User Data directory and its final folder (such as `Default` or `Profile 4`) is the Profile Directory.

Open **Settings > Browser Profiles** to add, edit, duplicate, delete, or test a profile. The test action clearly confirms before opening `https://www.google.com/`. Select a website in Settings and use its browser-profile dropdown to assign a profile. An in-use profile cannot be deleted.

Settings marks each profile as **Valid** or **Unavailable** and shows its configured directory and website usage. Select an unavailable logical profile and choose **Remap** to scan for a replacement local profile while retaining the same profile ID and all website assignments. Unused unavailable profiles are preserved until explicitly edited, remapped, or deleted.

Settings changes are section-scoped. Changing Windows startup, theme, launch timing, or update preferences does not perform blocking filesystem validation on unrelated browser profiles. Unavailable profiles produce a warning instead. Adding, editing, testing, remapping, or newly assigning a browser profile still requires that profile to be locally valid. When a launch includes both valid and unavailable profiles, valid websites open, unavailable websites are skipped, and the status area lists the skipped website names; fallback is never implicit.

When a Chrome executable path is blank, discovery checks `%PROGRAMFILES%`, `%PROGRAMFILES(X86)%`, then `%LOCALAPPDATA%` for `Google\Chrome\Application\chrome.exe`. A configured explicit path takes precedence. Chrome launch failures do not silently use another browser; fallback occurs only when `fallback_to_system_browser` is explicitly enabled.

## Configuration migration and recovery

Legacy configurations are migrated once to version 4. Existing websites, ordering, selections, settings, and browser profiles are preserved; missing browser profiles, setup state, and update preferences are added safely. Existing version 2 or newer users are treated as already set up, while a genuinely new configuration launches the wizard. Before committing migration, the original is copied to `config.json.bak`. The migrated file is written atomically. If migration cannot be written, the original remains unchanged. Invalid JSON/configuration recovery also backs up the invalid file before creating defaults.

Only validated HTTP/HTTPS URLs are launched. Browser values reject control characters and unsafe Profile Directory values. URLs with query strings are logged only by display name and origin.

Manual editing of `%APPDATA%\WorkLauncher\config.json` remains available for advanced users. Close Work Launcher before manual edits and preserve the existing JSON structure. The file remains the single source of truth; the Website Manager is its graphical editor and does not replace unrelated settings or browser profiles.

## Troubleshooting

- **Wrong profile opens:** verify User Data and Profile Directory separately against `chrome://version`; ensure the website is assigned to Chrome Work.
- **Chrome is already running:** Chrome normally routes the request to the matching running profile. If it behaves unexpectedly, close all Chrome processes and retry after confirming the arguments/configuration.
- **Missing Profile Directory:** confirm that `<User Data directory>\<Profile Directory>` exists and that the directory field is only a folder name such as `Profile 4`.
- **Chrome not found:** select `chrome.exe` explicitly in Browser Profiles or install Chrome in a standard location.
- Review logs in `%LOCALAPPDATA%\WorkLauncher\logs\` for sanitized discovery, validation, and launch results.

## Run, test, and build

Windows and Python 3 are required.

```bat
run.bat
build.bat
```

`build.bat` creates/uses `.venv`, installs test/build dependencies, runs the complete test suite, stops on failure, and creates the no-console executables plus `dist\WorkLauncher-Setup.exe`. Re-run it whenever source changes. Startup integration uses the current user's Startup folder and requires no administrator privileges.

Open All, Open Selected, individual buttons, selection/window persistence, launch delay, duplicate cooldown, in-progress locking, Settings, status, startup integration, configuration backup/recovery, URL validation, and rotating logging remain supported.

Work Launcher does not store credentials, automate login, bypass Okta, inspect cookies/passwords/history, inject scripts, or use Selenium.
