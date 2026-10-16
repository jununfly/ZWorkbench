package research

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strings"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

// 东方财富公开接口路径（roadmap 1-2-2，zj 拍板：免费免 token 行情源）。
const (
	emPathResearchUL = "/api/qt/ulist.np/get" // 个股实时报价
)

// emQuote 是东方财富 ulist 的紧凑字段（f2 最新价 / f3 涨跌幅 / f12 代码 / f14 名称）。
// fltt=2 时 f2/f3 已是十进制；停牌等无值情况 f2/f3 为 null。
type emQuote struct {
	F2  *float64 `json:"f2"`
	F3  *float64 `json:"f3"`
	F12 string   `json:"f12"`
	F14 string   `json:"f14"`
}

// emQuoteResponse 是 ulist 的统一外层。
type emQuoteResponse struct {
	RC   int `json:"rc"`
	Data struct {
		Diff []emQuote `json:"diff"`
	} `json:"data"`
}

func derefF(p *float64) float64 {
	if p == nil {
		return 0
	}
	return *p
}

// stripPrefix 去掉 SZ/SH 前缀，拿到裸代码用于匹配东方财富返回。
func stripPrefix(code string) string {
	return strings.TrimPrefix(strings.TrimPrefix(code, "SZ"), "SH")
}

// toSecID 把研究快照里的代码转成东方财富 secid（1.=沪 0.=深）。
// 支持 "SZ300750"/"SH600519" 前缀写法，也兼容裸代码（6 开头→沪，其余→深）。
func toSecID(code string) string {
	num := stripPrefix(code)
	market := "1"
	switch {
	case strings.HasPrefix(code, "SZ"):
		market = "0"
	case strings.HasPrefix(code, "SH"):
		market = "1"
	case strings.HasPrefix(num, "6"):
		market = "1"
	default:
		market = "0"
	}
	return market + "." + num
}

// emGet 用统一 datasource 契约发一次 GET 并解码（超时 / 鉴权 / 失败分类 / 限流全复用）。
func emGet(ctx context.Context, cfg datasource.Config, path string, q url.Values, dst any) error {
	r := datasource.Remote{Name: "remote-eastmoney", Path: path, Query: q, Cfg: cfg}
	return r.FetchJSON(ctx, dst)
}

// FetchEastmoney 用东方财富实时报价「富化」本地研究清单（C08 最小切片，roadmap 1-2-2）：
// 价格/涨跌幅取实时，用途/周期/核心判断/支持/反对等文字注解仍来自本地种子
// （研究者的主观判断，外部接口不提供）。未启用时返回 ErrUnconfigured（语义=未配置），
// 回退链据此静默回退到纯本地快照，不报警。
func FetchEastmoney(ctx context.Context, cfg datasource.Config) (*StockResearch, error) {
	if !cfg.Usable() {
		return nil, datasource.ErrUnconfigured
	}
	// 基础：本地种子（含注解）。
	var base StockResearch
	if err := json.Unmarshal(seedJSON, &base); err != nil {
		return nil, fmt.Errorf("parse seed snapshot: %w", err)
	}
	if len(base.Stocks) == 0 {
		base.Source = "remote-eastmoney"
		base.AsOf = time.Now().Format(time.RFC3339)
		return &base, nil
	}
	// 取实时报价（按 secid 批量）。
	secids := make([]string, 0, len(base.Stocks))
	for _, s := range base.Stocks {
		secids = append(secids, toSecID(s.Code))
	}
	var resp emQuoteResponse
	q := url.Values{}
	q.Set("fields", "f2,f3,f12,f14")
	q.Set("secids", strings.Join(secids, ","))
	q.Set("fltt", "2")
	if err := emGet(ctx, cfg, emPathResearchUL, q, &resp); err != nil {
		return nil, err
	}
	// 按裸代码建索引，富化价格/涨跌幅；找不到的个股保留种子值（fail-soft）。
	byBare := make(map[string]emQuote, len(resp.Data.Diff))
	for _, d := range resp.Data.Diff {
		byBare[stripPrefix(d.F12)] = d
	}
	for i := range base.Stocks {
		q, ok := byBare[stripPrefix(base.Stocks[i].Code)]
		if !ok {
			continue
		}
		// 仅当实时字段非 nil 才覆盖；东方财富对停牌等返回 null 时保留种子值（fail-soft，不写 0）。
		if q.F2 != nil {
			base.Stocks[i].Price = derefF(q.F2)
		}
		if q.F3 != nil {
			base.Stocks[i].ChangePct = derefF(q.F3)
		}
	}
	base.Source = "remote-eastmoney"
	base.AsOf = time.Now().Format(time.RFC3339)
	return &base, nil
}
