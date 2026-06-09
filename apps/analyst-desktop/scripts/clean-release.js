"use strict";

const fs = require("node:fs");
const path = require("node:path");

const releaseDir = path.resolve(__dirname, "..", "release");

fs.rmSync(releaseDir, { recursive: true, force: true });
console.log(`Cleaned ${releaseDir}`);
