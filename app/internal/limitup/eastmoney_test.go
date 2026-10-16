package limitup

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

func TestIsLimitUp(t *testing.T) {
	cases := []struct {
		code string
		chg  float64
		want bool
	}{
		{"600802", 10.06, true},  // 主板涨停
		{"600802", 9.50, false},  // 主板未达
		{"300045", 20.04, true},  // 创业板涨停(20%)
		{"300045", 15.00, false}, // 创业板未达
		{"688256", 20.00, true},  // 科创板涨停
		{"600802", -1.0, false},  // 下跌不算
	}
	for _, c := range cases {
		if got := isLimitUp(c.code, c.chg); got != c.want {
			t.Fatalf("isLimitUp(%q,%.2f)=%v, want %v", c.code, c.chg, got, c.want)
		}
	}
}

func TestClampStrength(t *testing.T) {
	if got := clampStrength(5.4); got != 54 {
		t.Fatalf("clampStrength(5.4)=%v, want 54", got)
	}
	if got := clampStrength(-2.0); got != 0 {
		t.Fatalf("clampStrength(-2.0)=%v, want 0", got)
	}
	if got := clampStrength(15.0); got != 100 {
		t.Fatalf("clampStrength(15.0)=%v, want 100(封顶)", got)
	}
}

func TestClassifyStage(t *testing.T) {
	cases := []struct {
		up, dn, maxBoard int
		want             string
	}{
		{5, 2, 1, "冰点"},     // <20 涨停
		{43, 50, 2, "退潮"},   // 跌停>涨停
		{43, 2, 11, "高潮"},   // 最高板>=5
		{95, 1, 3, "高潮"},    // 涨停>=80
		{60, 1, 3, "发酵"},    // 40-80
		{30, 1, 2, "回暖"},    // 20-40 且最高板>=2
		{30, 1, 1, "启动"},    // 20-40 但最高板<2
	}
	for _, c := range cases {
		if got := classifyStage(c.up, c.dn, c.maxBoard); got != c.want {
			t.Fatalf("classifyStage(%d,%d,%d)=%q, want %q", c.up, c.dn, c.maxBoard, got, c.want)
		}
	}
}

func TestFetchEastmoneyUnconfigured(t *testing.T) {
	_, err := FetchEastmoney(context.Background(), datasource.DefaultConfig())
	if !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("未配置应返回 ErrUnconfigured，得到 %v", err)
	}
}

// 三个端点的样例响应（股池在 push2ex，其余在 push2）。
const sampleBreadthJSON = `{"rc":0,"data":{"diff":[{"f104":1777,"f105":537,"f106":43,"f107":2}]}}`
const samplePoolJSON = `{"rc":0,"data":{"tc":3,"qdate":20261016,"pool":[
{"c":"600825","n":"新华传媒","p":15160,"zdp":10.01,"lbc":11,"hybk":"出版","zttj":{"days":11}},
{"c":"002889","n":"东方嘉盛","p":14310,"zdp":9.99,"lbc":2,"hybk":"物流","zttj":{"days":2}},
{"c":"600802","n":"福建水泥","p":6780,"zdp":10.06,"lbc":1,"hybk":"水泥","zttj":{"days":1}}]}}`
const sampleThemesJSON = `{"rc":0,"data":{"diff":[
{"f3":5.54,"f12":"BK0480","f14":"航天航空","f104":58},
{"f3":-1.20,"f12":"BK1157","f14":"飞行汽车","f104":0}]}}`
const sampleBoardJSON = `{"rc":0,"data":{"diff":[
{"f3":20.02,"f12":"300581","f14":"晨曦航空"},
{"f3":20.0,"f12":"301586","f14":"佳力奇"}]}}` // 取涨幅 Top1 作龙头

func TestFetchEastmoneyMapping(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		switch {
		case strings.Contains(r.URL.Path, "ulist"):
			_, _ = w.Write([]byte(sampleBreadthJSON))
		case r.URL.Path == emPathZTPool:
			_, _ = w.Write([]byte(samplePoolJSON))
		case strings.HasPrefix(q.Get("fs"), "b:"):
			_, _ = w.Write([]byte(sampleBoardJSON))
		case q.Get("fs") == "m:90+t:3":
			_, _ = w.Write([]byte(sampleThemesJSON))
		default:
			t.Errorf("未预期的请求 path=%s fs=%s", r.URL.Path, q.Get("fs"))
		}
	}))
	defer srv.Close()
	// 股池默认走真实 push2ex host；测试替换为 mock 地址，保证 hermetic。
	origPool := emPoolBaseURL
	emPoolBaseURL = srv.URL
	defer func() { emPoolBaseURL = origPool }()

	cfg := datasource.Config{Enabled: true, BaseURL: srv.URL}
	b, err := FetchEastmoney(context.Background(), cfg)
	if err != nil {
		t.Fatalf("FetchEastmoney 失败：%v", err)
	}
	if b.Source != "remote-eastmoney" {
		t.Fatalf("Source 应为 remote-eastmoney，得到 %q", b.Source)
	}
	// 情绪：涨停=43, 跌停=2, 最高板=11 → 高潮。
	if b.Sentiment.LimitUp != 43 || b.Sentiment.LimitDn != 2 {
		t.Fatalf("涨跌停家数映射错误：%+v", b.Sentiment)
	}
	if b.Sentiment.MaxBoard != 11 {
		t.Fatalf("MaxBoard 应为 11，得到 %d", b.Sentiment.MaxBoard)
	}
	if b.Sentiment.Stage != "高潮" {
		t.Fatalf("Stage 应为 高潮（最高板>=5），得到 %q", b.Sentiment.Stage)
	}
	// 连板梯队：按 days 降序 3 档，各 1 只；每只 Reason 填行业板块。
	if len(b.Tiers) != 3 {
		t.Fatalf("Tiers 数量异常：%+v", b.Tiers)
	}
	wantDays := []int{11, 2, 1}
	for i, tw := range wantDays {
		if b.Tiers[i].Days != tw {
			t.Fatalf("Tiers[%d].Days=%d, want %d", i, b.Tiers[i].Days, tw)
		}
		if len(b.Tiers[i].Stocks) != 1 {
			t.Fatalf("Tiers[%d] 应有 1 只，得到 %d", i, len(b.Tiers[i].Stocks))
		}
		if b.Tiers[i].Stocks[0].Reason == "" {
			t.Fatalf("Tiers[%d] 个股 Reason(行业) 不应为空", i)
		}
	}
	// 题材：2 个，强度按涨跌幅映射（航天航空 +5.54% → 55.4）；Top 题材补 Leading。
	if len(b.Themes) != 2 {
		t.Fatalf("题材数量异常：%d", len(b.Themes))
	}
	if b.Themes[0].Name != "航天航空" || b.Themes[0].Strength != 55.4 || b.Themes[0].LimitUpCount != 58 {
		t.Fatalf("题材映射错误：%+v", b.Themes[0])
	}
	if b.Themes[0].Leading != "晨曦航空" {
		t.Fatalf("题材 Leading 应为 晨曦航空，得到 %q", b.Themes[0].Leading)
	}
	// 负涨跌幅题材强度应为 0。
	if b.Themes[1].Strength != 0 {
		t.Fatalf("负涨跌幅题材强度应为 0，得到 %v", b.Themes[1].Strength)
	}
}

func TestFetchEastmoneyLive(t *testing.T) {
	if os.Getenv("ZW_LIVE_EM") != "1" {
		t.Skip("设 ZW_LIVE_EM=1 才对东方财富做真实调用")
	}
	cfg := datasource.Config{Enabled: true, BaseURL: "https://push2.eastmoney.com", TimeoutSec: 12}
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
	defer cancel()
	b, err := FetchEastmoney(ctx, cfg)
	if err != nil {
		t.Fatalf("FetchEastmoney 真实调用失败：%v", err)
	}
	if b.Sentiment.LimitUp == 0 && b.Sentiment.LimitDn == 0 {
		t.Fatalf("真实涨跌停家数异常：%+v", b.Sentiment)
	}
	_, _ = json.Marshal(b)
	boards := 0
	for _, t := range b.Tiers {
		boards += len(t.Stocks)
	}
	t.Logf("live limitup: limit_up=%d limit_dn=%d boards=%d themes=%d stage=%s max_board=%d",
		b.Sentiment.LimitUp, b.Sentiment.LimitDn, boards, len(b.Themes), b.Sentiment.Stage, b.Sentiment.MaxBoard)
	for i, th := range b.Themes {
		t.Logf("  theme[%d] %s strength=%.1f leading=%q", i, th.Name, th.Strength, th.Leading)
	}
}

// TestEmThemeLeadingByBoardDays 验证 1-2-2-1-1 选项 A：连板天数最高优先，胜过涨幅 Top1。
func TestEmThemeLeadingByBoardDays(t *testing.T) {
	// 股池 days 映射：300581 连板 5，301586 连板 2。
	poolDays := map[string]int{"300581": 5, "301586": 2}
	// 成分股按 f3 降序：301586(20.02) 是涨幅 Top1，但 300581(10.00 非涨幅第一) 连板更高 → 应选晨曦航空。
	const boardJSON = `{"rc":0,"data":{"diff":[
{"f3":20.02,"f12":"301586","f14":"佳力奇"},
{"f3":10.00,"f12":"300581","f14":"晨曦航空"}]}}`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		if strings.HasPrefix(q.Get("fs"), "b:") {
			_, _ = w.Write([]byte(boardJSON))
			return
		}
		t.Errorf("未预期的请求 path=%s fs=%s", r.URL.Path, q.Get("fs"))
	}))
	defer srv.Close()
	cfg := datasource.Config{Enabled: true, BaseURL: srv.URL}
	got, err := emThemeLeading(context.Background(), cfg, "BK0480", poolDays)
	if err != nil {
		t.Fatalf("emThemeLeading 失败：%v", err)
	}
	if got != "晨曦航空" {
		t.Fatalf("龙头应为连板最高的 晨曦航空(days=5)，得到 %q", got)
	}
}

// TestEmThemeLeadingFallbackTop1 验证回落：板块内无连板/涨停股时取涨幅 Top1。
func TestEmThemeLeadingFallbackTop1(t *testing.T) {
	poolDays := map[string]int{} // 板块内无任何股池成员
	const boardJSON = `{"rc":0,"data":{"diff":[
{"f3":9.50,"f12":"600111","f14":"北方稀土"},
{"f3":8.00,"f12":"600222","f14":"其他股"}]}}`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(boardJSON))
	}))
	defer srv.Close()
	cfg := datasource.Config{Enabled: true, BaseURL: srv.URL}
	got, err := emThemeLeading(context.Background(), cfg, "BK0480", poolDays)
	if err != nil {
		t.Fatalf("emThemeLeading 失败：%v", err)
	}
	if got != "北方稀土" {
		t.Fatalf("无连板股时应回落涨幅 Top1=北方稀土，得到 %q", got)
	}
}

// 防止 fmt 被误判未使用（测试辅助占位，保持与实现一致的错误包装风格）。
var _ = fmt.Sprintf
