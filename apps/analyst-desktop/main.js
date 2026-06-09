"use strict";

const { app, BrowserWindow, Menu, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const https = require("node:https");
const path = require("node:path");

const APP_ROOT = __dirname;
const SETTINGS_FILENAME = "desktop-settings.json";
const SETTINGS_DEFAULTS = {
  mode: "external",
  targetUrl: "http://127.0.0.1:8007",
  port: 8007,
  startupTimeoutMs: 45000,
  pythonExecutable: "python",
  repoRoot: "",
  backendCwd: "",
};

let mainWindow = null;
let backendProcess = null;
let isQuitting = false;
let lastStartupError = null;
let persistedSettings = null;

function getSettingsPath() {
  return path.join(app.getPath("userData"), SETTINGS_FILENAME);
}

function looksLikeRepoRoot(candidate) {
  return (
    fs.existsSync(
      path.join(candidate, "services", "analyst-console", "src", "analyst_console", "main.py"),
    ) &&
    fs.existsSync(path.join(candidate, "shared", "src", "sentinel_shared", "config", "base.py"))
  );
}

function findRepoRootFrom(startDir) {
  let current = path.resolve(startDir);

  while (true) {
    if (looksLikeRepoRoot(current)) {
      return current;
    }

    const parent = path.dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
}

function discoverRepoRoot() {
  const candidates = [
    process.cwd(),
    APP_ROOT,
    path.dirname(process.execPath),
    path.resolve(APP_ROOT, "..", ".."),
  ];

  for (const candidate of candidates) {
    const resolved = findRepoRootFrom(candidate);
    if (resolved) {
      return resolved;
    }
  }

  return null;
}

function coerceInt(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeUrl(value, fallback) {
  const candidate = String(value || fallback).trim();
  if (!candidate) {
    return fallback;
  }

  try {
    return new URL(candidate).toString().replace(/\/$/, "");
  } catch {
    return fallback;
  }
}

function loadPersistedSettings() {
  const settingsPath = getSettingsPath();
  try {
    const raw = fs.readFileSync(settingsPath, "utf-8");
    const parsed = JSON.parse(raw);
    return {
      ...SETTINGS_DEFAULTS,
      ...parsed,
      mode: parsed.mode === "embedded" ? "embedded" : "external",
      targetUrl: normalizeUrl(parsed.targetUrl, SETTINGS_DEFAULTS.targetUrl),
      port: coerceInt(parsed.port, SETTINGS_DEFAULTS.port),
      startupTimeoutMs: coerceInt(parsed.startupTimeoutMs, SETTINGS_DEFAULTS.startupTimeoutMs),
      pythonExecutable: String(parsed.pythonExecutable || SETTINGS_DEFAULTS.pythonExecutable),
      repoRoot: String(parsed.repoRoot || ""),
      backendCwd: String(parsed.backendCwd || ""),
    };
  } catch {
    return { ...SETTINGS_DEFAULTS };
  }
}

function savePersistedSettings(settings) {
  const settingsPath = getSettingsPath();
  fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
  fs.writeFileSync(settingsPath, `${JSON.stringify(settings, null, 2)}\n`, "utf-8");
  persistedSettings = settings;
}

function getEnvOverrides() {
  return {
    mode: process.env.SENTINEL_DESKTOP_BACKEND_MODE,
    targetUrl: process.env.SENTINEL_DESKTOP_URL,
    port: process.env.SENTINEL_DESKTOP_PORT,
    startupTimeoutMs: process.env.SENTINEL_DESKTOP_STARTUP_TIMEOUT_MS,
    pythonExecutable: process.env.SENTINEL_DESKTOP_PYTHON,
    repoRoot: process.env.SENTINEL_DESKTOP_REPO_ROOT,
    backendCwd: process.env.SENTINEL_DESKTOP_BACKEND_CWD,
  };
}

function getDesktopConfig() {
  const discoveredRepoRoot = discoverRepoRoot() || "";
  const baseSettings = persistedSettings || loadPersistedSettings();
  const env = getEnvOverrides();

  const repoRoot = String(env.repoRoot || baseSettings.repoRoot || discoveredRepoRoot || "");
  const targetUrl = normalizeUrl(env.targetUrl || baseSettings.targetUrl, SETTINGS_DEFAULTS.targetUrl);
  const port = coerceInt(env.port || baseSettings.port, SETTINGS_DEFAULTS.port);
  const startupTimeoutMs = coerceInt(
    env.startupTimeoutMs || baseSettings.startupTimeoutMs,
    SETTINGS_DEFAULTS.startupTimeoutMs,
  );

  const config = {
    mode: String(env.mode || baseSettings.mode || SETTINGS_DEFAULTS.mode).toLowerCase() === "embedded"
      ? "embedded"
      : "external",
    targetUrl,
    port,
    startupTimeoutMs,
    pythonExecutable: String(
      env.pythonExecutable || baseSettings.pythonExecutable || SETTINGS_DEFAULTS.pythonExecutable,
    ),
    repoRoot,
    backendCwd: String(env.backendCwd || baseSettings.backendCwd || repoRoot || ""),
    discoveredRepoRoot,
  };

  config.healthUrl = new URL("/health/ready", config.targetUrl).toString();
  return config;
}

function buildPythonPath(config) {
  if (!config.repoRoot) {
    return process.env.PYTHONPATH || "";
  }

  const pythonEntries = [
    path.join(config.repoRoot, "shared", "src"),
    path.join(config.repoRoot, "services", "analyst-console", "src"),
    path.join(config.repoRoot, "services", "decision-service", "src"),
    path.join(config.repoRoot, "services", "feedback-service", "src"),
  ];

  return [...pythonEntries, process.env.PYTHONPATH || ""]
    .filter(Boolean)
    .join(path.delimiter);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1200,
    minHeight: 760,
    backgroundColor: "#09111f",
    title: "SentinelStream Analyst Desktop",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(APP_ROOT, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Hardening: never let the renderer spawn new Electron windows. Any
  // window.open / target=_blank request is routed to the user's default
  // browser instead, which keeps untrusted navigation out of the app shell.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http:") || url.startsWith("https:")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function createMenu() {
  const template = [
    {
      label: "SentinelStream",
      submenu: [
        {
          label: "Open Settings",
          accelerator: "CmdOrCtrl+,",
          click: () => {
            showSettings();
          },
        },
        {
          label: "Retry Connection",
          accelerator: "CmdOrCtrl+R",
          click: async () => {
            await bootstrapDesktop();
          },
        },
        {
          label: "Open In Browser",
          click: async () => {
            await shell.openExternal(getDesktopConfig().targetUrl);
          },
        },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "toggledevtools" },
        { type: "separator" },
        { role: "resetzoom" },
        { role: "zoomin" },
        { role: "zoomout" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function requestJson(url, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const client = parsed.protocol === "https:" ? https : http;
    const request = client.request(
      parsed,
      { method: "GET", timeout: timeoutMs },
      (response) => {
        const chunks = [];

        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          const body = Buffer.concat(chunks).toString("utf-8");
          resolve({
            statusCode: response.statusCode || 0,
            body,
          });
        });
      },
    );

    request.on("timeout", () => {
      request.destroy(new Error(`Timed out after ${timeoutMs}ms`));
    });
    request.on("error", reject);
    request.end();
  });
}

async function waitForConsoleReady(config) {
  const deadline = Date.now() + config.startupTimeoutMs;
  let lastError = null;

  while (Date.now() < deadline) {
    try {
      const response = await requestJson(config.healthUrl, 3000);
      if (response.statusCode >= 200 && response.statusCode < 300) {
        return;
      }
      lastError = new Error(`Health check returned ${response.statusCode}`);
    } catch (error) {
      lastError = error;
    }

    await new Promise((resolve) => setTimeout(resolve, 1200));
  }

  throw lastError || new Error("Timed out waiting for the analyst console.");
}

function ensureEmbeddedBackend(config) {
  if (config.mode !== "embedded") {
    terminateEmbeddedBackend();
    return;
  }

  if (backendProcess) {
    return;
  }

  if (!config.repoRoot || !config.backendCwd) {
    lastStartupError =
      "Embedded mode could not locate the SentinelStream repository. Open Settings and set the repository root or backend working directory.";
    throw new Error(lastStartupError);
  }

  const backendEnv = {
    ...process.env,
    PYTHONPATH: buildPythonPath(config),
  };

  backendProcess = spawn(
    config.pythonExecutable,
    [
      "-m",
      "uvicorn",
      "analyst_console.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(config.port),
    ],
    {
      cwd: config.backendCwd,
      env: backendEnv,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    },
  );

  backendProcess.stdout.on("data", (chunk) => {
    process.stdout.write(`[embedded-console] ${chunk}`);
  });
  backendProcess.stderr.on("data", (chunk) => {
    process.stderr.write(`[embedded-console] ${chunk}`);
  });
  backendProcess.once("exit", (code, signal) => {
    if (!isQuitting) {
      lastStartupError = `Embedded analyst console exited unexpectedly (code=${code}, signal=${signal})`;
      showUnavailable(lastStartupError);
    }
    backendProcess = null;
  });
}

function terminateEmbeddedBackend() {
  if (!backendProcess) {
    return;
  }

  backendProcess.kill();
  backendProcess = null;
}

async function showLoading(config = getDesktopConfig()) {
  if (!mainWindow) {
    return;
  }

  await mainWindow.loadFile(path.join(APP_ROOT, "src", "loading.html"), {
    query: {
      mode: config.mode,
      targetUrl: config.targetUrl,
    },
  });
}

async function showUnavailable(errorMessage) {
  if (!mainWindow) {
    return;
  }

  const config = getDesktopConfig();
  await mainWindow.loadFile(path.join(APP_ROOT, "src", "unavailable.html"), {
    query: {
      mode: config.mode,
      targetUrl: config.targetUrl,
      errorMessage,
    },
  });
}

async function showSettings(message = "") {
  if (!mainWindow) {
    return;
  }

  const config = getDesktopConfig();
  await mainWindow.loadFile(path.join(APP_ROOT, "src", "settings.html"), {
    query: {
      mode: config.mode,
      targetUrl: config.targetUrl,
      port: String(config.port),
      startupTimeoutMs: String(config.startupTimeoutMs),
      pythonExecutable: config.pythonExecutable,
      repoRoot: config.repoRoot,
      backendCwd: config.backendCwd,
      discoveredRepoRoot: config.discoveredRepoRoot,
      message,
    },
  });
}

async function bootstrapDesktop() {
  const config = getDesktopConfig();
  await showLoading(config);

  try {
    ensureEmbeddedBackend(config);
    await waitForConsoleReady(config);

    if (!mainWindow) {
      return;
    }

    lastStartupError = null;
    await mainWindow.loadURL(config.targetUrl);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    lastStartupError = message;
    await showUnavailable(message);
  }
}

function sanitizeSettingsPayload(payload) {
  const payloadObject = payload && typeof payload === "object" ? payload : {};
  const discoveredRepoRoot = discoverRepoRoot() || "";
  const targetUrl = normalizeUrl(payloadObject.targetUrl, SETTINGS_DEFAULTS.targetUrl);
  const repoRoot = String(payloadObject.repoRoot || discoveredRepoRoot || "").trim();

  return {
    mode: String(payloadObject.mode || SETTINGS_DEFAULTS.mode).toLowerCase() === "embedded"
      ? "embedded"
      : "external",
    targetUrl,
    port: coerceInt(payloadObject.port, SETTINGS_DEFAULTS.port),
    startupTimeoutMs: coerceInt(
      payloadObject.startupTimeoutMs,
      SETTINGS_DEFAULTS.startupTimeoutMs,
    ),
    pythonExecutable: String(
      payloadObject.pythonExecutable || SETTINGS_DEFAULTS.pythonExecutable,
    ).trim(),
    repoRoot,
    backendCwd: String(payloadObject.backendCwd || repoRoot || "").trim(),
  };
}

ipcMain.handle("desktop:retry", async () => {
  await bootstrapDesktop();
  return { ok: lastStartupError === null, error: lastStartupError };
});

ipcMain.handle("desktop:open-external", async (_event, target) => {
  const url = target || getDesktopConfig().targetUrl;
  await shell.openExternal(url);
  return { ok: true };
});

ipcMain.handle("desktop:get-config", async () => getDesktopConfig());

ipcMain.handle("desktop:show-settings", async () => {
  await showSettings();
  return { ok: true };
});

ipcMain.handle("desktop:save-settings", async (_event, payload) => {
  const settings = sanitizeSettingsPayload(payload);
  savePersistedSettings(settings);
  terminateEmbeddedBackend();
  await bootstrapDesktop();
  return { ok: lastStartupError === null, error: lastStartupError, config: getDesktopConfig() };
});

app.whenReady().then(async () => {
  persistedSettings = loadPersistedSettings();
  createWindow();
  createMenu();
  await bootstrapDesktop();

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
      await bootstrapDesktop();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  isQuitting = true;
  terminateEmbeddedBackend();
});
