package mastery

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

func (LocalSnapshotSource) Fetch(_ context.Context) (*MasteryLibrary, error) {
	var b MasteryLibrary
	if err := json.Unmarshal(seedJSON, &b); err != nil {
		return nil, fmt.Errorf("parse seed snapshot: %w", err)
	}
	b.Source = "local-snapshot"
	return &b, nil
}

// RemoteSource 远程心法库源（C36 首选源）：走 datasource 统一契约（ADR 0017; formerly roadmap 1-2-1）。
// 未配置时 Fetch 返回 datasource.ErrUnconfigured（语义=未配置，不是故障），
// 回退链据此静默回退到本地快照，不报警。
type RemoteSource struct{ remote datasource.Remote }

// NewRemoteSource 用统一配置构造远程心法库源（路径即该领域的远程端点）。
func NewRemoteSource(cfg datasource.Config) RemoteSource {
	return RemoteSource{remote: datasource.Remote{
		Name: "remote-mastery",
		Path: "/mastery/library",
		Cfg:  cfg,
	}}
}

func (s RemoteSource) Name() string { return s.remote.Name }

func (s RemoteSource) Fetch(ctx context.Context) (*MasteryLibrary, error) {
	var b MasteryLibrary
	if err := s.remote.FetchJSON(ctx, &b); err != nil {
		return nil, err
	}
	b.Source = s.remote.Name
	return &b, nil
}

// FallbackChain 是「导入文件 → 远程 → 内嵌快照」的多源链（ADR 0017; formerly roadmap 1-2-5：语义收敛到 datasource 泛型实现）。
type FallbackChain = datasource.FallbackChain[*MasteryLibrary]

// NewFallbackChain 构造回退链（顺序即优先级）。
func NewFallbackChain(sources ...datasource.Source[*MasteryLibrary]) *FallbackChain {
	return datasource.NewFallbackChain(sources...)
}

// NewDefaultChain 默认「导入文件 → 远程 → 内嵌快照」（C36 + ADR 0017; formerly roadmap 1-2-3 D9）。
// cfg 与 importedPath 都由调用方显式注入（1-2-1 D3）：不在包内隐式读环境变量，
// 便于测试与 fail-closed。
//
// 导入文件排在最前：游资心法没有公开接口（见 import.go 说明），zj 自己的
// 导入数据集才是这个 tab 的可信来源；内嵌快照只做离线兜底。
func NewDefaultChain(cfg datasource.Config, importedPath string) *FallbackChain {
	return NewFallbackChain(NewImportedFileSource(importedPath), NewRemoteSource(cfg), LocalSnapshotSource{})
}
