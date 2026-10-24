// Package market 镜像 easy-stock「行情总览 C07」的领域模型与数据适配（C36）。
// 纯 stdlib，零外部依赖（符合 ADR 0015：Go 运行时零 cgo 依赖）。
package market

import "github.com/jununfly/ZWorkbench/app/internal/datasource"

// Index 主要指数（上证/深证/创业板/沪深300/科创50 等）。
type Index struct {
	Name      string  `json:"name"`
	Code      string  `json:"code"`
	Value     float64 `json:"value"`
	ChangePct float64 `json:"change_pct"` // 涨跌幅，正=涨(红)
}

// StockQuote 个股报价（涨幅榜/跌幅榜）。
type StockQuote struct {
	Code      string  `json:"code"`
	Name      string  `json:"name"`
	Price     float64 `json:"price"`
	ChangePct float64 `json:"change_pct"`
}

// Sector 板块涨跌（题材/行业）。
type Sector struct {
	Name      string  `json:"name"`
	ChangePct float64 `json:"change_pct"`
	Leading   string  `json:"leading"` // 领涨/领跌股
}

// Breadth 涨跌家数（市场宽度）。
type Breadth struct {
	Up       int `json:"up"`
	Down     int `json:"down"`
	Flat     int `json:"flat"`
	LimitUp  int `json:"limit_up"`
	LimitDn  int `json:"limit_down"`
}

// MarketOverview 行情总览聚合结构，对应 ES C07 的最小切片。
// Source/Fallback 是 C36 多源适配的证据字段：标记数据实际来自哪个源、是否走回退。
type MarketOverview struct {
	AsOf       string       `json:"as_of"`     // 快照时间（RFC3339）
	Source     string       `json:"source"`    // 实际命中源名（C36 证据）
	Fallback   bool         `json:"fallback"`  // 是否走回退（非首选源命中）
	Status     datasource.Status `json:"status"`    // 语义状态：ok/unconfigured/source_failed（1-2-5）
	Reason     string       `json:"reason,omitempty"` // 非 ok 时的可读原因（1-2-5）
	Indices    []Index      `json:"indices"`
	Breadth    Breadth      `json:"breadth"`
	TopGainers []StockQuote `json:"top_gainers"`
	TopLosers  []StockQuote `json:"top_losers"`
	Sectors    []Sector     `json:"sectors"`
}

// SetFallbackMeta 实现 datasource.StatusCarrier（ADR 0017; formerly roadmap 1-2-5）。
func (r *MarketOverview) SetFallbackMeta(fallback bool, status datasource.Status, reason, asOf string) {
	r.Fallback = fallback
	r.Status = status
	r.Reason = reason
	if r.AsOf == "" {
		r.AsOf = asOf
	}
}
