#!/usr/bin/env bash
#
# Go 测试门禁（roadmap 1-1-3）。
#
# 为什么要有这道门：`go test ./...` 之前只在人手敲的时候才跑，且没有时限。本仓在
# Python 侧吃过「全量套件挂死 9h42m」的亏（旧路线图 1-4），所以这道门的两条硬约束是
# **带时限**和**不靠缓存**：
#
#   * `-timeout` —— 超时即失败，而不是无限期挂着让人以为在跑；
#   * `-count=1` —— 不用测试结果缓存，避免「上次绿的」被当成「这次绿的」。
#
# 四道检查：
#   1. 预检 —— go 在 PATH、go.mod 就位；
#   2. `go vet ./...` —— 编译期能抓的问题先抓掉；
#   3. `go test ./... -count=1 -timeout <T>` —— 全绿，且限时；
#   4. 测试存在性回归 —— 已登记有测试的包，不允许悄悄变成零测试（删测试比写测试
#      容易得多，静默退化正是门禁要挡的事）。
#
# 「哪些包还没有测试」是 WARN 不是 FAIL：那是覆盖率缺口，由 1-1-5 单独跟踪，门禁
# 不假装它已经解决了。
#
# 用法：
#   bash app/scripts/check-go.sh                # 默认超时 180s
#   bash app/scripts/check-go.sh --timeout 60s  # 自定义单包超时
#
# 任一步失败即 exit 1，且打印失败的那一步。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TIMEOUT="180s"
# 两种写法都收：`--timeout 60s` 与 `--timeout=60s`。用 shift 遍历，是为了能消费
# 空格写法的下一个参数（`for arg in "$@"` 做不到）。
while [ $# -gt 0 ]; do
  case "$1" in
    --timeout)
      shift
      [ $# -gt 0 ] || { echo "--timeout 需要一个值（如 --timeout 60s）" >&2; exit 1; }
      TIMEOUT="$1"
      ;;
    --timeout=*)
      TIMEOUT="${1#--timeout=}"
      ;;
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

echo "== Go 测试门禁 (app) =="

# --- 1. 预检 -----------------------------------------------------------------
command -v go >/dev/null 2>&1 || fail "go 不在 PATH"
[ -f "$APP_DIR/go.mod" ] || fail "缺少 $APP_DIR/go.mod"
pass "预检：$(go version) + go.mod 就位（单包超时 ${TIMEOUT}）"

# --- 2. vet ------------------------------------------------------------------
echo "-- go vet ./..."
( cd "$APP_DIR" && go vet ./... ) || fail "go vet 有告警"
pass "go vet ./...：无告警"

# --- 3. 带时限的全量测试 -----------------------------------------------------
echo "-- go test ./... -count=1 -timeout ${TIMEOUT}"
( cd "$APP_DIR" && go test ./... -count=1 -timeout "$TIMEOUT" ) || fail "go test 未全绿（或超时 ${TIMEOUT}）"
pass "go test ./...：全绿（无缓存、限时 ${TIMEOUT}）"

# --- 4. 测试存在性回归 -------------------------------------------------------
# 这些包已登记有测试；任何一个变成零测试即为回归。新增有测试的包时把目录名加进来。
REGISTERED="buildguard api evidence webstatic"
for pkg in $REGISTERED; do
  dir="$APP_DIR/internal/$pkg"
  [ -d "$dir" ] || fail "登记有测试的包 internal/$pkg 不存在"
  hit="$(find "$dir" -type f -name '*_test.go' -print 2>/dev/null | head -1 || true)"
  [ -n "$hit" ] || fail "internal/$pkg 已登记有测试，但现在零测试文件（测试被删了？）"
done
pass "测试存在性回归：$(echo $REGISTERED | wc -w | tr -d ' ') 个登记包均有测试"

# --- 5. 覆盖率缺口（WARN，不是 FAIL）-----------------------------------------
MISSING="$(cd "$APP_DIR" && go list ./... 2>/dev/null | while read -r p; do
  dir="${p#github.com/jununfly/ZWorkbench/app/}"
  dir="${dir#github.com/jununfly/ZWorkbench/app}"
  if [ -n "$dir" ] && [ -d "$dir" ]; then
    if [ -z "$(find "$dir" -maxdepth 1 -type f -name '*_test.go' -print 2>/dev/null | head -1 || true)" ]; then
      echo "$p"
    fi
  fi
done || true)"
if [ -n "$MISSING" ]; then
  COUNT="$(printf '%s\n' "$MISSING" | grep -c . || true)"
  echo "WARN: $COUNT 个包仍无测试文件（覆盖率缺口，由 1-1-5 跟踪，本门禁不判失败）："
  printf '%s\n' "$MISSING" | sed 's/^/      - /'
fi

echo "== Go 测试门禁 ALL PASS =="
