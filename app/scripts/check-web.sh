#!/usr/bin/env bash
#
# 前端生产构建门禁（roadmap 1-1-2）。
#
# 为什么要有这道门：1-5-7 交付时前端只做了「沿用既有模式、类型一致」的人工判断，
# `npm install` + Vite 生产构建从未在本机跑过（见该节点 notes）。dev 模式走硬编码
# 端口、不经过生产打包，所以 `api.ts` 那种「只打包后才暴露」的缺陷在 dev 下永远
# 看不见（prod 白屏坑即由此而来）。这道门把「前端能生产构建」变成一条可机械复跑
# 的命令，而不是一次性的口头结论。
#
# 四道检查：
#   1. 预检 —— node / npm / package-lock.json 就位（没有 lock 就没有可复现安装）；
#   2. 安装 —— `npm ci` 严格按 lock 安装（不是 `npm install`，后者会漂移）；
#   3. 类型 —— `tsc --noEmit` 全量类型检查；
#   4. 构建 —— `vite build` 产出 dist/index.html，且 mtime 新于本次运行标记（
#      防止把上一次的遗留产物当成这次的产出）；
#   5. 入库守卫 —— dist / node_modules 等构建产物必须被 gitignore 覆盖。
#
# 用法：
#   bash app/scripts/check-web.sh                 # 全跑（含 npm ci）
#   bash app/scripts/check-web.sh --skip-install  # 已装好依赖，只跑类型 + 构建
#
# 任一步失败即 exit 1，且打印失败的那一步。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WEB_DIR="$APP_DIR/web"
REPO_ROOT="$(cd "$APP_DIR/.." && pwd)"

SKIP_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --skip-install) SKIP_INSTALL=1 ;;
    -h|--help)
      sed -n '2,26p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

echo "== 前端生产构建门禁 (app/web) =="

# --- 1. 预检 -----------------------------------------------------------------
command -v node >/dev/null 2>&1 || fail "node 不在 PATH"
command -v npm >/dev/null 2>&1 || fail "npm 不在 PATH"
[ -f "$WEB_DIR/package.json" ] || fail "缺少 $WEB_DIR/package.json"
[ -f "$WEB_DIR/package-lock.json" ] || fail "缺少 package-lock.json：没有 lock 就没有可复现安装"
pass "预检：node $(node -v) / npm $(npm -v) + package-lock.json 就位"

# 本次运行标记：用 mktemp 拿时间戳，再用它判定产物是不是这次构建的。
# 不用 `touch`（本机 shim 会拦），也不用 rm 清理旧产物（同上）。
MARKER="$(mktemp 2>/dev/null || true)"
[ -n "$MARKER" ] || fail "无法创建运行标记（mktemp 失败）"

# --- 2. 安装 -----------------------------------------------------------------
if [ "$SKIP_INSTALL" -eq 1 ]; then
  echo "SKIP: npm ci（--skip-install）"
else
  echo "-- npm ci（严格按 lock 安装）"
  ( cd "$WEB_DIR" && npm ci --no-audit --no-fund ) || fail "npm ci 失败"
  pass "npm ci：依赖与 lock 一致"
fi
[ -x "$WEB_DIR/node_modules/.bin/tsc" ] || fail "node_modules/.bin/tsc 不存在，先跑安装"
[ -x "$WEB_DIR/node_modules/.bin/vite" ] || fail "node_modules/.bin/vite 不存在，先跑安装"

# --- 3. 类型检查 -------------------------------------------------------------
echo "-- tsc --noEmit"
( cd "$WEB_DIR" && ./node_modules/.bin/tsc --noEmit ) || fail "tsc --noEmit 有类型错误"
pass "tsc --noEmit：无类型错误"

# --- 4. 生产构建 -------------------------------------------------------------
echo "-- vite build"
( cd "$WEB_DIR" && ./node_modules/.bin/vite build ) || fail "vite build 失败"

INDEX="$WEB_DIR/dist/index.html"
[ -f "$INDEX" ] || fail "vite build 后仍无 $INDEX"

# 产物必须比本次运行标记新，否则就是上一次的遗留物被当成了这次的产出。
NEWER="$(find "$INDEX" -newer "$MARKER" -print 2>/dev/null || true)"
[ -n "$NEWER" ] || fail "$INDEX 不是本次构建产出（mtime 未新于运行标记）"
pass "vite build：产出 dist/index.html 且为本次构建"

ASSET_COUNT="$(find "$WEB_DIR/dist/assets" -type f -name '*.js' 2>/dev/null | wc -l | tr -d ' ')"
[ "$ASSET_COUNT" -gt 0 ] || fail "dist/assets 下没有 js 产物"
pass "vite build：dist/assets 下 $ASSET_COUNT 个 js 产物"

# --- 5. 入库守卫 -------------------------------------------------------------
for rel in app/web/dist app/web/node_modules app/electron/dist app/electron/node_modules app/bin; do
  if [ -e "$REPO_ROOT/$rel" ]; then
    git -C "$REPO_ROOT" check-ignore -q "$rel" || fail "$rel 未被 gitignore 覆盖（构建产物不得入库）"
  fi
done
pass "入库守卫：dist / node_modules / bin 均被 gitignore 覆盖"

echo "== 前端生产构建门禁 ALL PASS =="
