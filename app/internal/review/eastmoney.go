package review

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

// 东方财富公开接口路径（roadmap 1-2-3 D8）。
// 与 C07/C08/C09 不同，复盘的真实源不是行情推送，而是研报列表：
//   - 研报列表在 reportapi 后端，push2 不服务该路径，故需独立 host；
//   - 盘面读数（指数 / 涨跌家数）仍在 push2，沿用 cfg.BaseURL。
const (
	emPathReport   = "/report/list"         // 机构研报列表（reportapi）
	emPathReviewUL = "/api/qt/ulist.np/get" // 指数与涨跌家数（push2）
	// emHostReport 是研报独立后端（roadmap 1-2-3 D8）。
	emHostReport = "https://reportapi.eastmoney.com"
)

// emReportBaseURL 是研报实际使用的 host，抽成变量以便测试替换为 httptest 地址，
// 保证测试 hermetic（默认即 emHostReport）。
var emReportBaseURL = emHostReport

// emIndexSecIDs 是盘面事实关注的 5 大指数（东方财富 secid 编码：1.=沪 0.=深）。
var emIndexSecIDs = []string{"1.000001", "0.399001", "0.399006", "1.000300", "1.000688"}

// emFactIndexCount 是盘面事实里展示的指数条数（5 条全列会让文案过长）。
const emFactIndexCount = 3

var (
	// emAuthorTopN 是作者观点展示条数（ZW_REVIEW_TOPN 覆盖）。
	emAuthorTopN = envInt("ZW_REVIEW_TOPN", 8)
	// emReportPageSize 是研报拉取篇数，同时是统计口径的样本量（ZW_REVIEW_PAGESIZE 覆盖）。
	emReportPageSize = envInt("ZW_REVIEW_PAGESIZE", 20)
	// emLookbackDays 是研报回看天数（ZW_REVIEW_LOOKBACK_DAYS 覆盖）。
	emLookbackDays = envInt("ZW_REVIEW_LOOKBACK_DAYS", 3)
)

// ratingOrder 是评级分布的固定展示顺序（不按计数排序，保证多次输出一致）。
var ratingOrder = []string{"买入", "增持", "中性", "减持", "卖出", "无评级"}

// emReportItem 是研报列表单条（reportapi /report/list）。
// 只取复盘用得到的字段；评级为空表示新股覆盖研究等无评级研报。
type emReportItem struct {
	Title        string `json:"title"`
	StockName    string `json:"stockName"`
	StockCode    string `json:"stockCode"`
	OrgSName     string `json:"orgSName"`
	PublishDate  string `json:"publishDate"`
	EmRatingName string `json:"emRatingName"`
	IndvInduName string `json:"indvInduName"`
	Researcher   string `json:"researcher"`
}

// emReportResponse 是研报列表外层。Hits 是区间内总篇数，Data 是本页条目。
type emReportResponse struct {
	Hits int            `json:"hits"`
	Data []emReportItem `json:"data"`
}

// emIndex 是指数列表条目（f2 最新价 / f3 涨跌幅 / f12 代码 / f14 名称）。
// 指数不存在停牌，故直接取 float64（缺失按 0 处理，不引入指针复杂度）。
type emIndex struct {
	F2  float64 `json:"f2"`
	F3  float64 `json:"f3"`
	F12 string  `json:"f12"`
	F14 string  `json:"f14"`
}

// emIndicesResponse 是指数列表外层。
type emIndicesResponse struct {
	RC   int `json:"rc"`
	Data struct {
		Diff []emIndex `json:"diff"`
	} `json:"data"`
}

// emBreadthResponse 涨跌家数（在上证 secid 上取 f104/f105/f106/f107）。
type emBreadthResponse struct {
	Data struct {
		Diff []struct {
			F104 int `json:"f104"` // 涨家数
			F105 int `json:"f105"` // 跌家数
			F106 int `json:"f106"` // 涨停
			F107 int `json:"f107"` // 跌停
		} `json:"diff"`
	} `json:"data"`
}

// breadth 是领域无关的盘面读数中间结构（buildFacts 的输入）。
type breadth struct {
	Up      int
	Down    int
	LimitUp int
	LimitDn int
}

// emGet 用统一 datasource 契约发一次 GET 并解码（超时 / 鉴权 / 失败分类全复用）。
// baseURL 为空时沿用 cfg.BaseURL；非空时覆盖（用于 reportapi 这种独立后端）。
func emGet(ctx context.Context, cfg datasource.Config, baseURL, path string, q url.Values, dst any) error {
	used := cfg
	if baseURL != "" {
		used.BaseURL = baseURL
	}
	r := datasource.Remote{Name: "remote-eastmoney", Path: path, Query: q, Cfg: used}
	return r.FetchJSON(ctx, dst)
}

// FetchEastmoney 用东方财富研报列表 + 盘面读数组装一份复盘摘要（C10，roadmap 1-2-3）。
//
// 字段边界（D8，诚实标注，不编造）：
//   - Authors：真实研报条目（机构 + 评级·个股·标题 + 发布日期）；
//   - Consensus / Divergence：可复核的统计口径（篇数 / 机构数 / 行业数 / 评级分布 / Top 行业）；
//   - Facts：真实盘面读数（指数涨跌、涨跌家数、涨跌停家数）；
//   - NextVerify：外部不提供主观判断，保留本地种子文本并显式标注「本地种子」。
//
// 未启用时返回 ErrUnconfigured（语义=未配置），回退链据此静默回退到本地快照。
func FetchEastmoney(ctx context.Context, cfg datasource.Config) (*ReviewDigest, error) {
	if !cfg.Usable() {
		return nil, datasource.ErrUnconfigured
	}
	var d ReviewDigest

	items, hits, err := emReports(ctx, cfg)
	if err != nil {
		return nil, err
	}
	d.Authors = mapAuthors(items, emAuthorTopN)
	d.Consensus = buildConsensus(items, hits, emLookbackDays)
	d.Divergence = buildDivergence(items)

	idx, err := emIndices(ctx, cfg)
	if err != nil {
		return nil, err
	}
	br, err := emBreadth(ctx, cfg)
	if err != nil {
		return nil, err
	}
	d.Facts = buildFacts(idx, br)
	d.NextVerify = seedNextVerify()

	d.Source = "remote-eastmoney"
	d.AsOf = time.Now().Format(time.RFC3339)
	return &d, nil
}

func emReports(ctx context.Context, cfg datasource.Config) ([]emReportItem, int, error) {
	var resp emReportResponse
	begin, end := reportRange(time.Now(), emLookbackDays)
	q := url.Values{}
	// beginTime/endTime 是必填参数（缺失时接口返回 400），用 UTC+8 日期计算。
	q.Set("beginTime", begin)
	q.Set("endTime", end)
	q.Set("pageNo", "1")
	q.Set("pageSize", strconv.Itoa(emReportPageSize))
	q.Set("qType", "0") // 全部研报（1=个股，2=策略…）
	q.Set("code", "*")
	q.Set("industryCode", "*")
	q.Set("rating", "*")
	q.Set("ratingChange", "*")
	if err := emGet(ctx, cfg, emReportBaseURL, emPathReport, q, &resp); err != nil {
		return nil, 0, err
	}
	return resp.Data, resp.Hits, nil
}

func emIndices(ctx context.Context, cfg datasource.Config) ([]emIndex, error) {
	var resp emIndicesResponse
	q := url.Values{}
	q.Set("fields", "f2,f3,f12,f14")
	q.Set("secids", strings.Join(emIndexSecIDs, ","))
	q.Set("fltt", "2")
	if err := emGet(ctx, cfg, "", emPathReviewUL, q, &resp); err != nil {
		return nil, err
	}
	return resp.Data.Diff, nil
}

func emBreadth(ctx context.Context, cfg datasource.Config) (breadth, error) {
	var resp emBreadthResponse
	q := url.Values{}
	q.Set("fields", "f104,f105,f106,f107")
	q.Set("secids", "1.000001") // 上证全市场涨跌家数
	q.Set("fltt", "2")
	if err := emGet(ctx, cfg, "", emPathReviewUL, q, &resp); err != nil {
		return breadth{}, err
	}
	if len(resp.Data.Diff) == 0 {
		return breadth{}, nil
	}
	d := resp.Data.Diff[0]
	return breadth{Up: d.F104, Down: d.F105, LimitUp: d.F106, LimitDn: d.F107}, nil
}

// reportRange 计算研报回看区间（UTC+8 日期，避免依赖系统 tzdata）。
// end=今天，begin=今天-(days-1)；days<=1 时 begin=end。
func reportRange(now time.Time, days int) (begin, end string) {
	loc := time.FixedZone("CST", 8*3600)
	t := now.In(loc)
	end = t.Format("20060102")
	if days <= 1 {
		return end, end
	}
	return t.AddDate(0, 0, -(days - 1)).Format("20060102"), end
}

// mapAuthors 把研报条目映射为作者观点：机构简称 + 「评级 · 个股：标题」+ 发布日期。
// 评级为空时显式标注「无评级」——留空会被读成“接口没返回”，两者语义不同。
func mapAuthors(items []emReportItem, topN int) []AuthorView {
	n := len(items)
	if topN > 0 && topN < n {
		n = topN
	}
	out := make([]AuthorView, 0, n)
	for _, it := range items[:n] {
		rating := strings.TrimSpace(it.EmRatingName)
		if rating == "" {
			rating = "无评级"
		}
		name := strings.TrimSpace(it.OrgSName)
		if name == "" {
			name = strings.TrimSpace(it.Researcher)
		}
		if name == "" {
			name = "未知机构"
		}
		view := rating + " · " + strings.TrimSpace(it.StockName) + "：" + strings.TrimSpace(it.Title)
		out = append(out, AuthorView{
			Name: name,
			View: view,
			Date: dateOnly(it.PublishDate),
		})
	}
	return out
}

// buildConsensus 用可复核的统计口径描述共识：篇数 / 机构数 / 行业数 / 评级分布 / Top 行业。
// hits 是区间内总篇数，len(items) 是本页样本量——两者不同时必须都写出来，
// 否则「统计了 20 篇」会被误读成「市场只有 20 篇研报」。
func buildConsensus(items []emReportItem, hits, days int) string {
	if len(items) == 0 {
		return fmt.Sprintf("近 %d 日无研报数据，无法给出机构共识。", days)
	}
	orgs := make(map[string]struct{}, len(items))
	indus := make(map[string]int, len(items))
	ratings := make(map[string]int, len(items))
	for _, it := range items {
		if o := strings.TrimSpace(it.OrgSName); o != "" {
			orgs[o] = struct{}{}
		}
		if ind := strings.TrimSpace(it.IndvInduName); ind != "" {
			indus[ind]++
		}
		r := strings.TrimSpace(it.EmRatingName)
		if r == "" {
			r = "无评级"
		}
		ratings[r]++
	}
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("机构观点：近 %d 日研报共 %d 篇（统计样本 %d 篇）", days, hits, len(items)))
	sb.WriteString(fmt.Sprintf("，覆盖 %d 家机构 / %d 个行业", len(orgs), len(indus)))
	sb.WriteString("；评级分布 " + joinCounts(ratings))
	top := topKeys(indus, 3)
	if len(top) > 0 {
		parts := make([]string, 0, len(top))
		for _, kv := range top {
			parts = append(parts, fmt.Sprintf("%s(%d)", kv.k, kv.v))
		}
		sb.WriteString("；聚焦行业 Top" + strconv.Itoa(len(parts)) + "：" + strings.Join(parts, " / "))
	}
	sb.WriteString("。")
	return sb.String()
}

// buildDivergence 用评级分布描述分歧：多类评级=分歧，单一评级=一致（不能把一致说成分歧）。
// 行业内部出现不同评级时单独列出——那才是真正「同一方向上的判断不一致」。
func buildDivergence(items []emReportItem) string {
	ratings := make(map[string]int, len(items))
	indRatings := make(map[string]map[string]struct{}, len(items))
	for _, it := range items {
		r := strings.TrimSpace(it.EmRatingName)
		if r == "" || r == "无评级" {
			continue // 无评级研报不参与分歧判定（新股覆盖研究等）
		}
		ratings[r]++
		if ind := strings.TrimSpace(it.IndvInduName); ind != "" {
			if indRatings[ind] == nil {
				indRatings[ind] = make(map[string]struct{})
			}
			indRatings[ind][r] = struct{}{}
		}
	}
	if len(ratings) == 0 {
		return "近段研报均无明确评级，无法判断分歧。"
	}
	var sb strings.Builder
	if len(ratings) == 1 {
		for k, v := range ratings {
			sb.WriteString(fmt.Sprintf("评级一致：%s %d 篇（唯一评级），暂无明显分歧。", k, v))
		}
		return sb.String()
	}
	sb.WriteString("评级分歧：" + joinCounts(ratings))
	sb.WriteString(fmt.Sprintf("（共 %d 类评级，无单一主导）", len(ratings)))
	split := make([]string, 0, 3)
	inds := make([]string, 0, len(indRatings))
	for ind := range indRatings {
		inds = append(inds, ind)
	}
	sort.Strings(inds)
	for _, ind := range inds {
		if len(indRatings[ind]) > 1 && len(split) < 3 {
			split = append(split, ind)
		}
	}
	if len(split) > 0 {
		sb.WriteString("；行业内部评级不一致：" + strings.Join(split, " / "))
	}
	sb.WriteString("。")
	return sb.String()
}

// buildFacts 用真实盘面读数组成盘面事实（指数涨跌 + 涨跌家数 + 涨跌停家数）。
func buildFacts(idx []emIndex, b breadth) string {
	var sb strings.Builder
	sb.WriteString("盘面事实：")
	if len(idx) == 0 {
		sb.WriteString("指数读数缺失；")
	} else {
		n := len(idx)
		if n > emFactIndexCount {
			n = emFactIndexCount
		}
		parts := make([]string, 0, n)
		for _, d := range idx[:n] {
			parts = append(parts, fmt.Sprintf("%s %.2f（%+.2f%%）", d.F14, d.F2, d.F3))
		}
		sb.WriteString(strings.Join(parts, "，") + "；")
	}
	sb.WriteString(fmt.Sprintf("涨 %d 家 / 跌 %d 家，涨停 %d 家 / 跌停 %d 家。",
		b.Up, b.Down, b.LimitUp, b.LimitDn))
	return sb.String()
}

// seedNextVerify 取本地种子的「次日验证条件」并显式标注来源。
// 这是全表唯一的主观字段：外部接口不提供，也不能用统计冒充判断。
func seedNextVerify() string {
	const prefix = "[本地种子·非实时] "
	var seed ReviewDigest
	if err := json.Unmarshal(seedJSON, &seed); err != nil || seed.NextVerify == "" {
		return prefix + "无次日验证条件（外部接口不提供主观判断，本地种子亦缺失）。"
	}
	return prefix + seed.NextVerify
}

// joinCounts 按固定评级顺序拼「买入 2 · 增持 1」；未预置的评级按名称排序追加，
// 保证输出确定性（不能直接遍历 map）。
func joinCounts(m map[string]int) string {
	parts := make([]string, 0, len(m))
	seen := make(map[string]struct{}, len(m))
	for _, k := range ratingOrder {
		if v, ok := m[k]; ok {
			parts = append(parts, fmt.Sprintf("%s %d", k, v))
			seen[k] = struct{}{}
		}
	}
	rest := make([]string, 0, len(m))
	for k := range m {
		if _, ok := seen[k]; !ok {
			rest = append(rest, k)
		}
	}
	sort.Strings(rest)
	for _, k := range rest {
		parts = append(parts, fmt.Sprintf("%s %d", k, m[k]))
	}
	return strings.Join(parts, " · ")
}

// kv 是排序用的计数条目。
type kv struct {
	k string
	v int
}

// topKeys 按计数降序取前 n 个 key（并列时按名称升序，保证确定性）。
func topKeys(m map[string]int, n int) []kv {
	out := make([]kv, 0, len(m))
	for k, v := range m {
		out = append(out, kv{k, v})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].v != out[j].v {
			return out[i].v > out[j].v
		}
		return out[i].k < out[j].k
	})
	if n > 0 && n < len(out) {
		out = out[:n]
	}
	return out
}

// dateOnly 把 "2026-10-16 00:00:00.000" 裁成 "2026-10-16"。
func dateOnly(s string) string {
	s = strings.TrimSpace(s)
	if len(s) >= 10 {
		return s[:10]
	}
	return s
}

// envInt 读环境变量整数，非法/空则回退默认值。
func envInt(key string, def int) int {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return def
}
