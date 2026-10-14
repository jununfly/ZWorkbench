package review

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

// Source 是 C36 多源适配/回退的抽象：每个源都尝试给出一份复盘摘要。
type Source interface {
	Name() string
	Fetch(ctx context.Context) (*ReviewDigest, error)
}

// LocalSnapshotSource 永远可用：返回内嵌的种子快照（离线/断网可用）。
type LocalSnapshotSource struct{}

func (LocalSnapshotSource) Name() string { return "local-snapshot" }

func (LocalSnapshotSource) Fetch(_ context.Context) (*ReviewDigest, error) {
	var b ReviewDigest
	if err := json.Unmarshal(seedJSON, &b); err != nil {
		return nil, fmt.Errorf("parse seed snapshot: %w", err)
	}
	b.Source = "local-snapshot"
	return &b, nil
}

// RemoteStubSource 占位远程源：当前未接真实复盘 API，固定失败 → 触发回退（C36 演示）。
type RemoteStubSource struct{}

func (RemoteStubSource) Name() string { return "remote-review" }

func (RemoteStubSource) Fetch(_ context.Context) (*ReviewDigest, error) {
	return nil, errors.New("remote source not wired yet (stub)")
}

// FallbackChain 按序尝试源，返回首个成功；非首选源命中即标记 fallback（C36 回退语义）。
type FallbackChain struct{ sources []Source }

func NewFallbackChain(sources ...Source) *FallbackChain {
	return &FallbackChain{sources: sources}
}

func (c *FallbackChain) Fetch(ctx context.Context) (*ReviewDigest, error) {
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
	return nil, fmt.Errorf("all review sources failed: %v", lastErr)
}

// NewDefaultChain 默认「远程优先、本地回退」（C36）。
func NewDefaultChain() *FallbackChain {
	return NewFallbackChain(RemoteStubSource{}, LocalSnapshotSource{})
}
