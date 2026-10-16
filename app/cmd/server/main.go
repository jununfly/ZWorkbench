package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/api"
	"github.com/jununfly/ZWorkbench/app/internal/config"
	"github.com/jununfly/ZWorkbench/app/internal/data"
	"github.com/jununfly/ZWorkbench/app/internal/domain"
	"github.com/jununfly/ZWorkbench/app/internal/evidence"
)

// buildHandler 装配完整请求处理链（config→store→tabs→evidence→router）。
// 抽出来便于测试（package main 白盒），main() 仅负责绑定端口与信号生命周期。
func buildHandler(cfg *config.Config) (http.Handler, *data.SqliteStore, *evidence.Owner, error) {
	var store data.Store
	var sqliteStore *data.SqliteStore
	if cfg.DB == "" || cfg.DB == "mem" {
		store = data.NewMemStore()
	} else {
		ss, err := data.NewSqliteStore(cfg.DB)
		if err != nil {
			return nil, nil, nil, fmt.Errorf("初始化 SQLite 失败：%w", err)
		}
		sqliteStore = ss
		store = ss
	}
	tabs := domain.DefaultTabs()

	// 1-5-6-3：未配置 ZW_EVIDENCE_DB → 内存库（重启即空，零副作用）；
	// 显式给路径才落 SQLite 文件。打开失败不静默降级为「无证据」，直接失败退出。
	evPath := cfg.EvidenceDB
	if evPath == "" {
		evPath = ":memory:"
	}
	ev, err := evidence.Open(evPath)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("初始化证据库失败：%w", err)
	}

	handler := api.NewRouter(cfg, store, tabs, ev)
	return handler, sqliteStore, ev, nil
}

// evidencePath 还原 buildHandler 内的证据库路径决定逻辑，仅供日志。
func evidencePath(cfg *config.Config) string {
	if cfg.EvidenceDB == "" {
		return ":memory:"
	}
	return cfg.EvidenceDB
}

func main() {
	cfg := config.Load()

	handler, sqliteStore, ev, err := buildHandler(cfg)
	if err != nil {
		log.Fatalf("[zw] 装配服务失败：%v", err)
	}
	defer ev.Close()
	if sqliteStore != nil {
		defer sqliteStore.Close()
	}
	log.Printf("[zw] evidence store: %s", evidencePath(cfg))

	srv := &http.Server{
		Addr:         cfg.Addr(),
		Handler:      handler,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}

	go func() {
		log.Printf("[zw] listening on %s  token=%s", cfg.Addr(), cfg.Token)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[zw] server error: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(ctx)
	log.Printf("[zw] shutdown")
}
