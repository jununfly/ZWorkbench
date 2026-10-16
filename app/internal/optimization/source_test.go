package optimization

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

func TestLocalSnapshotSourceFetch(t *testing.T) {
	b, err := LocalSnapshotSource{}.Fetch(context.Background())
	if err != nil {
		t.Fatalf("Fetch 失败：%v", err)
	}
	if b == nil || b.Source != "local-snapshot" {
		t.Fatalf("Source 期望 local-snapshot，得到 %v", b)
	}
	if b.OriginalScore != 65 {
		t.Fatalf("OriginalScore 期望 65，得到 %v", b.OriginalScore)
	}
	if b.OptimizedScore != 74 {
		t.Fatalf("OptimizedScore 期望 74，得到 %v", b.OptimizedScore)
	}
	if b.Improvement != 10 {
		t.Fatalf("Improvement 期望 10，得到 %v", b.Improvement)
	}
	if len(b.Targets) != 3 {
		t.Fatalf("Targets 期望 3，得到 %d", len(b.Targets))
	}
}

// TestRemoteSourceDisabledIsUnconfigured 验证默认（未启用）配置下，远程源返回
// ErrUnconfigured 而非「配了但坏了」：与 1-2-5「未配置/源失败」语义收敛对齐。
func TestRemoteSourceDisabledIsUnconfigured(t *testing.T) {
	b, err := NewRemoteSource(datasource.DefaultConfig()).Fetch(context.Background())
	if err == nil || b != nil {
		t.Fatalf("未配置远程源应失败且返回 nil，得到 err=%v b=%v", err, b)
	}
	if !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("未配置时应返回 ErrUnconfigured，得到 %v", err)
	}
}

func TestNewDefaultChainFallback(t *testing.T) {
	b, err := NewDefaultChain(datasource.DefaultConfig()).Fetch(context.Background())
	if err != nil {
		t.Fatalf("Fetch 失败：%v", err)
	}
	if !b.Fallback {
		t.Fatalf("远程未配置后落到本地快照，Fallback 应为 true")
	}
	if b.Source != "local-snapshot" {
		t.Fatalf("Fallback 源应为 local-snapshot，得到 %q", b.Source)
	}
}

func TestFallbackChainAllFail(t *testing.T) {
	_, err := NewFallbackChain(
		NewRemoteSource(datasource.DefaultConfig()),
		NewRemoteSource(datasource.DefaultConfig()),
	).Fetch(context.Background())
	if err == nil {
		t.Fatalf("全失败链应返回错误")
	}
	if !strings.Contains(err.Error(), "sources failed") {
		t.Fatalf("错误应含 sources failed，得到 %q", err.Error())
	}
}
