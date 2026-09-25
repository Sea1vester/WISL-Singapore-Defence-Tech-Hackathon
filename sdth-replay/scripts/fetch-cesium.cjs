#!/usr/bin/env node
// Vendors the Cesium build so the replay does not depend on the cesium.com CDN.
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const VERSION = "1.125";
const URL = `https://github.com/CesiumGS/cesium/releases/download/${VERSION}/Cesium-${VERSION}.zip`;
const DEST = path.join(__dirname, "..", "public", "cesium");

if (["Cesium.js", "Workers", "Assets", "Widgets/widgets.css"].every(name => fs.existsSync(path.join(DEST, name)))) {
  console.log(`cesium ${VERSION} already vendored at ${DEST}; nothing to do`);
  process.exit(0);
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cesium-"));
const zip = path.join(tmp, "cesium.zip");

try {
  console.log(`downloading ${URL}`);
  execFileSync("curl", ["-fsSL", "-o", zip, URL], { stdio: "inherit" });

  fs.mkdirSync(DEST, { recursive: true });
  // Extract only Build/Cesium/** into public/cesium/.
  if (process.platform === "win32") {
    execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command",
      "$ErrorActionPreference = 'Stop'; Expand-Archive -LiteralPath $env:WISL_CESIUM_ARCHIVE -DestinationPath $env:WISL_CESIUM_TEMP -Force"], {
      stdio: "inherit",
      env: { ...process.env, WISL_CESIUM_ARCHIVE: zip, WISL_CESIUM_TEMP: tmp },
    });
  } else {
    execFileSync("unzip", ["-o", "-q", zip, "Build/Cesium/*", "-d", tmp]);
  }
  fs.cpSync(path.join(tmp, "Build", "Cesium"), DEST, { recursive: true });

  let bytes = 0;
  for (const entry of fs.readdirSync(DEST, { recursive: true, withFileTypes: true })) {
    if (entry.isFile()) bytes += fs.statSync(path.join(entry.parentPath, entry.name)).size;
  }
  console.log(`vendored cesium ${VERSION} -> ${DEST} (${(bytes / 1048576).toFixed(1)} MB)`);
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
