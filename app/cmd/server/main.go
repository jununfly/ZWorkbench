package main

import (
	"context"
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
)

func main() {
	cfg := config.Load()

	// 1-5-5：ZW_DB="mem"（默认）走内存；否则走 SQLite 文件（modernc，无 cgo）。
	var store data.Store
	var sqliteStore *data.SqliteStore
	if cfg.DB == "" || cfg.DB == "mem" {
		store = data.NewMemStore()
	} else {
		ss, err := data.NewSqliteStore(cfg.DB)
		if err != nil {
			log.Fatalf("[zw] 初始化 SQLite 失败：%v", err)
		}
		sqliteStore = ss
		store = ss
	}
	tabs := domain.DefaultTabs()

	handler := api.NewRouter(cfg, store, tabs)

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
	if sqliteStore != nil {
		_ = sqliteStore.Close()
	}
	log.Printf("[zw] shutdown")
}
