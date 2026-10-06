#!/usr/bin/env node
'use strict';
const { spawnSync, spawn } = require('child_process');
const path = require('path');

const TAG = '[table-talk]';
const IS_WIN = process.platform === 'win32';
const MCP_SCRIPT = path.join(__dirname, 'sql-explorer.py');

function isInstalled(bin) {
  const finder = IS_WIN ? 'where' : 'which';
  return spawnSync(finder, [bin], { stdio: 'ignore' }).status === 0;
}

function run(label, cmd, args, opts) {
  console.log(`${TAG} ${label}...`);
  const result = spawnSync(cmd, args, { stdio: 'inherit', timeout: 300000, ...opts });
  if (result.error || result.status !== 0) {
    console.error(`${TAG} ${label} failed${result.status != null ? ` (exit ${result.status})` : ''}.`);
    return false;
  }
  return true;
}

function main() {
  const hadUv = isInstalled('uv');

  if (!hadUv) {
    // Official non-interactive standalone installer. No admin rights needed;
    // installs to %USERPROFILE%\.local\bin and updates the user PATH via the
    // registry, which this already-running process will not see. The steps
    // below that depend on uv are skipped this run and will succeed on the
    // next SessionStart once a new shell picks up the refreshed PATH.
    run(
      'uv not found; installing',
      'powershell.exe',
      ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', 'irm https://astral.sh/uv/install.ps1 | iex']
    );
    process.exit(0);
  }

  run('warming up the sql-explorer-mcp environment', 'uv', [
    'sync', '--quiet', '--locked', '--script', MCP_SCRIPT,
  ]);

  const hadAz = isInstalled('az');

  if (!hadAz) {
    // Reuses the uv dependency the plugin already needs instead of the
    // Azure CLI MSI/winget path, so no admin rights or separate installer
    // are needed. az won't be resolvable in this process's PATH until the
    // next SessionStart, so the sign-in check below is skipped this run.
    const installed = run('az cli not found; installing', 'uv', ['tool', 'install', 'azure-cli']);
    if (installed) run('updating PATH for az cli', 'uv', ['tool', 'update-shell']);
    process.exit(0);
  }

  const signedIn = spawnSync('az', ['account', 'show', '--only-show-errors'], {
    stdio: 'ignore',
    shell: IS_WIN,
  }).status === 0;

  if (!signedIn) {
    console.log(`${TAG} not signed in to Azure; opening 'az login' in the background...`);
    const login = spawn('az', ['login'], { detached: true, stdio: 'ignore', shell: IS_WIN });
    login.unref();
  }

  process.exit(0);
}

try {
  main();
} catch (err) {
  console.error(`${TAG} unexpected error: ${err && err.message}`);
  process.exit(0);
}
