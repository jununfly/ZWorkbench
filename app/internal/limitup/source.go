package limitup

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

//go:embed snapshot.json
var seedJSON []byte

// Source 是 C36 多源适配/回退的抽象：每个源都尝试给出一份连板看板。
type Source interface {
	Name() string
	Fetch(ctx context.Context) (*LimitUpBoard, error)
}

// LocalSnapshotSource 永远可用：返回内嵌的种子快照（离线/断网可用，对应 ES「缓存」精神）。
type LocalSnapshotSource struct{}

func (LocalSnapshotSource) Name() string { return "local-snapshot" }

func (LocalSnapshotSource) Fetch(_ context.Context) (*LimitUpBoard, error) {
	var b LimitUpBoard
	if err := json.Unmarshal(seedJSON, &b); err != nil {
		return nil, fmt.Errorf("parse seed snapshot: %w", err)
	}
	b.Source = "local-snapshot"
	return &b, nil
}

// RemoteSource 远程连板/题材源（C36 首选源）：走 datasource 统一契约（roadmap 1-2-1）。
// 未配置时 Fetch 返回 datasource.ErrUnconfigured（语义=未配置，不是故障），
// 回退链据此静默回退到本地快照，不报警。
type RemoteSource struct{ remote datasource.Remote }

// NewRemoteSource 用统一配置构造远程连板/题材源（路径即该领域的远程端点）。
func NewRemoteSource(cfg datasource.Config) RemoteSource {
	return RemoteSource{remote: datasource.Remote{
		Name: "remote-kpl",
		Path: "/limitup/board",
		Cfg:  cfg,
	}}
}

func (s RemoteSource) Name() string { return s.remote.Name }

func (s RemoteSource) Fetch(ctx context.Context) (*LimitUpBoard, error) {
	// 1-2-2：东方财富真实连板/题材/情绪。未启用时 FetchEastmoney 内部返回
	// ErrUnconfigured（语义=未配置），回退链据此静默回退本地快照。
	return FetchEastmoney(ctx, s.remote.Cfg)
}

// FallbackChain 按序尝试源，返回首个成功；非首选源命中即标记 fallback（C36 回退语义）。
type FallbackChain struct{ sources []Source }

// NewFallbackChain 构造回退链（顺序即优先级）。
func NewFallbackChain(sources ...Source) *FallbackChain {
	return &FallbackChain{sources: sources}
}

// Fetch 尝试所有源，返回第一个成功结果；同时标注是否走了回退。
func (c *FallbackChain) Fetch(ctx context.Context) (*LimitUpBoard, error) {
	var lastErr error
	for i, s := range c.sources {
		b, err := s.Fetch(ctx)
		if err == nil && b != nil {
			b.Fallback = i > 0
			if b.AsOf == "" {
				b.AsOf = time.Now().Format(time.RFC3339)
			}
			return b, nil
		}
		lastErr = err
	}
	return nil, fmt.Errorf("all limitup sources failed: %v", lastErr)
}

// NewDefaultChain 默认「远程优先、本地回退」（C36）。
// cfg 由调用方显式注入（1-2-1 D3）：不在包内隐式读环境变量，便于测试与 fail-closed。
func NewDefaultChain(cfg datasource.Config) *FallbackChain {
	return NewFallbackChain(NewRemoteSource(cfg), LocalSnapshotSource{})
}
