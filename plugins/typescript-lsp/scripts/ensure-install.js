#!/usr/bin/env node
'use strict';
const { spawnSync } = require('child_process');
const path = require('path');

const BIN = 'typescript-language-server';
const PKGS = ['typescript-language-server', 'typescript@^5.9'];

function isInstalled(bin) {
  const finder = process.platform === 'win32' ? 'where' : 'which';
  return spawnSync(finder, [bin], { stdio: 'ignore' }).status === 0;
}

function hasCompatibleTypescript() {
  const root = spawnSync('npm', ['root', '-g'], { shell: process.platform === 'win32' });
  if (root.status !== 0) return false;
  const globalRoot = root.stdout.toString().trim();
  let pkg;
  try {
    pkg = require(path.join(globalRoot, 'typescript', 'package.json'));
  } catch {
    return false;
  }
  const major = parseInt(String(pkg.version).split('.')[0], 10);
  return Number.isInteger(major) && major < 7;
}

if (isInstalled(BIN) && hasCompatibleTypescript()) process.exit(0);

console.log(`[typescript-lsp] installing/upgrading ${PKGS.join(', ')}...`);
const result = spawnSync('npm', ['install', '-g', ...PKGS], {
  stdio: 'inherit',
  shell: process.platform === 'win32',
});
if (result.status !== 0) {
  console.error(`[typescript-lsp] install failed (exit ${result.status}); LSP features unavailable this session.`);
}
process.exit(0);
