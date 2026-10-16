package research

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

func TestToSecID(t *testing.T) {
	cases := map[string]string{
		"SZ300750": "0.300750",
		"SH600519": "1.600519",
		"SZ002594": "0.002594",
		"300750":   "0.300750", // 创业板裸代码 → 深
		"600519":   "1.600519", // 沪市裸代码 → 沪
	}
	for in, want := range cases {
		if got := toSecID(in); got != want {
			t.Fatalf("toSecID(%q)=%q, want %q", in, got, want)
		}
	}
}

func TestFetchEastmoneyUnconfigured(t *testing.T) {
	_, err := FetchEastmoney(context.Background(), datasource.DefaultConfig())
	if !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("未配置应返回 ErrUnconfigured，得到 %v", err)
	}
}

// sampleResearchQuoteJSON 返回研究清单三只票的实时报价（含 null 占位，验证 deref 容错）。
const sampleResearchQuoteJSON = `{"rc":0,"data":{"diff":[
{"f2":270.10,"f3":2.55,"f12":"300750","f14":"宁德时代"},
{"f2":null,"f3":null,"f12":"600519","f14":"贵州茅台"},
{"f2":315.20,"f3":4.10,"f12":"002594","f14":"比亚迪"}]}}`

func TestFetchEastmoneyMapping(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "ulist") {
			t.Errorf("research 仅应请求 ulist，得到 path=%s", r.URL.Path)
		}
		_, _ = w.Write([]byte(sampleResearchQuoteJSON))
	}))
	defer srv.Close()

	cfg := datasource.Config{Enabled: true, BaseURL: srv.URL}
	b, err := FetchEastmoney(context.Background(), cfg)
	if err != nil {
		t.Fatalf("FetchEastmoney 失败：%v", err)
	}
	if b.Source != "remote-eastmoney" {
		t.Fatalf("Source 应为 remote-eastmoney，得到 %q", b.Source)
	}
	if len(b.Stocks) != 3 {
		t.Fatalf("研究股数量异常：%d", len(b.Stocks))
	}
	byCode := map[string]ResearchStock{}
	for _, s := range b.Stocks {
		byCode[s.Code] = s
	}
	// 宁德时代：价格/涨跌幅被实时覆盖。
	nx := byCode["SZ300750"]
	if nx.Price != 270.10 || nx.ChangePct != 2.55 {
		t.Fatalf("宁德时代实时富化失败：%+v", nx)
	}
	// 贵州茅台：实时返回 null → 保留种子价格(1520)，不被误写成 0。
	mt := byCode["SH600519"]
	if mt.Price != 1520.00 || mt.ChangePct != -1.02 {
		t.Fatalf("茅台 null 容错失败：%+v", mt)
	}
	// 注解必须保留（用途/周期/核心判断等）。
	if mt.Purpose != "观察" || mt.Cycle != "中期" || mt.Core == "" {
		t.Fatalf("注解丢失：%+v", mt)
	}
}

func TestFetchEastmoneyLive(t *testing.T) {
	if os.Getenv("ZW_LIVE_EM") != "1" {
		t.Skip("设 ZW_LIVE_EM=1 才对东方财富做真实调用")
	}
	cfg := datasource.Config{Enabled: true, BaseURL: "https://push2.eastmoney.com", TimeoutSec: 10}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	b, err := FetchEastmoney(ctx, cfg)
	if err != nil {
		t.Fatalf("FetchEastmoney 真实调用失败：%v", err)
	}
	if len(b.Stocks) == 0 {
		t.Fatalf("真实研究股为空")
	}
	// 至少一只价格被实时覆盖（!= 种子值）。
	enriched := false
	for _, s := range b.Stocks {
		if s.Price != 0 {
			enriched = true
			break
		}
	}
	if !enriched {
		t.Fatalf("真实报价未富化任何个股：%+v", b.Stocks)
	}
	_, _ = json.Marshal(b)
	t.Logf("live research: stocks=%d source=%s", len(b.Stocks), b.Source)
}
