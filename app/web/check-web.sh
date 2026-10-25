#!/usr/bin/env bash
# ZWorkbench Web 构建门禁（重建自 zj-ui 约定）：npm ci → tsc --noEmit → eslint(零 error) → vite build
# 设计原则：标记文件用 `: >` 建立（不碰 touch/rm），构建产物落 dist/。
set -e
cd "$(dirname "$0")"

echo "[check-web] npm ci ..."
npm ci

echo "[check-web] tsc --noEmit ..."
./node_modules/.bin/tsc --noEmit

echo "[check-web] eslint (a11y gate: G-V4) ..."
./node_modules/.bin/eslint .

echo "[check-web] vite build ..."
./node_modules/.bin/vite build

# 用 : > 建立/刷新构建标记（mtime 判据，不删除任何文件）
: > .zw-web-built

echo "[check-web] OK"
