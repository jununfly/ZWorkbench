package market

import (
	"context"
	"net/url"
	"strconv"
	"strings"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

// 东方财富公开接口路径（roadmap 1-2-2，zj 拍板：免费免 token 行情源）。
// 非官方接口，自用可接受；若需合规化，后续只改本文件即可，业务包的 Source 契约不动。
const (
	emPathIndices = "/api/qt/ulist.np/get" // 指数 / 涨跌家数
	emPathClist   = "/api/qt/clist/get"    // 涨幅榜 / 跌幅榜 / 板块
)

// majorIndexSecIDs 是 C07 行情总览关注的 5 大指数（东方财富 secid 编码：1.=沪 0.=深）。
var majorIndexSecIDs = []string{"1.000001", "0.399001", "0.399006", "1.000300", "1.000688"}

// emQuote 是东方财富 clist/ulist 的紧凑字段（f2 最新价 / f3 涨跌幅 / f12 代码 / f14 名称）。
// fltt=2 时 f2/f3 已是十进制；停牌等无值情况 f2/f3 为 null。
type emQuote struct {
	F2  *float64 `json:"f2"`
	F3  *float64 `json:"f3"`
	F12 string   `json:"f12"`
	F14 string   `json:"f14"`
}

// emListResponse 是 clist/ulist 的统一外层。
type emListResponse struct {
	RC   int `json:"rc"`
	Data struct {
		Total int       `json:"total"`
		Diff  []emQuote `json:"diff"`
	} `json:"data"`
}

// emBreadthResponse 涨跌家数（在 上证 secid 上取 f104/f105/f106/f107）。
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

func deref(p *float64) float64 {
	if p == nil {
		return 0
	}
	return *p
}

// emGet 用统一 datasource 契约发一次 GET 并解码（超时 / 鉴权 / 失败分类 / 限流全复用）。
func emGet(ctx context.Context, cfg datasource.Config, path string, q url.Values, dst any) error {
	r := datasource.Remote{Name: "remote-eastmoney", Path: path, Query: q, Cfg: cfg}
	return r.FetchJSON(ctx, dst)
}

// FetchEastmoney 走东方财富公开接口组装一份完整行情总览（C07 最小切片）。
// cfg 未启用/未配地址时返回 datasource.ErrUnconfigured（语义=未配置），
// 回退链据此静默回退到本地种子快照，不报警。
func FetchEastmoney(ctx context.Context, cfg datasource.Config) (*MarketOverview, error) {
	if !cfg.Usable() {
		return nil, datasource.ErrUnconfigured
	}
	var ov MarketOverview

	idx, err := emIndices(ctx, cfg)
	if err != nil {
		return nil, err
	}
	ov.Indices = idx

	breadth, err := emBreadth(ctx, cfg)
	if err != nil {
		return nil, err
	}
	ov.Breadth = breadth

	gainers, losers, err := emTopMovers(ctx, cfg)
	if err != nil {
		return nil, err
	}
	ov.TopGainers, ov.TopLosers = gainers, losers

	sectors, err := emSectors(ctx, cfg)
	if err != nil {
		return nil, err
	}
	ov.Sectors = sectors

	ov.Source = "remote-eastmoney"
	return &ov, nil
}

func emIndices(ctx context.Context, cfg datasource.Config) ([]Index, error) {
	var resp emListResponse
	q := url.Values{}
	q.Set("fields", "f2,f3,f12,f14")
	q.Set("secids", strings.Join(majorIndexSecIDs, ","))
	q.Set("fltt", "2")
	if err := emGet(ctx, cfg, emPathIndices, q, &resp); err != nil {
		return nil, err
	}
	return mapIndices(resp), nil
}

func emBreadth(ctx context.Context, cfg datasource.Config) (Breadth, error) {
	var resp emBreadthResponse
	q := url.Values{}
	q.Set("fields", "f104,f105,f106,f107")
	q.Set("secids", "1.000001") // 上证全市场涨跌家数
	q.Set("fltt", "2")
	if err := emGet(ctx, cfg, emPathIndices, q, &resp); err != nil {
		return Breadth{}, err
	}
	return mapBreadth(resp), nil
}

func emTopMovers(ctx context.Context, cfg datasource.Config) ([]StockQuote, []StockQuote, error) {
	gainers, err := emClist(ctx, cfg, "1", 10) // po=1：按涨跌幅降序 → 涨幅榜
	if err != nil {
		return nil, nil, err
	}
	losers, err := emClist(ctx, cfg, "0", 10) // po=0：按涨跌幅升序 → 跌幅榜
	if err != nil {
		return nil, nil, err
	}
	return gainers, losers, nil
}

func emClist(ctx context.Context, cfg datasource.Config, po string, pz int) ([]StockQuote, error) {
	var resp emListResponse
	q := url.Values{}
	q.Set("pn", "1")
	q.Set("pz", strconv.Itoa(pz))
	q.Set("po", po)
	q.Set("np", "1")
	q.Set("fltt", "2")
	q.Set("invt", "2")
	q.Set("fid", "f3")
	q.Set("fs", "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23") // 沪深京全部 A 股
	q.Set("fields", "f12,f14,f2,f3")
	if err := emGet(ctx, cfg, emPathClist, q, &resp); err != nil {
		return nil, err
	}
	return mapStockQuotes(resp), nil
}

func emSectors(ctx context.Context, cfg datasource.Config) ([]Sector, error) {
	var resp emListResponse
	q := url.Values{}
	q.Set("pn", "1")
	q.Set("pz", "8")
	q.Set("po", "1")
	q.Set("np", "1")
	q.Set("fltt", "2")
	q.Set("invt", "2")
	q.Set("fid", "f3")
	q.Set("fs", "m:90+t:2") // 板块
	q.Set("fields", "f12,f14,f2,f3")
	if err := emGet(ctx, cfg, emPathClist, q, &resp); err != nil {
		return nil, err
	}
	return mapSectors(resp), nil
}

// mapIndices 把东方财富指数列表映射回领域结构。
func mapIndices(r emListResponse) []Index {
	out := make([]Index, 0, len(r.Data.Diff))
	for _, d := range r.Data.Diff {
		out = append(out, Index{
			Code:      d.F12,
			Name:      d.F14,
			Value:     deref(d.F2),
			ChangePct: deref(d.F3),
		})
	}
	return out
}

// mapBreadth 把涨跌家数响应映射回领域结构（Flat 东方财富未单列，留 0）。
func mapBreadth(r emBreadthResponse) Breadth {
	if len(r.Data.Diff) == 0 {
		return Breadth{}
	}
	d := r.Data.Diff[0]
	return Breadth{
		Up:       d.F104,
		Down:     d.F105,
		LimitUp:  d.F106,
		LimitDn:  d.F107,
	}
}

// mapStockQuotes 把 clist 个股列表映射回领域结构（涨幅榜 / 跌幅榜共用）。
func mapStockQuotes(r emListResponse) []StockQuote {
	out := make([]StockQuote, 0, len(r.Data.Diff))
	for _, d := range r.Data.Diff {
		out = append(out, StockQuote{
			Code:      d.F12,
			Name:      d.F14,
			Price:     deref(d.F2),
			ChangePct: deref(d.F3),
		})
	}
	return out
}

// mapSectors 把 clist 板块列表映射回领域结构。
func mapSectors(r emListResponse) []Sector {
	out := make([]Sector, 0, len(r.Data.Diff))
	for _, d := range r.Data.Diff {
		out = append(out, Sector{
			Name:      d.F14,
			ChangePct: deref(d.F3),
		})
	}
	return out
}
