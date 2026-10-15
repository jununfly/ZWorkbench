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
#   NOTARIZE=1 DEV_ID_APP="Developer ID Application: ..." APPLE_KEYCHAIN_PROFILE=zw-notary \
#     scripts/build-desktop.sh        # 公证版（分发给他人；环境变量契约见第 1b 节）
#   SIGN_ID="ZWorkbench Dev" scripts/build-desktop.sh
#                                     # 只签名、不公证（打包时即签，含 hardened runtime +
#                                     # entitlements + 内嵌二进制纳签）。用于两段式验收：
#                                     # 先单独验签名，再上公证，便于定位失败环节。
#
# 签名/公证：默认关（出 unsigned dmg）。
#   - 本地自用：macOS 首次启动被 Gatekeeper 拦（"无法验证是否含恶意软件"），右键(Control+点击)→打开
#     一次性放行即可。自签【过不了 Gatekeeper】（只认 Apple Developer ID），仅个别 EDR 场景有用。
#   - 两套自签入口，别混用：
#       SIGN_ID   = 走 electron-builder 签名路径（打包时即签，hardened runtime + entitlements +
#                   内嵌二进制纳签）——**推荐**，dmg 里的 .app 就是签好的。
#       SIGN_CERT = 旧入口，打包**之后**用 `codesign --force --deep` 补签，**仅 --dir 模式有效**；
#                   dmg 模式下签的是中间产物、包内仍是 unsigned（脚本会明确告警）。
#   - 分发给他人才需要公证：NOTARIZE=1（见第 1b 节的环境变量契约）。
#   - XProtect 是另一层（Apple 内置杀毒，按特征库判定，无用户侧绕过）。公证能否解开 XProtect 误杀
#     取决于命中类型，不在本脚本保证范围内。
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

# ---- 1b. 公证门控预检（默认关；NOTARIZE=1 打开）-----------------------------
# 放在这里（而非打包前）是为了【快速失败】：缺证书/缺凭证时不做无谓的 go build + npm build。
# 前置：① 付费 Apple Developer Program，钥匙串里有 "Developer ID Application: <名字> (<TEAMID>)"
#       ② 公证凭证（三选一；推荐 A，凭证不落命令行历史）：
#          A) APPLE_KEYCHAIN_PROFILE=<profile>
#             先存：xcrun notarytool store-credentials <profile> \
#                     --apple-id <AppleID> --team-id <TEAMID> --password <App专用密码>
#          B) APPLE_ID + APPLE_APP_SPECIFIC_PASSWORD + APPLE_TEAM_ID
#          C) APPLE_API_KEY + APPLE_API_KEY_ID + APPLE_API_ISSUER
# 打开后发生什么：
#   以 DEV_ID_APP 签名（hardened runtime + electron/build/entitlements.mac.plist，并显式纳入
#   内嵌 Go 二进制）→ electron-builder 送公证并 staple .app → dmg 产出后再送公证 + staple dmg（第 6 节）。
# 注意：公证解的是 Gatekeeper；它是 XProtect 误杀的【可能】解法之一，不保证。
NOTARIZE="${NOTARIZE:-0}"
SIGN_ID="${SIGN_ID:-}"
CRED_KIND=""
DEV_ID_APP="${DEV_ID_APP:-}"
if [[ "${NOTARIZE}" == "1" ]]; then
  if [[ "${GOOS_TARGET}" != "darwin" ]]; then
    echo "[build] NOTARIZE=1 仅支持 macOS（当前 ${GOOS_TARGET}/${GOARCH_TARGET}）" >&2
    exit 1
  fi
  if [[ -n "${SIGN_CERT:-}" ]]; then
    echo "[build] NOTARIZE=1 与 SIGN_CERT 互斥：自签会改写签名、使公证票据失效" >&2
    exit 1
  fi
  if [[ -z "${DEV_ID_APP}" ]]; then
    echo "[build] NOTARIZE=1 需要 DEV_ID_APP=\"Developer ID Application: <名字> (<TEAMID>)\"" >&2
    exit 1
  fi
  CODESIGN_IDS="$(security find-identity -v -p codesigning 2>/dev/null || true)"
  case "${CODESIGN_IDS}" in
    *"${DEV_ID_APP}"*) ;;
    *)
      echo "[build] 钥匙串找不到签名证书：${DEV_ID_APP}" >&2
      echo "[build] 当前 codesigning 身份：" >&2
      printf '%s\n' "${CODESIGN_IDS}" | sed 's/^/  /' >&2
      exit 1
      ;;
  esac
  if [[ -n "${APPLE_KEYCHAIN_PROFILE:-}" ]]; then
    CRED_KIND="keychain"
  elif [[ -n "${APPLE_ID:-}" && -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
    CRED_KIND="appleid"
  elif [[ -n "${APPLE_API_KEY:-}" && -n "${APPLE_API_KEY_ID:-}" && -n "${APPLE_API_ISSUER:-}" ]]; then
    CRED_KIND="apikey"
  else
    echo "[build] NOTARIZE=1 缺少公证凭证（三选一）：" >&2
    echo "[build]   A) APPLE_KEYCHAIN_PROFILE" >&2
    echo "[build]   B) APPLE_ID + APPLE_APP_SPECIFIC_PASSWORD + APPLE_TEAM_ID" >&2
    echo "[build]   C) APPLE_API_KEY + APPLE_API_KEY_ID + APPLE_API_ISSUER" >&2
    exit 1
  fi
  command -v xcrun >/dev/null 2>&1 || { echo "[build] 找不到 xcrun（需 Xcode Command Line Tools）" >&2; exit 1; }
  xcrun --find notarytool >/dev/null 2>&1 || { echo "[build] notarytool 不可用（需 Xcode 13+）" >&2; exit 1; }
  xcrun --find stapler >/dev/null 2>&1 || { echo "[build] stapler 不可用" >&2; exit 1; }
  ENTITLEMENTS="${APP_DIR}/electron/build/entitlements.mac.plist"
  [[ -f "${ENTITLEMENTS}" ]] || { echo "[build] 缺少 entitlements：${ENTITLEMENTS}" >&2; exit 1; }
  echo "[build] 公证已启用：cert=${DEV_ID_APP} / cred=${CRED_KIND} / entitlements=${ENTITLEMENTS}"
fi

# ---- 1c. 只签名门控（SIGN_ID；不带公证）--------------------------------------
# 触发：SIGN_ID="ZWorkbench Dev" scripts/build-desktop.sh
# 语义：走 electron-builder 的 identity 路径 → 在**打包时**签名（hardened runtime +
#       build/entitlements.mac.plist + 显式纳入内嵌 Go 二进制），**不送 Apple 公证**。
# 价值：把「签名链路正确」与「Apple 判定通过」解耦。公证首跑失败时，先用 SIGN_ID 排掉
#       签名侧问题（内嵌二进制漏签 / entitlements 未生效 / 身份取不到），再上 NOTARIZE=1。
# 与 NOTARIZE / SIGN_CERT 均互斥，理由见下方报错文案。
if [[ -n "${SIGN_ID}" ]]; then
  if [[ "${GOOS_TARGET}" != "darwin" ]]; then
    echo "[build] SIGN_ID 仅支持 macOS（当前 ${GOOS_TARGET}/${GOARCH_TARGET}）" >&2
    exit 1
  fi
  if [[ "${NOTARIZE}" == "1" ]]; then
    echo "[build] SIGN_ID 与 NOTARIZE=1 互斥：公证自带 identity，二选一即可" >&2
    exit 1
  fi
  if [[ -n "${SIGN_CERT:-}" ]]; then
    echo "[build] SIGN_ID 与 SIGN_CERT 互斥：两套签名会互相覆盖（前者打包时签、后者打包后补签）" >&2
    exit 1
  fi
  CODESIGN_IDS="$(security find-identity -v -p codesigning 2>/dev/null || true)"
  case "${CODESIGN_IDS}" in
    *"${SIGN_ID}"*) ;;
    *)
      echo "[build] 钥匙串找不到签名身份：${SIGN_ID}" >&2
      echo "[build] 当前 codesigning 身份：" >&2
      printf '%s\n' "${CODESIGN_IDS}" | sed 's/^/  /' >&2
      exit 1
      ;;
  esac
  echo "[build] 只签名（不公证）已启用：identity=${SIGN_ID}"
fi

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

# 公证门控的状态（NOTARIZE / CRED_KIND / DEV_ID_APP / ENTITLEMENTS）已在第 1b 节预检完毕。
# 统一入口：$@ 透传 electron-builder 的 config 覆盖项（空参数安全，不依赖 bash>=4.4 的空数组展开）
run_eb() {
  if [[ "${MODE}" == "dir" ]]; then
    echo "[build] electron-builder --dir ${EB_PLATFORM} ${EB_ARCH} $* ..."
    npx electron-builder --dir "${EB_PLATFORM}" "${EB_ARCH}" "$@" || true
  else
    echo "[build] electron-builder ${EB_PLATFORM} ${EB_ARCH} $* ..."
    npx electron-builder "${EB_PLATFORM}" "${EB_ARCH}" "$@" || true
  fi
}

if [[ "${CRED_KIND}" == "appleid" ]]; then
  # teamId 必须显式下发：electron-builder 只从 config 读 teamId（不读 APPLE_TEAM_ID 环境变量）。
  # 其余凭证走 env 即可；且不能与 keychain/apiKey 同时给 teamId，否则 @electron/notarize 判定凭证冲突。
  run_eb "--config.mac.identity=${DEV_ID_APP}" "--config.mac.notarize.teamId=${APPLE_TEAM_ID}"
elif [[ "${NOTARIZE}" == "1" ]]; then
  run_eb "--config.mac.identity=${DEV_ID_APP}"
elif [[ -n "${SIGN_ID}" ]]; then
  # 只覆盖 identity：hardenedRuntime / entitlements / binaries 均取自 package.json，
  # 在打包时生效（dmg 内的 .app 即是签好的，不像 SIGN_CERT 那样签在打包之后）。
  run_eb "--config.mac.identity=${SIGN_ID}"
else
  run_eb
fi

# ---- 4b. 可选：自签证书重签（仅个别 EDR 场景；【不能】绕过 Gatekeeper/XProtect）-----
# 触发： SIGN_CERT="ZWorkbench Dev" scripts/build-desktop.sh
# 与 NOTARIZE=1 互斥（自签会改写签名、使公证票据失效），上方已硬拦。
# 关键：自签【不要】--options runtime（Electron 渲染进程 V8 需 JIT，hardened runtime
#       无对应 entitlement 会"意外退出"）。走公证时再用 build/entitlements.mac.plist + runtime。
# 注：dmg 模式在 build 后才签 .app 无效（dmg 已封好），故 dmg 模式请改用
#     --dir 拿到 .app 后重签，或自行从 dmg 拷出 .app 再签。
if [[ -n "${SIGN_CERT:-}" ]]; then
  APP_BUNDLE="${APP_DIR}/electron/dist/mac-${GOARCH_TARGET}/ZWorkbench.app"
  if [[ ! -d "${APP_BUNDLE}" ]]; then
    echo "[build] 自签跳过：找不到 ${APP_BUNDLE}（dmg 模式请用 --dir，或自行从 dmg 拷出 .app 再签）" >&2
  else
    # 签名发生在打包之后：dmg 模式下包内那份 .app 早已封好，此处只签得到中间产物。
    # 不做静默成功——明确告知包内仍是 unsigned，避免误以为 dmg 已签。
    if [[ "${MODE}" != "dir" ]]; then
      echo "[build] !! SIGN_CERT 在安装包模式下【不改变包内签名】：本步签的只是打包中间产物" >&2
      echo "[build]    ${APP_BUNDLE}" >&2
      echo "[build]    这是临时目录，产出的 dmg 里那份 .app 仍是 unsigned。" >&2
      echo "[build]    要「打包即签名」（dmg 内就是签好的）请改用 SIGN_ID=${SIGN_CERT}" >&2
    fi
    echo "[build] 自签（不含 hardened runtime）：${SIGN_CERT}"
    codesign --force --deep --sign "${SIGN_CERT}" "${APP_BUNDLE}"
    codesign --verify --deep --strict --verbose=2 "${APP_BUNDLE}" | head -5
    echo "[build] 自签完成（--dir 模式下该产物即最终产物，可直接本地启动）。"
  fi
fi

# ---- 5. 证据摘要 ------------------------------------------------------------
# 只认 electron-builder 的最终产物（.dmg / .exe / .AppImage），或 --dir 模式下以
# productName 命名的 .app。注意不能拿 Electron.app 当证据：那是打包中途从
# node_modules/electron/dist 拷过来的原始壳，打包失败时它也会存在，会给出假阳性。
echo
echo "[build] ---- 产物证据 ----"
# 注意：这里【不能】用 eval + $PATTERN 字符串去拼 find 的参数。`\(` 在传进 eval 之前就被
# shell 还原成裸 `(`，eval 二次解析时报 "syntax error near unexpected token '('"；而 stderr
# 又被 2>/dev/null 吞掉，于是 find 静默返回空 → ARTIFACT 赋值在 set -e 下直接终止脚本，表现
# 为「打印完『产物证据』就无声退出 1」。已改为直接写死 find 参数（模式名内联，顺带省掉 grep）。
# 产物按模式各认一类，且【按优先级取】而不是丢进同一个 sort 里比字典序：
# --dir 的产物是 .app，但 dist 下常还躺着上一次的 dmg；路径上 dist/ZWorkbench-*.dmg
# 排在 dist/mac-arm64/ZWorkbench.app 之前，sort|head -1 会把旧 dmg 当成本次产物（假阳性）。
if [[ "${MODE}" == "dir" ]]; then
  ARTIFACT="$(find "${APP_DIR}/electron/dist" -maxdepth 2 -name "ZWorkbench*.app" -print 2>/dev/null | sort | head -1 || true)"
  if [[ -z "${ARTIFACT}" ]]; then
    ARTIFACT="$(find "${APP_DIR}/electron/dist" -maxdepth 2 -name "ZWorkbench*.dmg" -print 2>/dev/null | sort | head -1 || true)"
  fi
else
  ARTIFACT="$(find "${APP_DIR}/electron/dist" -maxdepth 2 \
    \( -name "ZWorkbench*.dmg" -o -name "ZWorkbench*.exe" -o -name "ZWorkbench*.AppImage" \) -print 2>/dev/null | sort | head -1 || true)"
fi
if [[ -z "${ARTIFACT}" ]]; then
  echo "[build] 打包失败：electron/dist 下未找到本次 ZWorkbench 产物（模式=${MODE}）" >&2
  echo "[build] （dist 下现有内容：）" >&2
  find "${APP_DIR}/electron/dist" -maxdepth 2 -print 2>/dev/null | head -20 >&2
  exit 1
fi
echo "[build] artifact: ${ARTIFACT} ($(du -sh "${ARTIFACT}" | cut -f1), mtime=$(date -r "${ARTIFACT}" '+%Y-%m-%d %H:%M:%S'))"

# ---- 6. 公证后置：dmg 送公证 + staple + 机械校验（仅 NOTARIZE=1）--------------
# 为什么还要这一步：electron-builder 的 notarize 只覆盖 .app（第 4 步已做并 staple），
# dmg 本身不在其中。dmg 不公证时，用户挂载后打开 app 仍可用（app 有 staple 票据），
# 但拿不到"安装镜像已验证"的体验；此处补上，并做三道机械校验留证。
if [[ "${NOTARIZE}" == "1" ]]; then
  case "${ARTIFACT}" in
    *.dmg)
      echo "[build] notarytool submit (dmg, 需等待 Apple 回执) ..."
      if [[ -n "${APPLE_KEYCHAIN_PROFILE:-}" ]]; then
        xcrun notarytool submit "${ARTIFACT}" --keychain-profile "${APPLE_KEYCHAIN_PROFILE}" --wait
      elif [[ -n "${APPLE_API_KEY:-}" ]]; then
        xcrun notarytool submit "${ARTIFACT}" --key "${APPLE_API_KEY}" --key-id "${APPLE_API_KEY_ID}" --issuer "${APPLE_API_ISSUER}" --wait
      else
        xcrun notarytool submit "${ARTIFACT}" --apple-id "${APPLE_ID}" --password "${APPLE_APP_SPECIFIC_PASSWORD}" --team-id "${APPLE_TEAM_ID}" --wait
      fi
      xcrun stapler staple "${ARTIFACT}"
      xcrun stapler validate "${ARTIFACT}"
      ;;
    *)
      echo "[build] 非 dmg 产物（$(basename "${ARTIFACT}")），跳过 dmg 公证；.app 已由 electron-builder 公证并 staple。"
      ;;
  esac

  APP_BUNDLE="$(find "${APP_DIR}/electron/dist" -maxdepth 2 -name ZWorkbench.app -print 2>/dev/null | head -1)"
  if [[ -n "${APP_BUNDLE}" ]]; then
    echo "[build] 校验 .app 签名链 / staple 票据 / Gatekeeper 评估："
    codesign --verify --deep --strict --verbose=2 "${APP_BUNDLE}" \
      && echo "[build]   codesign verify: OK" \
      || { echo "[build]   codesign verify 失败" >&2; exit 1; }
    xcrun stapler validate "${APP_BUNDLE}" \
      && echo "[build]   staple validate: OK" \
      || { echo "[build]   staple 校验失败（公证未生效或签名被改写）" >&2; exit 1; }
    # spctl 仅作参考：离线/未登录 Apple 服务的机器上可能仍打印 rejected
    spctl --assess --type exec -vv "${APP_BUNDLE}" 2>&1 | tail -2 || true
  fi
fi

# ---- 6b. 只签名模式的机械校验（SIGN_ID）--------------------------------------
# 目的：把「签名链路」的证据在构建时就打出来，而不是靠人事后手敲 codesign。
# 三条断言各自对应一个真实会踩的坑：签名链不完整 / entitlements 未生效 / 内嵌 Go 二进制漏签
# （最后一条是公证失败的头号原因）。
if [[ -n "${SIGN_ID}" ]]; then
  APP_BUNDLE="$(find "${APP_DIR}/electron/dist" -maxdepth 2 -name ZWorkbench.app -print 2>/dev/null | head -1)"
  if [[ -n "${APP_BUNDLE}" ]]; then
    echo "[build] 校验签名（只签名模式）："
    codesign --verify --deep --strict --verbose=2 "${APP_BUNDLE}" >/dev/null 2>&1 \
      && echo "[build]   codesign verify: OK（含内嵌二进制）" \
      || { echo "[build]   codesign verify 失败：签名链不完整" >&2; exit 1; }
    RT_FLAG="$(codesign -dv "${APP_BUNDLE}" 2>&1 | grep -o 'flags=0x[0-9a-f]*(runtime)' || true)"
    echo "[build]   hardened runtime: ${RT_FLAG:-未启用（entitlements 将不生效）}"
    echo "[build]   entitlements（com.apple.security.*）："
    codesign -d --entitlements - "${APP_BUNDLE}" 2>/dev/null \
      | grep -o 'com\.apple\.security\.[a-z.-]*' | sort -u | sed 's/^/     /' || true
    GO_BIN="${APP_BUNDLE}/Contents/Resources/bin/zworkbench-go"
    if [[ -f "${GO_BIN}" ]]; then
      if codesign -dv "${GO_BIN}" >/dev/null 2>&1; then
        echo "[build]   内嵌 Go 二进制: 已签名"
      else
        echo "[build]   内嵌 Go 二进制: 未签名（公证必失败）" >&2
        exit 1
      fi
    fi
  fi
fi

echo
echo "[build] 完成。"
if [[ "${NOTARIZE}" == "1" && "${GOOS_TARGET}" == "darwin" ]]; then
  echo "[build] 已公证 + staple：他人下载后可正常双击打开（Gatekeeper 放行）。"
  echo "[build]   若仍被 XProtect 以『包含恶意软件』拦截，属特征库误杀，公证不必然可解。"
elif [[ -n "${SIGN_ID}" ]]; then
  echo "[build] 已用 ${SIGN_ID} 签名（hardened runtime + entitlements + 内嵌二进制纳签），但【未公证】。"
  echo "[build]   可用于本机验证签名链路与启动行为；分发给他人仍需 NOTARIZE=1（未公证包仍会被拦）。"
elif [[ "${GOOS_TARGET}" == "darwin" ]]; then
  echo "[build] 提示：macOS 未公证包首次启动被 Gatekeeper 拦截（文案含『无法验证是否含恶意软件』，非真判毒）。"
  echo "[build]   打开方式：右键(Control+点击) ${ARTIFACT} → 『打开』即可；不要先 xattr -dr 删隔离标记。"
  echo "[build]   要分发他人：NOTARIZE=1 + DEV_ID_APP + 公证凭证 重跑本脚本。"
else
  echo "[build]   Windows 未签名包：首次从『Windows 安全中心 → 更多 → 仍要运行』放行。"
fi
