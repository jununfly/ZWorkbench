package mastery

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
	if len(b.Figures) != 4 {
		t.Fatalf("Figures 期望 4，得到 %d", len(b.Figures))
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
	b, err := NewDefaultChain(datasource.DefaultConfig(), "").Fetch(context.Background())
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

// TestNewDefaultChainImportedWins 导入文件优先于内嵌快照，且不算回退（roadmap 1-2-3 D9 链序）。
func TestNewDefaultChainImportedWins(t *testing.T) {
	p := writeImport(t, sampleImportJSON)
	lib, err := NewDefaultChain(datasource.DefaultConfig(), p).Fetch(context.Background())
	if err != nil {
		t.Fatalf("Fetch 失败：%v", err)
	}
	if lib.Source != "imported-file" {
		t.Fatalf("有导入文件时应命中 imported-file，得到 %q", lib.Source)
	}
	if lib.Fallback {
		t.Fatalf("命中首选源时 Fallback 应为 false")
	}
	if len(lib.Figures) != 2 {
		t.Fatalf("应使用导入文件的 2 条，得到 %d", len(lib.Figures))
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
