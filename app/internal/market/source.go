package market

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

//go:embed snapshot.json
var seedJSON []byte

// LocalSnapshotSource 永远可用：返回内嵌的种子快照（离线/断网可用，对应 ES「7 天缓存」精神）。
type LocalSnapshotSource struct{}

func (LocalSnapshotSource) Name() string { return "local-snapshot" }

func (LocalSnapshotSource) Fetch(_ context.Context) (*MarketOverview, error) {
	var ov MarketOverview
	if err := json.Unmarshal(seedJSON, &ov); err != nil {
		return nil, fmt.Errorf("parse seed snapshot: %w", err)
	}
	ov.Source = "local-snapshot"
	return &ov, nil
}

// RemoteSource 远程行情源（C36 首选源）：走 datasource 统一契约（roadmap 1-2-1）。
// 未配置时 Fetch 返回 datasource.ErrUnconfigured（语义=未配置，不是故障），
// 回退链据此静默回退到本地快照，不报警。
type RemoteSource struct{ remote datasource.Remote }

// NewRemoteSource 用统一配置构造远程行情源（路径即该领域的远程端点）。
func NewRemoteSource(cfg datasource.Config) RemoteSource {
	return RemoteSource{remote: datasource.Remote{
		Name: "remote-eastmoney",
		Path: "/market/overview",
		Cfg:  cfg,
	}}
}

func (s RemoteSource) Name() string { return s.remote.Name }

func (s RemoteSource) Fetch(ctx context.Context) (*MarketOverview, error) {
	// 1-2-2：统一契约 + 东方财富公开接口适配器。未启用时 FetchEastmoney 内部返回
	// ErrUnconfigured（语义=未配置），回退链据此静默回退本地快照。
	return FetchEastmoney(ctx, s.remote.Cfg)
}

// FallbackChain 是「远程优先、本地回退」的多源链（roadmap 1-2-5：语义收敛到 datasource 泛型实现）。
type FallbackChain = datasource.FallbackChain[*MarketOverview]

// NewFallbackChain 构造回退链（顺序即优先级）。
func NewFallbackChain(sources ...datasource.Source[*MarketOverview]) *FallbackChain {
	return datasource.NewFallbackChain(sources...)
}

// NewDefaultChain 默认「远程优先、本地回退」（C36）。
// cfg 由调用方显式注入（1-2-1 D3）：不在包内隐式读环境变量，便于测试与 fail-closed。
func NewDefaultChain(cfg datasource.Config) *FallbackChain {
	return NewFallbackChain(NewRemoteSource(cfg), LocalSnapshotSource{})
}
