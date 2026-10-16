#!/usr/bin/env bash
#
# 打包脚本回归门禁（roadmap 1-1-4）。
#
# 守的对象是 `build-desktop.sh` 的 **unsigned 路径** —— 也就是默认那条没人签名的路径。
# 为什么单独守它：签名/公证那两条路各自有前置门控（缺证书就 exit 1），失败是显式的；
# 而 unsigned 路径没有任何前置检查，它一旦坏掉（资源漏进包、前端 chunk 没打进去、
# Go 二进制没更新）表现是「包打得出来、装上去白屏」。1-1-3 那个 prod 白屏坑正是这一类。
#
# 四道检查：
#   1. 契约 —— 必须是 unsigned 路径：NOTARIZE / SIGN_ID / SIGN_CERT 都不得设置
#      （这道门禁守的就是默认路径，带签名进来等于没守）；
#   2. 打包 —— `build-desktop.sh` 退出码 0，且产物是 dmg（--dir 模式下是 .app）；
#   3. 新鲜度 —— 产物 mtime 必须新于本次运行标记。dist/ 下常躺着上一次的 dmg，
#      只看「有没有产物」会把遗留物当成这次的产出（假阳性）；
#   4. 资源布局 —— 只 --dir 模式验：包内必须有可执行的 Go 二进制、前端 index.html
#      和至少一个 JS chunk。dmg 封好后看不到里面，所以布局断言走 --dir。
#
# 用法：
#   bash app/scripts/check-package.sh            # 完整 unsigned dmg 回归（慢，几分钟）
#   bash app/scripts/check-package.sh --dir      # 只出 .app（快），额外验资源布局
#
# 任一步失败即 exit 1，且打印失败的那一步。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EB_DIST="$APP_DIR/electron/dist"

MODE="dmg"
# shift 必须在每个分支之后执行：漏了它，`--dir` 会一直匹配同一个 $1 → 死循环。
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) MODE="dir" ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

echo "== 打包脚本回归门禁 (unsigned, mode=${MODE}) =="

# --- 1. unsigned 契约 --------------------------------------------------------
[ -z "${NOTARIZE:-}" ] || fail "NOTARIZE 已设置：本门禁只守 unsigned 路径，带签名的构建请单独验"
[ -z "${SIGN_ID:-}" ] || fail "SIGN_ID 已设置：本门禁只守 unsigned 路径，带签名的构建请单独验"
[ -z "${SIGN_CERT:-}" ] || fail "SIGN_CERT 已设置：本门禁只守 unsigned 路径，带签名的构建请单独验"
[ -f "$APP_DIR/scripts/build-desktop.sh" ] || fail "找不到 build-desktop.sh"
pass "契约：unsigned 路径（NOTARIZE/SIGN_ID/SIGN_CERT 均未设置）"

# 本次运行标记：产物必须比它新，否则就是上一次的遗留物。
# 不用 `touch`（本机 shim 会拦），不用 rm 清旧产物（同上）。
MARKER="$(mktemp 2>/dev/null || true)"
[ -n "$MARKER" ] || fail "无法创建运行标记（mktemp 失败）"

# --- 2. 打包 -----------------------------------------------------------------
echo "-- build-desktop.sh $( [ "$MODE" = dir ] && echo --dir )"
if [ "$MODE" = "dir" ]; then
  bash "$APP_DIR/scripts/build-desktop.sh" --dir || fail "build-desktop.sh --dir 退出码非 0"
else
  bash "$APP_DIR/scripts/build-desktop.sh" || fail "build-desktop.sh 退出码非 0"
fi

# --- 3. 产物 + 新鲜度 --------------------------------------------------------
if [ "$MODE" = "dir" ]; then
  ARTIFACT="$(find "$EB_DIST" -maxdepth 2 -name "ZWorkbench*.app" -print 2>/dev/null | sort | head -1 || true)"
else
  ARTIFACT="$(find "$EB_DIST" -maxdepth 2 \
    \( -name "ZWorkbench*.dmg" -o -name "ZWorkbench*.exe" -o -name "ZWorkbench*.AppImage" \) -print 2>/dev/null | sort | head -1 || true)"
fi
[ -n "$ARTIFACT" ] || fail "electron/dist 下未找到 ZWorkbench 产物（mode=${MODE}）"
[ -s "$ARTIFACT" ] || fail "产物为空：$ARTIFACT"

NEWER="$(find "$ARTIFACT" -newer "$MARKER" -print 2>/dev/null || true)"
[ -n "$NEWER" ] || fail "$ARTIFACT 不是本次构建产出（mtime 未新于运行标记，可能是遗留物）"
pass "产物：$(basename "$ARTIFACT") ($(du -sh "$ARTIFACT" | cut -f1), mtime=$(date -r "$ARTIFACT" '+%Y-%m-%d %H:%M:%S'))"

# --- 4. 资源布局（仅 --dir）--------------------------------------------------
if [ "$MODE" = "dir" ]; then
  GO_BIN="$ARTIFACT/Contents/Resources/bin/zworkbench-go"
  [ -f "$GO_BIN" ] || fail "包内缺少 Go 二进制：$GO_BIN"
  [ -x "$GO_BIN" ] || fail "包内 Go 二进制不可执行：$GO_BIN"
  pass "资源布局：Contents/Resources/bin/zworkbench-go 存在且可执行"
  [ -f "$ARTIFACT/Contents/Resources/web/dist/index.html" ] || fail "包内缺少 web/dist/index.html"
  JS_COUNT="$(find "$ARTIFACT/Contents/Resources/web/dist/assets" -type f -name '*.js' 2>/dev/null | wc -l | tr -d ' ')"
  [ "$JS_COUNT" -gt 0 ] || fail "包内缺少前端 JS chunk（index.html 会引用不存在的哈希 → 白屏）"
  pass "资源布局：web/dist/index.html + $JS_COUNT 个 JS chunk 已入包"
else
  echo "SKIP: 资源布局断言（dmg 模式下看不到包内；需要请用 --dir 跑）"
fi

echo "== 打包脚本回归门禁 ALL PASS =="
