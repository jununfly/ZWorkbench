package review

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

// 研报列表样例（reportapi host）：评级齐全 / 无评级 / 不同行业混合。
const sampleReportJSON = `{"hits":5,"data":[
{"title":"2026年第三季度业绩预告点评：Q3业绩同比高增","stockName":"乐鑫科技","stockCode":"688018","orgSName":"东吴证券","publishDate":"2026-10-16 00:00:00.000","emRatingName":"买入","indvInduName":"半导体","researcher":"陈海进"},
{"title":"Q3业绩大幅预增，AI PCB高景气延续","stockName":"沪电股份","stockCode":"002463","orgSName":"华金证券","publishDate":"2026-10-16 00:00:00.000","emRatingName":"增持","indvInduName":"元件","researcher":"孙潇雅"},
{"title":"出货稳步提升，隔膜盈利环比持续走高","stockName":"恩捷股份","stockCode":"002812","orgSName":"国信证券","publishDate":"2026-10-15 00:00:00.000","emRatingName":"买入","indvInduName":"电池","researcher":"王蔚祺"},
{"title":"新股覆盖研究：南方乳业","stockName":"南方乳业","stockCode":"920196","orgSName":"华金证券","publishDate":"2026-10-15 00:00:00.000","emRatingName":"","indvInduName":"饮料乳品","researcher":"郑庆炜"},
{"title":"三季报业绩点评：毛利率持续提升","stockName":"宇通客车","stockCode":"600066","orgSName":"东吴证券","publishDate":"2026-10-14 00:00:00.000","emRatingName":"中性","indvInduName":"商用车","researcher":"黄细里"}]}`

// 盘面读数样例（push2 host）：指数在前，涨跌家数在后（两次 ulist 请求）。
const sampleIndicesJSON = `{"rc":0,"data":{"diff":[
{"f2":3210.11,"f3":0.31,"f12":"000001","f14":"上证指数"},
{"f2":10123.45,"f3":-0.12,"f12":"399001","f14":"深证成指"},
{"f2":2030.11,"f3":0.55,"f12":"399006","f14":"创业板指"}]}}`
const sampleBreadthJSON = `{"rc":0,"data":{"diff":[{"f104":1777,"f105":537,"f106":43,"f107":2}]}}`

// newMockEM 同时服务研报(reportapi)与盘面(push2)两个后端：
// 区别在 path（/report/list vs /api/qt/ulist.np/get），与真实 host 拆分一致。
func newMockEM(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		switch {
		case r.URL.Path == emPathReport:
			if q.Get("beginTime") == "" || q.Get("endTime") == "" {
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			_, _ = w.Write([]byte(sampleReportJSON))
		case r.URL.Path == emPathReviewUL && strings.Contains(q.Get("fields"), "f104"):
			_, _ = w.Write([]byte(sampleBreadthJSON))
		case r.URL.Path == emPathReviewUL:
			_, _ = w.Write([]byte(sampleIndicesJSON))
		default:
			t.Errorf("未预期的请求 path=%s query=%s", r.URL.Path, r.URL.RawQuery)
		}
	}))
	return srv
}

func TestFetchEastmoneyUnconfigured(t *testing.T) {
	_, err := FetchEastmoney(context.Background(), datasource.DefaultConfig())
	if !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("未配置应返回 ErrUnconfigured，得到 %v", err)
	}
}

// TestMapAuthors 映射与截断：评级空→“无评级”，日期裁到 YYYY-MM-DD，条数按 topN 截断。
func TestMapAuthors(t *testing.T) {
	var resp emReportResponse
	if err := json.Unmarshal([]byte(sampleReportJSON), &resp); err != nil {
		t.Fatalf("解析样例失败：%v", err)
	}
	got := mapAuthors(resp.Data, 3)
	if len(got) != 3 {
		t.Fatalf("topN=3 应截断到 3 条，得到 %d", len(got))
	}
	if got[0].Name != "东吴证券" {
		t.Fatalf("Authors[0].Name 应为 东吴证券，得到 %q", got[0].Name)
	}
	if !strings.Contains(got[0].View, "买入") || !strings.Contains(got[0].View, "乐鑫科技") {
		t.Fatalf("Authors[0].View 应含评级与个股，得到 %q", got[0].View)
	}
	if got[0].Date != "2026-10-16" {
		t.Fatalf("Authors[0].Date 应裁到日期，得到 %q", got[0].Date)
	}
	// 第 4 条样例评级为空 → 应显式标注“无评级”，而不是留空让人误读。
	if idx := 3; idx < len(got) && !strings.Contains(got[idx].View, "无评级") {
		t.Fatalf("空评级应标注为 无评级，得到 %q", got[idx].View)
	}
	all := mapAuthors(resp.Data, 10)
	if len(all) != 5 {
		t.Fatalf("topN 大于实际条数时应返回全部 5 条，得到 %d", len(all))
	}
	if strings.Contains(all[3].View, "无评级") != true {
		t.Fatalf("第 4 条应标注 无评级，得到 %q", all[3].View)
	}
}

// TestBuildConsensusDeterministic 统计口径必须可复核且多次输出一致（map 遍历需排序）。
func TestBuildConsensusDeterministic(t *testing.T) {
	var resp emReportResponse
	if err := json.Unmarshal([]byte(sampleReportJSON), &resp); err != nil {
		t.Fatalf("解析样例失败：%v", err)
	}
	first := buildConsensus(resp.Data, resp.Hits, 3)
	second := buildConsensus(resp.Data, resp.Hits, 3)
	if first != second {
		t.Fatalf("统计输出必须确定性：\n%q\n%q", first, second)
	}
	// 样例：5 篇 / 3 家机构 / 5 个行业 / 评级 买入2 增持1 中性1 无评级1。
	for _, want := range []string{"5 篇", "3 家机构", "5 个行业", "买入 2", "增持 1", "中性 1", "无评级 1"} {
		if !strings.Contains(first, want) {
			t.Fatalf("共识统计应含 %q，得到 %q", want, first)
		}
	}
	if empty := buildConsensus(nil, 0, 3); !strings.Contains(empty, "无研报") {
		t.Fatalf("空数据应给出明确的无数据表述，得到 %q", empty)
	}
}

// TestBuildDivergence 多评级=有分歧；单一评级=一致（不能把一致说成分歧）。
func TestBuildDivergence(t *testing.T) {
	var resp emReportResponse
	if err := json.Unmarshal([]byte(sampleReportJSON), &resp); err != nil {
		t.Fatalf("解析样例失败：%v", err)
	}
	multi := buildDivergence(resp.Data)
	if !strings.Contains(multi, "分歧") {
		t.Fatalf("多评级应判定为分歧，得到 %q", multi)
	}
	one := buildDivergence(resp.Data[:1]) // 仅 买入
	if !strings.Contains(one, "一致") || strings.Contains(one, "分歧：") {
		t.Fatalf("单一评级应判定为一致，得到 %q", one)
	}
}

func TestBuildFacts(t *testing.T) {
	facts := buildFacts(
		[]emIndex{{F2: 3210.11, F3: 0.31, F12: "000001", F14: "上证指数"}},
		breadth{Up: 1777, Down: 537, LimitUp: 43, LimitDn: 2},
	)
	for _, want := range []string{"上证指数", "3210.11", "+0.31%", "1777", "537", "43", "2"} {
		if !strings.Contains(facts, want) {
			t.Fatalf("盘面事实应含 %q，得到 %q", want, facts)
		}
	}
}

// TestFetchEastmoneyMapping 端到端映射（hermetic）：研报走 reportapi 独立 host 覆盖，
// 盘面走 cfg.BaseURL；两处都指向 mock，不打真实外网。
func TestFetchEastmoneyMapping(t *testing.T) {
	srv := newMockEM(t)
	defer srv.Close()
	origHost := emReportBaseURL
	emReportBaseURL = srv.URL
	defer func() { emReportBaseURL = origHost }()

	cfg := datasource.Config{Enabled: true, BaseURL: srv.URL}
	d, err := FetchEastmoney(context.Background(), cfg)
	if err != nil {
		t.Fatalf("FetchEastmoney 失败：%v", err)
	}
	if d.Source != "remote-eastmoney" {
		t.Fatalf("Source 应为 remote-eastmoney，得到 %q", d.Source)
	}
	if len(d.Authors) != 5 { // 样例 5 条 < topN(8) → 返回全部，不补空位
		t.Fatalf("作者观点条数应为 5（样例上限），得到 %d", len(d.Authors))
	}
	if d.Consensus == "" || d.Divergence == "" || d.Facts == "" || d.NextVerify == "" {
		t.Fatalf("四个区块都不应为空：%+v", d)
	}
	// NextVerify 是主观判断，外部不提供 → 必须显式标注来自本地种子。
	if !strings.Contains(d.NextVerify, "本地种子") {
		t.Fatalf("NextVerify 应标注来自本地种子，得到 %q", d.NextVerify)
	}
	if !strings.Contains(d.Facts, "涨停 43") || !strings.Contains(d.Facts, "跌停 2") {
		t.Fatalf("Facts 应为真实盘面读数，得到 %q", d.Facts)
	}
}

// TestReportRange 回看区间：end=今天(UTC+8)，begin=今天-(days-1)。
func TestReportRange(t *testing.T) {
	now := time.Date(2026, 10, 16, 2, 0, 0, 0, time.UTC) // UTC+8 → 2026-10-16 10:00
	begin, end := reportRange(now, 3)
	if end != "20261016" {
		t.Fatalf("end 应为 20261016，得到 %q", end)
	}
	if begin != "20261014" {
		t.Fatalf("begin 应为 20261014，得到 %q", begin)
	}
	same, _ := reportRange(now, 1)
	if same != "20261016" {
		t.Fatalf("days=1 时 begin 应等于今天，得到 %q", same)
	}
}

func TestFetchEastmoneyLive(t *testing.T) {
	if os.Getenv("ZW_LIVE_EM") != "1" {
		t.Skip("设 ZW_LIVE_EM=1 才对东方财富做真实调用")
	}
	cfg := datasource.Config{Enabled: true, BaseURL: "https://push2.eastmoney.com", TimeoutSec: 15}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	d, err := FetchEastmoney(ctx, cfg)
	if err != nil {
		t.Fatalf("FetchEastmoney 真实调用失败：%v", err)
	}
	if len(d.Authors) == 0 {
		t.Fatalf("真实研报条数不应为 0")
	}
	t.Logf("live review: authors=%d source=%s", len(d.Authors), d.Source)
	t.Logf("  consensus: %s", d.Consensus)
	t.Logf("  divergence: %s", d.Divergence)
	t.Logf("  facts: %s", d.Facts)
	t.Logf("  next_verify: %s", d.NextVerify)
	for i, a := range d.Authors {
		t.Logf("  author[%d] %s (%s): %s", i, a.Name, a.Date, a.View)
	}
}
