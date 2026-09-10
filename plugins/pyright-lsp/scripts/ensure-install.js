#!/usr/bin/env node
'use strict';
const { spawnSync } = require('child_process');

const BIN = 'pyright';
const PKGS = ['pyright'];

function isInstalled(bin) {
  const finder = process.platform === 'win32' ? 'where' : 'which';
  return spawnSync(finder, [bin], { stdio: 'ignore' }).status === 0;
}

if (isInstalled(BIN)) process.exit(0);

console.log(`[pyright-lsp] ${BIN} not found on PATH; installing...`);
const result = spawnSync('npm', ['install', '-g', ...PKGS], {
  stdio: 'inherit',
  shell: process.platform === 'win32',
});
if (result.status !== 0) {
  console.error(`[pyright-lsp] install failed (exit ${result.status}); LSP features unavailable this session.`);
}
process.exit(0);
