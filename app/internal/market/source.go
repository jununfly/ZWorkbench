package market

import (
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

//go:embed snapshot.json
var seedJSON []byte

// Source 是 C36 多源适配/回退的抽象：每个源都尝试给出一份行情总览。
type Source interface {
	Name() string
	Fetch(ctx context.Context) (*MarketOverview, error)
}

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

// RemoteStubSource 占位远程源：当前未接真实行情 API，固定失败 → 触发回退（C36 演示）。
// 后续切片把这里换成东方财富/开盘啦等真实适配，成功即不再回退。
type RemoteStubSource struct{}

func (RemoteStubSource) Name() string { return "remote-eastmoney" }

func (RemoteStubSource) Fetch(_ context.Context) (*MarketOverview, error) {
	return nil, errors.New("remote source not wired yet (stub)")
}

// FallbackChain 按序尝试源，返回首个成功；非首选源命中即标记 fallback（C36 回退语义）。
type FallbackChain struct{ sources []Source }

// NewFallbackChain 构造回退链（顺序即优先级）。
func NewFallbackChain(sources ...Source) *FallbackChain {
	return &FallbackChain{sources: sources}
}

// Fetch 尝试所有源，返回第一个成功结果；同时标注是否走了回退。
func (c *FallbackChain) Fetch(ctx context.Context) (*MarketOverview, error) {
	var lastErr error
	for i, s := range c.sources {
		ov, err := s.Fetch(ctx)
		if err == nil && ov != nil {
			ov.Fallback = i > 0
			if ov.AsOf == "" {
				ov.AsOf = time.Now().Format(time.RFC3339)
			}
			return ov, nil
		}
		lastErr = err
	}
	return nil, fmt.Errorf("all market sources failed: %v", lastErr)
}

// NewDefaultChain 默认「远程优先、本地回退」（C36）。
func NewDefaultChain() *FallbackChain {
	return NewFallbackChain(RemoteStubSource{}, LocalSnapshotSource{})
}
