package inspection

import (
	"context"
	"errors"
	"math"
	"os"
	"path/filepath"
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
	// 隐式校验内嵌 snapshot.json 能正确反序列化成巡检报告（schema 漂移会在此暴露）
	if b.TotalAssets != 500000 {
		t.Fatalf("TotalAssets 期望 500000，得到 %v", b.TotalAssets)
	}
	if b.RiskLevel != "中风险" {
		t.Fatalf("RiskLevel 期望 中风险，得到 %q", b.RiskLevel)
	}
	if len(b.Holdings) != 4 {
		t.Fatalf("Holdings 期望 4，得到 %d", len(b.Holdings))
	}
	if len(b.Dimensions) != 4 {
		t.Fatalf("Dimensions 期望 4，得到 %d", len(b.Dimensions))
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

// --- ImportedFileSource（1-2-4 D11）---

func writePortfolio(t *testing.T, body string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "portfolio.json")
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatalf("写持仓文件失败：%v", err)
	}
	return p
}

const samplePortfolioJSON = `{"as_of":"2026-10-16T15:30:00+08:00","cash":120000,"total_assets":680000,"holdings":[
{"code":"SZ300750","name":"宁德时代","weight":25,"cost":250.10,"price":268.40,"pnl_pct":7.32},
{"code":"SH600519","name":"贵州茅台","weight":20,"cost":1540.00,"price":1520.00,"pnl_pct":-1.30}]}`

func TestImportedFileSourceUnconfigured(t *testing.T) {
	_, err := NewImportedFileSource("").Fetch(context.Background())
	if !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("空路径应返回 ErrUnconfigured，得到 %v", err)
	}
	if _, err := NewImportedFileSource("   ").Fetch(context.Background()); !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("空白路径同样应视为未配置，得到 %v", err)
	}
}

func TestImportedFileSourceLoadsRealFacts(t *testing.T) {
	p := writePortfolio(t, samplePortfolioJSON)
	rep, err := NewImportedFileSource(p).Fetch(context.Background())
	if err != nil {
		t.Fatalf("导入失败：%v", err)
	}
	if rep.Source != "imported-portfolio" {
		t.Fatalf("Source 应为 imported-portfolio，得到 %q", rep.Source)
	}
	// 事实来自真实文件
	if rep.TotalAssets != 680000 {
		t.Fatalf("TotalAssets 应为文件真实值 680000，得到 %v", rep.TotalAssets)
	}
	if rep.Cash != 120000 {
		t.Fatalf("Cash 应为文件真实值 120000，得到 %v", rep.Cash)
	}
	if len(rep.Holdings) != 2 || rep.Holdings[0].Name != "宁德时代" {
		t.Fatalf("持仓应为文件真实值，得到 %+v", rep.Holdings)
	}
	// pnl = 25%*680000*7.32% + 20%*680000*(-1.30%) = 12444 + (-1768) = 10676
	wantPnl := (25.0/100)*680000*(7.32/100) + (20.0/100)*680000*(-1.30/100)
	if math.Abs(rep.Pnl-wantPnl) > 1e-6 {
		t.Fatalf("Pnl 应加权计算为 %v，得到 %v", wantPnl, rep.Pnl)
	}
	// 评估字段来自种子且带非实时标记
	if !strings.Contains(rep.Dimensions[0].Basis, "本地种子·非实时") {
		t.Fatalf("维度依据应含非实时标记，得到 %q", rep.Dimensions[0].Basis)
	}
	if rep.AsOf != "2026-10-16T15:30:00+08:00" {
		t.Fatalf("文件自带 AsOf 应被保留，得到 %q", rep.AsOf)
	}
}

func TestImportedFileSourceFillsAsOf(t *testing.T) {
	p := writePortfolio(t, `{"cash":0,"total_assets":100,"holdings":[{"code":"A","name":"a","weight":10,"cost":1,"price":1,"pnl_pct":0}]}`)
	rep, err := NewImportedFileSource(p).Fetch(context.Background())
	if err != nil {
		t.Fatalf("导入失败：%v", err)
	}
	if strings.TrimSpace(rep.AsOf) == "" {
		t.Fatalf("AsOf 缺失时应自动补当前时间")
	}
}

func TestImportedFileSourceFailureModes(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "nope.json")
	badJSON := writePortfolio(t, `{"holdings":[`)
	noTotal := writePortfolio(t, `{"cash":0,"holdings":[{"code":"A","name":"a","weight":10,"cost":1,"price":1,"pnl_pct":0}]}`)
	empty := writePortfolio(t, `{"total_assets":100,"cash":0,"holdings":[]}`)

	cases := []struct {
		name    string
		path    string
		wantMsg string
	}{
		{"文件不存在", missing, "unreadable"},
		{"JSON 损坏", badJSON, "parse failed"},
		{"缺 total_assets", noTotal, "missing total_assets"},
		{"无持仓", empty, "no holdings"},
	}
	for _, c := range cases {
		_, err := NewImportedFileSource(c.path).Fetch(context.Background())
		if err == nil {
			t.Fatalf("%s 应失败（fail-closed），却返回成功", c.name)
		}
		if !strings.Contains(err.Error(), c.wantMsg) {
			t.Fatalf("%s 错误信息应含 %q，得到 %q", c.name, c.wantMsg, err.Error())
		}
		if !strings.Contains(err.Error(), c.path) {
			t.Fatalf("%s 错误信息应带文件路径，得到 %q", c.name, err.Error())
		}
	}
}
