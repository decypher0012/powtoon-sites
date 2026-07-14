# Work Launcher

Work Launcher is a lightweight Windows Tkinter app that opens six work websites in configured browser profiles. It stores configuration at `%APPDATA%\WorkLauncher\config.json`, rotating logs at `%LOCALAPPDATA%\WorkLauncher\logs\`, and never reads or modifies browser data or credentials.

## Browser profiles

Each website references a named entry in `browser_profiles`. The defaults are **Windows Default Browser** and **Chrome Work**. All six built-in sites use Chrome Work, configured as:

```text
User Data directory: C:\Users\decyp\AppData\Local\Google\Chrome\User Data
Profile Directory: Profile 4
Fallback to Windows default browser: disabled
```

These are deliberately separate. Chrome receives `--user-data-dir=<User Data>` and `--profile-directory=Profile 4`; the combined `...\User Data\Profile 4` path is not a browser executable or a substitute for those two arguments.

To identify another profile, open `chrome://version` in that profile and inspect **Profile Path**. Its parent is the User Data directory and its final folder (such as `Default` or `Profile 4`) is the Profile Directory.

Open **Settings > Browser Profiles** to add, edit, duplicate, delete, or test a profile. The test action clearly confirms before opening `https://www.google.com/`. Select a website in Settings and use its browser-profile dropdown to assign a profile. An in-use profile cannot be deleted.

When a Chrome executable path is blank, discovery checks `%PROGRAMFILES%`, `%PROGRAMFILES(X86)%`, then `%LOCALAPPDATA%` for `Google\Chrome\Application\chrome.exe`. A configured explicit path takes precedence. Chrome launch failures do not silently use another browser; fallback occurs only when `fallback_to_system_browser` is explicitly enabled.

## Configuration migration and recovery

Version 1 configuration is migrated once to version 2. Existing websites, ordering, selections, and settings are preserved; browser profiles are added and websites without an assignment receive `chrome-work`. Before committing migration, the original is copied to `config.json.bak`. The migrated file is written atomically. If migration cannot be written, the original remains unchanged. Invalid JSON/configuration recovery also backs up the invalid file before creating defaults.

Only validated HTTP/HTTPS URLs are launched. Browser values reject control characters and unsafe Profile Directory values. URLs with query strings are logged only by display name and origin.

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

`build.bat` creates/uses `.venv`, installs test/build dependencies, runs the complete test suite, stops on failure, and creates the no-console one-file executable at `dist\WorkLauncher.exe`. Re-run it whenever source changes. Startup integration uses the current user's Startup folder and requires no administrator privileges.

Open All, Open Selected, individual buttons, selection/window persistence, launch delay, duplicate cooldown, in-progress locking, Settings, status, startup integration, configuration backup/recovery, URL validation, and rotating logging remain supported.

Work Launcher does not store credentials, automate login, bypass Okta, inspect cookies/passwords/history, inject scripts, or use Selenium.
