#!/usr/bin/env node
/**
 * build-backend.js — 使用 PyInstaller 构建内置 Python 后端运行时
 *
 * @req SHALL-253
 *
 * 产物：desktop/build/backend/yuleosh-server/yuleosh-server[.exe]
 * 随后由 electron-builder 通过 extraResources 复制到 resources/backend。
 *
 * 注意：PyInstaller 产物与构建平台绑定。要为 macOS/Linux/Windows 分别构建，
 * 必须在对应操作系统上执行 `npm run build:backend`。
 *
 * 用法：
 *   node scripts/build-backend.js
 *   PYTHON=/path/to/python node scripts/build-backend.js
 */

'use strict';

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const DESKTOP_DIR = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(DESKTOP_DIR, '..');
const SRC_DIR = path.join(REPO_ROOT, 'src');
const ENTRY = path.join(__dirname, 'backend_entry.py');
const DIST_DIR = path.join(DESKTOP_DIR, 'build', 'backend');
const WORK_DIR = path.join(DESKTOP_DIR, 'build', '.pyinstaller');
const EXE_NAME = 'yuleosh-server';

function resolvePython() {
  const candidates = [
    process.env.PYTHON,
    process.platform === 'win32' ? 'python' : 'python3',
    'python',
  ].filter(Boolean);

  for (const candidate of candidates) {
    const probe = spawnSync(candidate, ['-c', 'import sys; print(sys.version_info[:2])'], {
      encoding: 'utf8',
    });
    if (probe.status === 0) {
      return candidate;
    }
  }
  throw new Error('未找到可用的 Python 3.10+，请通过 PYTHON 环境变量指定解释器');
}

function main() {
  if (!fs.existsSync(ENTRY)) {
    throw new Error(`入口脚本不存在: ${ENTRY}`);
  }
  if (!fs.existsSync(SRC_DIR)) {
    throw new Error(`Python 源码目录不存在: ${SRC_DIR}`);
  }

  const python = resolvePython();
  const check = spawnSync(python, ['-c', 'import PyInstaller'], { stdio: 'ignore' });
  if (check.status !== 0) {
    throw new Error(
      `PyInstaller 未安装。请先执行: ${python} -m pip install pyinstaller`
    );
  }

  fs.mkdirSync(DIST_DIR, { recursive: true });
  fs.mkdirSync(WORK_DIR, { recursive: true });

  const args = [
    '-m',
    'PyInstaller',
    '--noconfirm',
    '--clean',
    '--onedir',
    '--name', EXE_NAME,
    '--paths', SRC_DIR,
    '--distpath', DIST_DIR,
    '--workpath', WORK_DIR,
    '--specpath', WORK_DIR,
    '--collect-all', 'yuleosh',
    '--console',
    ENTRY,
  ];

  console.log(`[build-backend] python: ${python}`);
  console.log(`[build-backend] output: ${path.join(DIST_DIR, EXE_NAME)}`);

  const result = spawnSync(python, args, { stdio: 'inherit', cwd: DESKTOP_DIR });
  if (result.status !== 0) {
    throw new Error(`PyInstaller 构建失败，退出码 ${result.status}`);
  }

  const binaryName = process.platform === 'win32' ? `${EXE_NAME}.exe` : EXE_NAME;
  const binaryPath = path.join(DIST_DIR, EXE_NAME, binaryName);
  if (!fs.existsSync(binaryPath)) {
    throw new Error(`构建完成但未找到可执行文件: ${binaryPath}`);
  }

  const sizeMb = (fs.statSync(binaryPath).size / 1024 / 1024).toFixed(1);
  console.log(`[build-backend] OK ${binaryPath} (${sizeMb} MB)`);
}

try {
  main();
} catch (err) {
  console.error(`[build-backend] ERROR: ${err.message}`);
  process.exit(1);
}
