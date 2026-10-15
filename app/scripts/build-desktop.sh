#!/usr/bin/env bash
#
# 1-1-3：构建 ZWorkbench 桌面包。
#
#   产物布局（打包后）：
#     <app>/Contents/Resources/bin/zworkbench-go      Go 本地服务
#     <app>/Contents/Resources/web/dist/              前端产物（Go 托管）
#
# 用法：
#   scripts/build-desktop.sh          # 打当前平台完整安装包（macOS→dmg, Windows→nsis）
#   scripts/build-desktop.sh --dir    # 只产出未打包的 app 目录（快，用于验证资源布局）
#
# 签名/公证不在本切片（需用户证书）。macOS 出的是 unsigned dmg：
# 首次启动若被 XProtect 拦（"已阻止恶意软件并移到废纸篓"），用自签证书重签（见 README）。
# 自签切记不要加 --options runtime（会让 Electron 渲染进程 V8 无 JIT 权限而崩溃"意外退出"）；
# 只有走公证(notarize)时才配合 entitlements.plist 加 hardened runtime。
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="dist"
if [[ "${1:-}" == "--dir" ]]; then
  MODE="dir"
fi

echo "[build] app dir: ${APP_DIR}"

# ---- 1. 平台 → Go 目标 + electron-builder 参数 --------------------------------
case "$(uname -s)" in
  Darwin)
    GOOS_TARGET=darwin
    GOARCH_TARGET="$(uname -m)"          # arm64 | x64
    EB_PLATFORM=--mac
    EB_ARCH=--"${GOARCH_TARGET}"
    GO_BIN_NAME=zworkbench-go
    ;;
  MINGW*|MSYS*|CYGWIN*)
    GOOS_TARGET=windows
    GOARCH_TARGET=amd64
    EB_PLATFORM=--win
    EB_ARCH=--x64
    GO_BIN_NAME=zworkbench-go.exe
    ;;
  Linux)
    GOOS_TARGET=linux
    GOARCH_TARGET=amd64
    EB_PLATFORM=--linux
    EB_ARCH=--x64
    GO_BIN_NAME=zworkbench-go
    ;;
  *)
    echo "[build] 不支持的平台：$(uname -s)" >&2
    exit 1
    ;;
esac
echo "[build] target: ${GOOS_TARGET}/${GOARCH_TARGET} (${EB_PLATFORM} ${EB_ARCH})"

# ---- 2. Go 本地服务 ----------------------------------------------------------
cd "${APP_DIR}"
echo "[build] go build ..."
# 注意：受限环境（强制沙箱）下 go 可能因「无法删除临时构建目录」以非 0 退出，
# 但产物本身已经正确写出。因此不以 go 的退出码为准，改以「产物新于本次构建标记」
# 为准。这样既不误判失败，也不会拿上一次的旧二进制冒充本次构建成功。
# （不用 rm 清理旧产物：部分沙箱对 rm 有安全拦截。）
MARKER="bin/.build-marker"
: > "${MARKER}"
GOOS="${GOOS_TARGET}" GOARCH="${GOARCH_TARGET}" CGO_ENABLED=0 \
  go build -trimpath -o "bin/${GO_BIN_NAME}" ./cmd/server || true
if [[ ! -x "bin/${GO_BIN_NAME}" || "bin/${GO_BIN_NAME}" -ot "${MARKER}" ]]; then
  echo "[build] go build 失败：bin/${GO_BIN_NAME} 未生成或未更新" >&2
  exit 1
fi
echo "[build] go binary: bin/${GO_BIN_NAME} ($(du -h "bin/${GO_BIN_NAME}" | cut -f1))"
# go 在受限环境清理中断时会在 bin/ 留下 0 字节的 umask 探针文件（*-go-tmp-umask）；
# 不进包——由 package.json 的 extraResources filter 只放行二进制名来排除。

# ---- 3. 前端产物 ------------------------------------------------------------
cd "${APP_DIR}/web"
if [[ ! -d node_modules ]]; then
  echo "[build] npm install (web) ..."
  npm install
fi
# 同上：npm run build 在受限环境可能因收尾清理被拦而以非 0 退出，
# 以「dist/index.html 新于本次构建标记」为准。
WEB_MARKER=".build-marker"
: > "${WEB_MARKER}"
echo "[build] npm run build (web) ..."
npm run build || true
if [[ ! -f dist/index.html || dist/index.html -ot "${WEB_MARKER}" ]]; then
  echo "[build] 前端构建失败：web/dist/index.html 未生成或未更新" >&2
  exit 1
fi
# 额外校验：dist/index.html 引用了带哈希的 /assets/index-*.js；若构建只写了 index.html
# 却没产出 JS chunk（emptyOutDir:false 下，旧 index.html 引用了未生成的哈希），打包进
# dmg 后 Electron 加载到 404 脚本 → 整屏白且无报错。此处在源头拦截。
shopt -s nullglob
ASSET_JS=(dist/assets/*.js)
shopt -u nullglob
if [[ ${#ASSET_JS[@]} -eq 0 ]]; then
  echo "[build] 前端构建失败：dist/assets 下无 JS 产物（index.html 引用了未生成的 chunk）" >&2
  exit 1
fi
echo "[build] web dist ok ($(printf '%s\n' "${ASSET_JS[@]}" | wc -l | tr -d ' ') JS chunk(s))"

# ---- 4. Electron 壳 ---------------------------------------------------------
cd "${APP_DIR}/electron"
if [[ ! -d node_modules ]]; then
  echo "[build] npm install (electron) ..."
  npm install
fi

if [[ "${MODE}" == "dir" ]]; then
  echo "[build] electron-builder --dir ..."
  npx electron-builder --dir "${EB_PLATFORM}" "${EB_ARCH}" || true
else
  echo "[build] electron-builder ${EB_PLATFORM} ${EB_ARCH} ..."
  npx electron-builder "${EB_PLATFORM}" "${EB_ARCH}" || true
fi

# ---- 4b. 可选：自签证书重签（本地开发绕过 XProtect；非公证）-------------
# 触发： SIGN_CERT="ZWorkbench Dev" scripts/build-desktop.sh
# 关键：自签【不要】--options runtime（Electron 渲染进程 V8 需 JIT，hardened runtime
#       无对应 entitlement 会"意外退出"）。走公证时再用 entitlements.plist + runtime。
# 注：dmg 模式在 build 后才签 .app 无效（dmg 已封好），故 dmg 模式请改用
#     --dir 拿到 .app 后重签，或自行从 dmg 拷出 .app 再签。
if [[ -n "${SIGN_CERT:-}" ]]; then
  APP_BUNDLE="${APP_DIR}/electron/dist/mac-${GOARCH_TARGET}/ZWorkbench.app"
  if [[ ! -d "${APP_BUNDLE}" ]]; then
    echo "[build] 自签跳过：找不到 ${APP_BUNDLE}（dmg 模式请用 --dir，或自行从 dmg 拷出 .app 再签）" >&2
  else
    echo "[build] 自签（不含 hardened runtime）：${SIGN_CERT}"
    codesign --force --deep --sign "${SIGN_CERT}" "${APP_BUNDLE}"
    codesign --verify --deep --strict --verbose=2 "${APP_BUNDLE}" | head -5
    echo "[build] 自签完成。用此 .app（或 --dir 产物）即可本地启动。"
  fi
fi

# ---- 5. 证据摘要 ------------------------------------------------------------
# 只认 electron-builder 的最终产物（.dmg / .exe / .AppImage），或 --dir 模式下以
# productName 命名的 .app。注意不能拿 Electron.app 当证据：那是打包中途从
# node_modules/electron/dist 拷过来的原始壳，打包失败时它也会存在，会给出假阳性。
echo
echo "[build] ---- 产物证据 ----"
if [[ "${MODE}" == "dir" ]]; then
  PATTERN="-name *.app -o -name *.dmg -o -name *.exe -o -name *.AppImage"
else
  PATTERN="-name *.dmg -o -name *.exe -o -name *.AppImage"
fi
ARTIFACT="$(eval find "${APP_DIR}/electron/dist" -maxdepth 2 \( ${PATTERN} \) -print 2>/dev/null \
  | grep '/ZWorkbench' | sort | head -1)"
if [[ -z "${ARTIFACT}" ]]; then
  echo "[build] 打包失败：electron/dist 下未找到 ZWorkbench 的 dmg/exe/AppImage 产物" >&2
  echo "[build] （dist 下现有内容：）" >&2
  find "${APP_DIR}/electron/dist" -maxdepth 2 -print 2>/dev/null | head -20 >&2
  exit 1
fi
echo "[build] artifact: ${ARTIFACT} ($(du -sh "${ARTIFACT}" | cut -f1))"
echo
echo "[build] 完成。"
echo "[build] 提示：macOS 未公证包首次启动被 Gatekeeper 拦截（文案含『无法验证是否含恶意软件』，非真判毒）。"
echo "[build]   打开方式：右键(Control+点击) ${ARTIFACT} → 『打开』即可；不要先 xattr -dr 删隔离标记。"
echo "[build]   Windows 未签名包：首次从『Windows 安全中心 → 更多 → 仍要运行』放行。"
