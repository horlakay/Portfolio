"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("sentinelDesktop", {
  retry: () => ipcRenderer.invoke("desktop:retry"),
  openExternal: (targetUrl) => ipcRenderer.invoke("desktop:open-external", targetUrl),
  getConfig: () => ipcRenderer.invoke("desktop:get-config"),
  showSettings: () => ipcRenderer.invoke("desktop:show-settings"),
  saveSettings: (payload) => ipcRenderer.invoke("desktop:save-settings", payload),
});
