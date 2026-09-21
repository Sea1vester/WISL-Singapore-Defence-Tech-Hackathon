#!/usr/bin/env node
// Vendors the Cesium build so the replay does not depend on the cesium.com CDN.
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const VERSION = "1.125";
const URL = `https://github.com/CesiumGS/cesium/releases/download/${VERSION}/Cesium-${VERSION}.zip`;
const DEST = path.join(__dirname, "..", "public", "cesium");

if (fs.existsSync(path.join(DEST, "Cesium.js"))) {
  console.log(`cesium ${VERSION} already vendored at ${DEST}; nothing to do`);
  process.exit(0);
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cesium-"));
const zip = path.join(tmp, "cesium.zip");

console.log(`downloading ${URL}`);
execFileSync("curl", ["-fsSL", "-o", zip, URL], { stdio: "inherit" });

fs.mkdirSync(DEST, { recursive: true });
// Extract only Build/Cesium/** into public/cesium/.
execFileSync("unzip", ["-o", "-q", zip, "Build/Cesium/*", "-d", tmp]);
execFileSync("rsync", ["-a", `${tmp}/Build/Cesium/`, `${DEST}/`]);

let bytes = 0;
for (const entry of fs.readdirSync(DEST, { recursive: true, withFileTypes: true })) {
  if (entry.isFile()) bytes += fs.statSync(path.join(entry.parentPath, entry.name)).size;
}
fs.rmSync(tmp, { recursive: true, force: true });
console.log(`vendored cesium ${VERSION} -> ${DEST} (${(bytes / 1048576).toFixed(1)} MB)`);
