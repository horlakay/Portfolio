# SentinelStream Analyst Desktop

SentinelStream Analyst Desktop is the first desktop shell for the existing
`analyst-console` experience. It wraps the current FastAPI/Jinja console in an
Electron window so the project can evolve toward a Windows-distributable analyst
workbench instead of remaining browser-only.

## What it does today

- launches a native desktop window for the analyst console
- supports an `external` mode that points at an already-running console URL
- supports an `embedded` development mode that starts the FastAPI
  `analyst-console` process locally
- persists desktop settings locally so you can switch connection targets without
  retyping environment variables
- shows a branded loading screen while the console warms up
- falls back to an offline screen with retry and browser-open actions when the
  console is unreachable

## Recommended mode

Use `external` mode with the existing Docker Compose stack:

```powershell
docker compose up -d postgres redis redpanda otel-collector rule-engine model-service feature-service decision-service feedback-service analyst-console
cd apps/analyst-desktop
npm install
npm run dev
```

Environment variables:

- `SENTINEL_DESKTOP_BACKEND_MODE`
  - `external` (default) or `embedded`
- `SENTINEL_DESKTOP_URL`
  - default: `http://127.0.0.1:8007`
- `SENTINEL_DESKTOP_PORT`
  - default: `8007`
- `SENTINEL_DESKTOP_STARTUP_TIMEOUT_MS`
  - default: `45000`

Use `Ctrl+,` inside the desktop app to open the built-in Settings screen.

## Embedded mode

Embedded mode is useful when you want the desktop shell to launch the
`analyst-console` process for you during development.

It only starts the console process itself. The decision and feedback services
still need to be reachable if you want the dashboard to render live data.

```powershell
python -m pip install .[dev]
$env:SENTINEL_DESKTOP_BACKEND_MODE = "embedded"
$env:SENTINEL_DESKTOP_PYTHON = "$PWD\\.venv314\\Scripts\\python.exe"
cd apps/analyst-desktop
npm run dev
```

Optional overrides for embedded mode:

- `SENTINEL_DESKTOP_PYTHON`
- `SENTINEL_DESKTOP_REPO_ROOT`
- `SENTINEL_DESKTOP_BACKEND_CWD`

## Packaging

Local packaging commands:

```powershell
cd apps/analyst-desktop
npm install
npm run pack
npm run dist
```

`pack` and `dist` now clean the previous `release/` directory first so the
output folder only contains the current build artifacts.

Current packaging targets:

- Windows NSIS installer
- Windows portable executable

Expected release artifacts:

- `release/SentinelStream Analyst Desktop-Setup-<version>-x64.exe`
- `release/SentinelStream Analyst Desktop-Portable-<version>-x64.exe`

## Microsoft Store direction

This shell is the first productization step, not the final Microsoft Store
artifact yet. The next phase would be:

1. define a supported runtime mode for end users
2. add production icons, branding, and update flow
3. package with Microsoft-friendly identity and submission assets
4. align the app with Store privacy-policy and support requirements
5. move from Electron packaging to a Store-oriented MSIX release workflow

Store preparation materials now live in:

- `store/README.md`
- `store/partner-center-checklist.md`
- `store/listing.en-US.md`
- `store/privacy-policy.template.md`
- `store/support.template.md`

Public-facing release drafts also live in:

- `../../docs/desktop-store-release.md`
- `../../docs/legal/privacy-policy.md`
- `../../docs/legal/support.md`
