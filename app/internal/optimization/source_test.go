package optimization

import (
	"context"
	"errors"
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

// --- ImportedFileSource（1-2-4 D12）---

func writePortfolio(t *testing.T, body string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "portfolio.json")
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatalf("写持仓文件失败：%v", err)
	}
	return p
}

// 持仓文件与种子优化方案对照：种子有 宁德时代(SZ300750,from=28) / 隆基绿能(SH601012,from=8)
// / 招商银行(SH600036,from=0 新增)；文件含 宁德时代(25) / 隆基绿能(8) / 茅台(20)。
const samplePortfolioJSON = `{"as_of":"2026-10-16T15:30:00+08:00","cash":120000,"total_assets":680000,"holdings":[
{"code":"SZ300750","name":"宁德时代","weight":25,"cost":250.10,"price":268.40,"pnl_pct":7.32},
{"code":"SH601012","name":"隆基绿能","weight":8,"cost":22.40,"price":21.10,"pnl_pct":-5.80},
{"code":"SH600519","name":"贵州茅台","weight":20,"cost":1540.00,"price":1520.00,"pnl_pct":-1.30}]}`

func TestImportedFileSourceUnconfigured(t *testing.T) {
	_, err := NewImportedFileSource("").Fetch(context.Background())
	if !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("空路径应返回 ErrUnconfigured，得到 %v", err)
	}
}

func TestImportedFileSourceOverridesRealWeights(t *testing.T) {
	p := writePortfolio(t, samplePortfolioJSON)
	plan, err := NewImportedFileSource(p).Fetch(context.Background())
	if err != nil {
		t.Fatalf("导入失败：%v", err)
	}
	if plan.Source != "imported-portfolio" {
		t.Fatalf("Source 应为 imported-portfolio，得到 %q", plan.Source)
	}
	byCode := map[string]Target{}
	for _, t2 := range plan.Targets {
		byCode[t2.Code] = t2
	}
	// 宁德时代：种子 from=28 → 真实 25（覆盖 + 标记）
	catl := byCode["SZ300750"]
	if catl.FromWeight != 25 {
		t.Fatalf("宁德时代 from_weight 应被真实持仓覆盖为 25，得到 %v", catl.FromWeight)
	}
	if !strings.Contains(catl.Reason, "基于真实持仓") {
		t.Fatalf("命中真实持仓应带标记，得到 %q", catl.Reason)
	}
	// 隆基绿能：种子 from=8 → 真实 8（覆盖，值恰巧相同但仍应标记）
	longi := byCode["SH601012"]
	if longi.FromWeight != 8 {
		t.Fatalf("隆基 from_weight 应为 8，得到 %v", longi.FromWeight)
	}
	if !strings.Contains(longi.Reason, "基于真实持仓") {
		t.Fatalf("隆基应带真实持仓标记，得到 %q", longi.Reason)
	}
	// 招商银行：种子 from=0 且无对应持仓 → 保持原样，不伪造
	cmb := byCode["SH600036"]
	if cmb.FromWeight != 0 {
		t.Fatalf("招商银行(新增) from_weight 应保持 0，得到 %v", cmb.FromWeight)
	}
	if strings.Contains(cmb.Reason, "基于真实持仓") {
		t.Fatalf("未命中不应带真实持仓标记，得到 %q", cmb.Reason)
	}
	// 建议部分带非实时标记
	if !strings.Contains(plan.Conditions, "本地种子·非实时") {
		t.Fatalf("conditions 应含非实时标记，得到 %q", plan.Conditions)
	}
	// 评分仍为种子值（建议，非事实）
	if plan.OriginalScore != 65 || plan.OptimizedScore != 74 {
		t.Fatalf("评分应保留种子值，得到 %v/%v", plan.OriginalScore, plan.OptimizedScore)
	}
}

func TestImportedFileSourceFailureModes(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "nope.json")
	badJSON := writePortfolio(t, `{"holdings":[`)
	empty := writePortfolio(t, `{"total_assets":100,"cash":0,"holdings":[]}`)

	cases := []struct {
		name    string
		path    string
		wantMsg string
	}{
		{"文件不存在", missing, "unreadable"},
		{"JSON 损坏", badJSON, "parse failed"},
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
