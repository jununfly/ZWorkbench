package limitup

import (
	"context"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

// 东方财富公开接口路径（roadmap 1-2-2，zj 拍板：免费免 token 行情源）。
const (
	emPathLimitUL = "/api/qt/ulist.np/get" // 涨跌停家数
	emPathLimitCL = "/api/qt/clist/get"     // 涨停个股 / 概念板块 / 板块成分股
	emPathZTPool  = "/getTopicZTPool"       // 涨停股池（连板天数专用，仅在 push2ex 上可用）
	// emHostPool 是涨停股池独立后端：push2 主机不服务该路径，push2ex 也不服务
	// clist/ulist，故股池必须单独指定 host（roadmap 1-2-2-1 D7）。
	emHostPool = "https://push2ex.eastmoney.com"
	// emUT 是东方财富网页端公开 ut 参数（非私密凭证，前端硬编码常量）。
	emUT = "7eea3edcaed734bea9cbfc24409ed989"
)

// emPoolBaseURL 是股池实际使用的 host，抽成变量以便测试替换为 httptest 地址，
// 保证测试 hermetic（默认即 emHostPool）。
var emPoolBaseURL = emHostPool

// emQuote 是东方财富 clist/ulist 的紧凑字段（f2 最新价 / f3 涨跌幅 / f12 代码 / f14 名称 / f104 领涨股数）。
type emQuote struct {
	F2  *float64 `json:"f2"`
	F3  *float64 `json:"f3"`
	F12 string   `json:"f12"`
	F14 string   `json:"f14"`
	F104 int     `json:"f104"`
}

// emListResponse 是 clist/ulist 的统一外层。
type emListResponse struct {
	RC   int `json:"rc"`
	Data struct {
		Diff []emQuote `json:"diff"`
	} `json:"data"`
}

// emLimitResponse 涨跌停家数（在 上证 secid 上取 f104/f105/f106/f107）。
type emLimitResponse struct {
	Data struct {
		Diff []struct {
			F104 int `json:"f104"` // 涨家数
			F105 int `json:"f105"` // 跌家数
			F106 int `json:"f106"` // 涨停
			F107 int `json:"f107"` // 跌停
		} `json:"diff"`
	} `json:"data"`
}

// emZTPoolItem 是涨停股池单条（getTopicZTPool）。
// p 为价格×1000（分*10），需 /1000；zdp 已是涨跌幅%；zttj.days 是连板天数（权威）。
type emZTPoolItem struct {
	C    string  `json:"c"`    // 代码
	N    string  `json:"n"`    // 名称
	P    float64 `json:"p"`    // 价格×1000
	Zdp  float64 `json:"zdp"`  // 涨跌幅%
	Lbc  int     `json:"lbc"`  // 连板次数（备用）
	Hybk string  `json:"hybk"` // 行业板块
	Zttj struct {
		Days int `json:"days"` // 连板天数（权威）
	} `json:"zttj"`
}

// emZTPoolResponse 涨停股池外层。
type emZTPoolResponse struct {
	Data struct {
		TC    int            `json:"tc"` // 涨停总数
		Qdate int            `json:"qdate"`
		Pool  []emZTPoolItem `json:"pool"`
	} `json:"data"`
}

func derefF(p *float64) float64 {
	if p == nil {
		return 0
	}
	return *p
}

// emGet 用统一 datasource 契约发一次 GET 并解码（超时 / 鉴权 / 失败分类 / 限流全复用）。
// baseURL 为空时沿用 cfg.BaseURL；非空时覆盖（用于 push2ex 股池这种独立后端）。
func emGet(ctx context.Context, cfg datasource.Config, baseURL, path string, q url.Values, dst any) error {
	used := cfg
	if baseURL != "" {
		used.BaseURL = baseURL
	}
	r := datasource.Remote{Name: "remote-eastmoney", Path: path, Query: q, Cfg: used}
	return r.FetchJSON(ctx, dst)
}

// isLimitUp 按市场分板的涨停判定：主板 10%，创业板(30)/科创板(688/689) 20%。
// 北交所(8/4, 30% 限制) 罕见出现在主涨停板列表，这里按 10% 近似（follow-up 可精化）。
func isLimitUp(code string, chg float64) bool {
	if chg <= 0 {
		return false
	}
	switch {
	case strings.HasPrefix(code, "30"), strings.HasPrefix(code, "688"), strings.HasPrefix(code, "689"):
		return chg >= 19.8
	default:
		return chg >= 9.8
	}
}

// clampStrength 把板块涨跌幅映射成 0~100 的强度（负涨跌幅→0）。
func clampStrength(chg float64) float64 {
	if chg <= 0 {
		return 0
	}
	s := chg * 10 // +10% → 100
	if s > 100 {
		s = 100
	}
	return s
}

// classifyStage 基于真实读数的精确情绪阶段（roadmap 1-2-2-1 D7，取代纯涨停数启发式）。
// 冰点(<20涨停) / 退潮(跌停>涨停) / 高潮(>=80或最高板>=5) / 发酵(40-80) / 回暖(20-40且最高板>=2) / 启动(其余)。
func classifyStage(limitUp, limitDn, maxBoard int) string {
	switch {
	case limitUp < 20:
		return "冰点"
	case limitDn > limitUp:
		return "退潮"
	case limitUp >= 80 || maxBoard >= 5:
		return "高潮"
	case limitUp >= 40:
		return "发酵"
	case maxBoard >= 2:
		return "回暖"
	default:
		return "启动"
	}
}

// shanghaiDate 用 UTC+8 推算交易日（上海无夏令时，避免依赖系统 tzdata）。
func shanghaiDate(now time.Time) string {
	t := now.UTC().Add(8 * time.Hour)
	return t.Format("20060102")
}

// FetchEastmoney 组装真实连板/题材/情绪看板（C09 深化，roadmap 1-2-2-1）。
// 真实可得：全市场涨停/跌停家数(breadth)、连板梯队(含连板天数, 来自涨停股池)、
// 概念板块强度 + 龙头股(题材雷达)、精确情绪阶段。
// 未启用时返回 ErrUnconfigured（语义=未配置），回退链静默回退到本地种子快照。
func FetchEastmoney(ctx context.Context, cfg datasource.Config) (*LimitUpBoard, error) {
	if !cfg.Usable() {
		return nil, datasource.ErrUnconfigured
	}
	var b LimitUpBoard

	up, dn, err := emLimitCounts(ctx, cfg)
	if err != nil {
		return nil, err
	}
	b.Sentiment.LimitUp, b.Sentiment.LimitDn = up, dn

	codeToDays, tiers, maxBoard, err := emLimitUpPool(ctx, cfg)
	if err != nil {
		return nil, err
	}
	b.Tiers = tiers

	themes, err := emThemes(ctx, cfg)
	if err != nil {
		return nil, err
	}
	// 题材领涨股：仅给 Top N 概念板块补 Leading（控制请求数，roadmap 1-2-2-1 D7）。
	// Leading 改用「连板天数最高优先」选龙头（1-2-2-1-1 选项 A），codeToDays 来自股池映射。
	for i := 0; i < len(themes) && i < emLeadingTopN; i++ {
		lead, lerr := emThemeLeading(ctx, cfg, themes[i].Code, codeToDays)
		if lerr != nil {
			// 单题材龙头查询失败不致命：留空，不阻断整板。
			continue
		}
		themes[i].Leading = lead
	}
	b.Themes = themes

	b.Sentiment.MaxBoard = maxBoard
	b.Sentiment.Stage = classifyStage(up, dn, maxBoard)

	b.Source = "remote-eastmoney"
	b.AsOf = time.Now().Format(time.RFC3339)
	return &b, nil
}

func emLimitCounts(ctx context.Context, cfg datasource.Config) (int, int, error) {
	var resp emLimitResponse
	q := url.Values{}
	q.Set("fields", "f104,f105,f106,f107")
	q.Set("secids", "1.000001") // 上证全市场涨跌停家数
	q.Set("fltt", "2")
	if err := emGet(ctx, cfg, "", emPathLimitUL, q, &resp); err != nil {
		return 0, 0, err
	}
	if len(resp.Data.Diff) == 0 {
		return 0, 0, nil
	}
	d := resp.Data.Diff[0]
	return d.F106, d.F107, nil
}

// emLimitUpPool 用涨停股池专用接口取当日全部涨停个股及其连板天数，
// 返回 (按 days 降序分组的梯队, 最高板高度, error)。这是 ①连板天数 的权威数据源，
// 彻底替代原 clist 涨幅榜过滤首板法（roadmap 1-2-2-1 D7）。
func emLimitUpPool(ctx context.Context, cfg datasource.Config) (map[string]int, []Tier, int, error) {
	var resp emZTPoolResponse
	q := url.Values{}
	q.Set("ut", emUT)
	q.Set("dpt", "wz.ztzt")
	q.Set("Pageindex", "0")
	q.Set("pagesize", "300")
	q.Set("sort", "fbt:asc")
	q.Set("date", shanghaiDate(time.Now()))
	if err := emGet(ctx, cfg, emPoolBaseURL, emPathZTPool, q, &resp); err != nil {
		return nil, nil, 0, err
	}

	byDays := make(map[int][]LimitUpStock)
	// codeToDays 是股池 6 位代码→连板天数 的权威映射，供题材龙头按连板高度选股（1-2-2-1-1 选项 A）。
	codeToDays := make(map[string]int, len(resp.Data.Pool))
	maxBoard := 0
	for _, it := range resp.Data.Pool {
		days := it.Zttj.Days
		if days < 1 {
			days = 1 // 兜底：股池偶发 days=0 时按首板计
		}
		s := LimitUpStock{
			Code:      it.C,
			Name:      it.N,
			Price:     it.P / 1000,
			ChangePct: it.Zdp,
			Reason:    it.Hybk, // 行业板块作为涨停原因/题材标签填充
		}
		byDays[days] = append(byDays[days], s)
		codeToDays[it.C] = days
		if days > maxBoard {
			maxBoard = days
		}
	}

	daysList := make([]int, 0, len(byDays))
	for d := range byDays {
		daysList = append(daysList, d)
	}
	sort.Sort(sort.Reverse(sort.IntSlice(daysList)))

	tiers := make([]Tier, 0, len(daysList))
	for _, d := range daysList {
		tiers = append(tiers, Tier{Days: d, Stocks: byDays[d]})
	}
	return codeToDays, tiers, maxBoard, nil
}

func emThemes(ctx context.Context, cfg datasource.Config) ([]Theme, error) {
	var resp emListResponse
	q := url.Values{}
	q.Set("pn", "1")
	q.Set("pz", strconv.Itoa(emThemeTopN)) // 题材广度可调（默认 10，ZW_LIMITUP_THEME_TOPN 覆盖）
	q.Set("po", "1")
	q.Set("np", "1")
	q.Set("fltt", "2")
	q.Set("invt", "2")
	q.Set("fid", "f3")
	q.Set("fs", "m:90+t:3") // 概念板块
	q.Set("fields", "f12,f14,f3,f104")
	if err := emGet(ctx, cfg, "", emPathLimitCL, q, &resp); err != nil {
		return nil, err
	}
	out := make([]Theme, 0, len(resp.Data.Diff))
	for _, d := range resp.Data.Diff {
		out = append(out, Theme{
			Name:         d.F14,
			Code:         d.F12,
			LimitUpCount: d.F104, // f104=领涨股数（题材涨停数的近似代理）
			Strength:     clampStrength(derefF(d.F3)),
			Leading:      "", // 题材领涨股：下方按板块成分股补
		})
	}
	return out, nil
}

// emThemeTopN 取 TopN 概念板块（题材广度），默认 10，ZW_LIMITUP_THEME_TOPN 覆盖（1-2-2-1-1 ②）。
var emThemeTopN = envInt("ZW_LIMITUP_THEME_TOPN", 10)
// emLeadingTopN 只给热度最高的 N 个题材补连板/涨停龙头，默认 8，ZW_LIMITUP_LEADING_TOPN 覆盖（1-2-2-1-1 ②）。
var emLeadingTopN = envInt("ZW_LIMITUP_LEADING_TOPN", 8)
// emConstituentPz 取板块成分股的数量上限（供连板天数映射选龙头），内部实现细节（1-2-2-1-1 ①）。
const emConstituentPz = 20

// envInt 读环境变量整数，非法/空则回退默认值。
func envInt(key string, def int) int {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return def
}

// emThemeLeading 取某概念板块的「连板/涨停龙头」（1-2-2-1-1 选项 A）。
// 逻辑：取板块前 emConstituentPz 只成分股，按股池 codeToDays 映射的连板天数降序选最高者；
// 板块内若无连板/涨停股（poolDays 无命中）则回落涨幅 Top1（diff 已按 f3 降序）。
// fs=b:<板块代码> 在 push2 上可用（2026-10-16 实跑 b:BK0480 通过）。
func emThemeLeading(ctx context.Context, cfg datasource.Config, boardCode string, poolDays map[string]int) (string, error) {
	if !strings.HasPrefix(boardCode, "BK") {
		return "", nil // 非标准板块代码跳过，不当作错误
	}
	var resp emListResponse
	q := url.Values{}
	q.Set("pn", "1")
	q.Set("pz", strconv.Itoa(emConstituentPz)) // 取前 N 只成分股供连板天数映射
	q.Set("po", "1")
	q.Set("np", "1")
	q.Set("fltt", "2")
	q.Set("invt", "2")
	q.Set("fid", "f3")
	q.Set("fs", "b:"+boardCode)
	q.Set("fields", "f12,f14,f3")
	if err := emGet(ctx, cfg, "", emPathLimitCL, q, &resp); err != nil {
		return "", err
	}
	if len(resp.Data.Diff) == 0 {
		return "", nil
	}
	// 选龙头：连板天数最高优先；并列时涨停/涨幅高者在前（diff 已按 f3 降序，先出现者 chg 更高）；
	// 全程无 poolDays 命中则 best 保持 diff[0]（涨幅 Top1 回落）。
	best := resp.Data.Diff[0]
	bestDays := poolDays[best.F12]
	for _, d := range resp.Data.Diff[1:] {
		if poolDays[d.F12] > bestDays {
			best, bestDays = d, poolDays[d.F12]
		}
	}
	return best.F14, nil
}
