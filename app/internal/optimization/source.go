package optimization

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

//go:embed snapshot.json
var seedJSON []byte

// LocalSnapshotSource 永远可用：返回内嵌的种子快照（离线/断网可用）。
type LocalSnapshotSource struct{}

func (LocalSnapshotSource) Name() string { return "local-snapshot" }

func (LocalSnapshotSource) Fetch(_ context.Context) (*OptimizationPlan, error) {
	b, err := parseSeedPlan()
	if err != nil {
		return nil, err
	}
	b.Source = "local-snapshot"
	return b, nil
}

// parseSeedPlan 解析内嵌种子快照（离线兜底 + 导入源取建议部分的基准）。
// 种子快照同时服务两处：①LocalSnapshotSource 整包兜底；②ImportedFileSource 取
// 优化建议（评分/改善/条件），并以真实持仓覆盖各 target 的当前仓位。
func parseSeedPlan() (*OptimizationPlan, error) {
	var b OptimizationPlan
	if err := json.Unmarshal(seedJSON, &b); err != nil {
		return nil, fmt.Errorf("parse seed snapshot: %w", err)
	}
	return &b, nil
}

// RemoteSource 远程持仓优化源（C36 首选源）：走 datasource 统一契约（roadmap 1-2-1）。
// 未配置时 Fetch 返回 datasource.ErrUnconfigured（语义=未配置，不是故障），
// 回退链据此静默回退到本地快照，不报警。
type RemoteSource struct{ remote datasource.Remote }

// NewRemoteSource 用统一配置构造远程持仓优化源（路径即该领域的远程端点）。
func NewRemoteSource(cfg datasource.Config) RemoteSource {
	return RemoteSource{remote: datasource.Remote{
		Name: "remote-optimization",
		Path: "/portfolio/optimization",
		Cfg:  cfg,
	}}
}

func (s RemoteSource) Name() string { return s.remote.Name }

func (s RemoteSource) Fetch(ctx context.Context) (*OptimizationPlan, error) {
	var b OptimizationPlan
	if err := s.remote.FetchJSON(ctx, &b); err != nil {
		return nil, err
	}
	b.Source = s.remote.Name
	return &b, nil
}

// FallbackChain 是「导入文件优先、远程次之、本地回退」的多源链（roadmap 1-2-5：语义收敛到 datasource 泛型实现）。
type FallbackChain = datasource.FallbackChain[*OptimizationPlan]

// NewFallbackChain 构造回退链（顺序即优先级）。
func NewFallbackChain(sources ...datasource.Source[*OptimizationPlan]) *FallbackChain {
	return datasource.NewFallbackChain(sources...)
}

// NewDefaultChain 默认「导入文件优先、远程次之、本地回退」（C36 + 1-2-4 D12）。
// cfg 由调用方显式注入（1-2-1 D3）；importedPath 是真实持仓导入文件路径，
// 空串表示未导入（ImportedFileSource 返回 ErrUnconfigured，静默落到下一源）。
// 不在包内隐式读环境变量，便于测试与 fail-closed。
func NewDefaultChain(cfg datasource.Config, importedPath string) *FallbackChain {
	return NewFallbackChain(
		NewImportedFileSource(importedPath),
		NewRemoteSource(cfg),
		LocalSnapshotSource{},
	)
}
