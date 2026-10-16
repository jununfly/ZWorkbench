// Package limitup 镜像 easy-stock「超短连板/题材/情绪 C09」的领域模型与数据适配（C36）。
// 纯 stdlib，零外部依赖（符合 ADR 0015：Go 运行时零 cgo 依赖）。
package limitup

import "github.com/jununfly/ZWorkbench/app/internal/datasource"

// LimitUpStock 连板个股。
type LimitUpStock struct {
	Code      string  `json:"code"`
	Name      string  `json:"name"`
	Price     float64 `json:"price"`
	ChangePct float64 `json:"change_pct"`
	Reason    string  `json:"reason"` // 涨停原因 / 题材标签
}

// Tier 连板梯队：同一连板天数的股票集合（days=1 为首板）。
type Tier struct {
	Days   int            `json:"days"`
	Stocks []LimitUpStock `json:"stocks"`
}

// Theme 题材（趋势题材雷达的一项）。
type Theme struct {
	Name         string  `json:"name"`
	Code         string  `json:"code"`           // 板块代码（BKxxxx），用于查成分股龙头
	LimitUpCount int     `json:"limit_up_count"` // 该题材内涨停家数
	Strength     float64 `json:"strength"`       // 强度 0~100
	Leading      string  `json:"leading"`        // 龙头 / 代表股
}

// Sentiment 情绪周期（启动/发酵/高潮/分歧/退潮）。
type Sentiment struct {
	Stage    string `json:"stage"`     // 阶段名
	MaxBoard int    `json:"max_board"` // 全市场最高连板高度
	LimitUp  int    `json:"limit_up"`  // 全市场涨停数
	LimitDn  int    `json:"limit_down"`// 全市场跌停数
}

// LimitUpBoard 超短连板/题材/情绪聚合结构，对应 ES C09 的最小切片。
// Source/Fallback 是 C36 多源适配的证据字段：标记数据实际来自哪个源、是否走回退。
type LimitUpBoard struct {
	AsOf     string           `json:"as_of"`     // 快照时间（RFC3339）
	Source   string           `json:"source"`    // 实际命中源名（C36 证据）
	Fallback bool             `json:"fallback"`  // 是否走回退（非首选源命中）
	Status   datasource.Status `json:"status"`    // 语义状态：ok/unconfigured/source_failed（1-2-5）
	Reason   string           `json:"reason,omitempty"` // 非 ok 时的可读原因（1-2-5）
	Tiers    []Tier           `json:"tiers"`     // 连板梯队（按 days 降序）
	Themes   []Theme          `json:"themes"`    // 题材雷达
	Sentiment Sentiment       `json:"sentiment"`
}

// SetFallbackMeta 实现 datasource.StatusCarrier（roadmap 1-2-5）。
func (r *LimitUpBoard) SetFallbackMeta(fallback bool, status datasource.Status, reason, asOf string) {
	r.Fallback = fallback
	r.Status = status
	r.Reason = reason
	if r.AsOf == "" {
		r.AsOf = asOf
	}
}
