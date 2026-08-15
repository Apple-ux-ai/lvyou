import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const root = process.cwd();

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

describe("local TravelMate runtime scripts", () => {
  it("provides double-click start and stop launchers", () => {
    expect(read("start-travelmate.cmd")).toContain("Start-TravelMate.ps1");
    expect(read("stop-travelmate.cmd")).toContain("Stop-TravelMate.ps1");
  });

  it("starts hidden services, waits for health, and opens the home page", () => {
    const script = read("scripts/local/Start-TravelMate.ps1");

    expect(script).toContain("/api/health");
    expect(script).toContain("/pages/home.html");
    expect(script).toContain("-WindowStyle Hidden");
    expect(script).toContain("Invoke-WebRequest");
    expect(script).toContain("ConvertTo-Json");
    expect(script).toContain("Start-Process");
  });

  it("stops only recorded TravelMate command lines", () => {
    const script = read("scripts/local/Stop-TravelMate.ps1");

    expect(script).toContain("Win32_Process");
    expect(script).toContain("CommandLine");
    expect(script).toContain("uvicorn app.main:app");
    expect(script).toContain("http.server");
    expect(script).toContain("Stop-Process");
  });

  it("provides guarded backup and latest-restore launchers", () => {
    expect(read("backup-travelmate.cmd")).toContain("Backup-TravelMate.ps1");
    expect(read("restore-latest-travelmate.cmd")).toContain("Restore-TravelMate.ps1");

    const backupScript = read("scripts/local/Backup-TravelMate.ps1");
    expect(backupScript).toContain("local_data.py");
    expect(backupScript).toContain("backup");

    const restoreScript = read("scripts/local/Restore-TravelMate.ps1");
    expect(restoreScript).toContain("manifest.json");
    expect(restoreScript).toContain("Read-Host");
    expect(restoreScript).toContain("Stop-TravelMate.ps1");
    expect(restoreScript).toContain("local_data.py");
    expect(restoreScript).toContain("verify_backup.py");
    expect(restoreScript).toContain("read-only verification");
    expect(restoreScript).toContain("restore");
  });
});
