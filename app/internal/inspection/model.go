// Package inspection 镜像 easy-stock「持仓AI巡检 C11」的领域模型（C36 多源适配）。
// 纯 stdlib，零外部依赖（符合 ADR 0015：Go 运行时零 cgo 依赖）。
package inspection

import "github.com/jununfly/ZWorkbench/app/internal/datasource"

// Holding 一只持仓：仓位 / 成本 / 现价 / 盈亏。
type Holding struct {
	Code    string  `json:"code"`
	Name    string  `json:"name"`
	Weight  float64 `json:"weight"` // 仓位占比 %
	Cost    float64 `json:"cost"`   // 成本
	Price   float64 `json:"price"`  // 现价
	PnlPct  float64 `json:"pnl_pct"` // 盈亏 %
}

// Dimension 四维综合评分的一项：持有逻辑 / 组合结构 / 风险管理 / 策略匹配。
type Dimension struct {
	Name   string  `json:"name"`
	Weight float64 `json:"weight"`
	Score  float64 `json:"score"`
	Basis  string  `json:"basis"` // 评分依据（可展开核验）
}

// InspectionReport 持仓巡检报告（C11 最小切片）：组合盈亏 + 四维评分 + 逐股。
// AsOf/Source/Fallback 是 C36 证据字段。
type InspectionReport struct {
	AsOf        string           `json:"as_of"`
	Source      string           `json:"source"`
	Fallback    bool             `json:"fallback"`
	Status      datasource.Status `json:"status"`    // 语义状态：ok/unconfigured/source_failed（1-2-5）
	Reason      string           `json:"reason,omitempty"` // 非 ok 时的可读原因（1-2-5）
	TotalAssets float64          `json:"total_assets"`
	Cash        float64          `json:"cash"`
	Pnl         float64          `json:"pnl"`
	RiskLevel   string           `json:"risk_level"`
	Score       float64          `json:"score"`
	Dimensions  []Dimension      `json:"dimensions"`
	Holdings    []Holding        `json:"holdings"`
}

// SetFallbackMeta 实现 datasource.StatusCarrier（roadmap 1-2-5）。
func (r *InspectionReport) SetFallbackMeta(fallback bool, status datasource.Status, reason, asOf string) {
	r.Fallback = fallback
	r.Status = status
	r.Reason = reason
	if r.AsOf == "" {
		r.AsOf = asOf
	}
}
