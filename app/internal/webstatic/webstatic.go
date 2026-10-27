// Package webstatic 托管前端构建产物（app/web/dist）。
//
// 打包后的 Go 服务必须自己托管前端构建产物（app/web/dist），否则 Electron 窗口加载
// http://127.0.0.1:<port>/ 只会拿到 404（实测：打包前 GET / -> 404 page not found）。
// formerly roadmap 1-1-3（仅作溯源，非权威出处；执行协议见 AGENTS.md 第 2 节 Step 3）。
//
// 采用「磁盘托管 + 多候选路径」而非 go:embed，因为 app/web/dist 已 gitignore：
// embed 会让全新 clone 的 `go build` 直接失败。
//
// 失败语义遵循项目约定：依赖缺失时显式 503，绝不静默返回空页（空页会被误读成
// 「前端没数据」而不是「产物缺失」）。
package webstatic

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

const missingMsg = "ZW: 前端产物缺失。设置 ZW_WEB_DIR 指向 web/dist，" +
	"或在 app/web 下执行 `npm run build` 后再启动。"

// Dir 解析前端 dist 目录；全部候选都不存在时返回空串。
//
// 候选顺序：
//  1. 显式入参（来自 ZW_WEB_DIR，Electron 打包后传 resources 路径）
//  2. 可执行文件同级 web/dist
//  3. 可执行文件上一级 web/dist（打包布局：Resources/bin/<exe> → Resources/web）
//  4. 当前工作目录 web/dist（开发期 `go run ./cmd/server`）
func Dir(explicit string) string {
	if explicit != "" && isDist(explicit) {
		return explicit
	}
	var cands []string
	if exe, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exe)
		if resolved, err := filepath.EvalSymlinks(exe); err == nil {
			exeDir = filepath.Dir(resolved)
		}
		cands = append(cands,
			filepath.Join(exeDir, "web", "dist"),
			filepath.Join(exeDir, "..", "web", "dist"),
		)
	}
	cwd, err := os.Getwd()
	if err == nil {
		cands = append(cands, filepath.Join(cwd, "web", "dist"))
	}
	for _, c := range cands {
		if isDist(c) {
			return c
		}
	}
	return ""
}

func isDist(p string) bool {
	st, err := os.Stat(filepath.Join(p, "index.html"))
	return err == nil && !st.IsDir()
}

// NewHandler 返回 SPA 静态处理器。dir 为空时，非 /api/ 请求一律 503 + 明确文案。
//
// 静态资源统一回 Access-Control-Allow-Origin：*，因为 Vite 构建出的入口是
// <script type="module" crossorigin>，在 Electron/Chromium 的 CORS 语义下，缺少该头
// 可能被当作跨域请求拦掉（curl 看不出——它不执行 JS，只验证 HTTP 状态）。同源场景下
// 该头无害，却能消除「资源被 CORS 拦 → 整屏白」的歧义。
func NewHandler(dir string) http.Handler {
	if dir == "" {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if strings.HasPrefix(r.URL.Path, "/api/") {
				http.Error(w, "api route not found", http.StatusNotFound)
				return
			}
			w.Header().Set("Access-Control-Allow-Origin", "*")
			w.Header().Set("Content-Type", "text/plain; charset=utf-8")
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = fmt.Fprintln(w, missingMsg)
		})
	}

	fs := http.FileServer(http.Dir(dir))
	index := filepath.Join(dir, "index.html")

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		if strings.HasPrefix(r.URL.Path, "/api/") {
			http.Error(w, "api route not found", http.StatusNotFound)
			return
		}
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		rel := strings.TrimPrefix(filepath.Clean("/"+strings.TrimPrefix(r.URL.Path, "/")), "/")
		if rel != "" && rel != "." {
			if st, err := os.Stat(filepath.Join(dir, filepath.FromSlash(rel))); err == nil && !st.IsDir() {
				fs.ServeHTTP(w, r)
				return
			}
		}
		// SPA 兜底：未知路径回 index.html，交给前端路由。
		http.ServeFile(w, r, index)
	})
}
