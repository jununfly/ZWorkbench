// Package research 镜像 easy-stock「个股分级研究 C08」的领域模型（C36 多源适配）。
// 纯 stdlib，零外部依赖（符合 ADR 0015：Go 运行时零 cgo 依赖）。
package research

import "github.com/jununfly/ZWorkbench/app/internal/datasource"

// ResearchStock 一只被研究的个股：用途 / 周期 / 核心判断 + 支持与反对证据。
type ResearchStock struct {
	Code      string  `json:"code"`
	Name      string  `json:"name"`
	Price     float64 `json:"price"`
	ChangePct float64 `json:"change_pct"`
	Purpose   string  `json:"purpose"` // 观察 / 准备新开仓 / 已有持仓
	Cycle     string  `json:"cycle"`   // 超短 / 波段 / 中期
	Core      string  `json:"core"`    // 核心判断
	Support   string  `json:"support"` // 支持证据
	Against   string  `json:"against"` // 反对证据
}

// StockResearch 个股分级研究聚合（C08 最小切片）。
// AsOf/Source/Fallback 是 C36 证据字段：标记数据来源与是否走回退。
type StockResearch struct {
	AsOf     string           `json:"as_of"`
	Source   string           `json:"source"`
	Fallback bool             `json:"fallback"`
	Status   datasource.Status `json:"status"`    // 语义状态：ok/unconfigured/source_failed（1-2-5）
	Reason   string           `json:"reason,omitempty"` // 非 ok 时的可读原因（1-2-5）
	Stocks   []ResearchStock  `json:"stocks"`
}

// SetFallbackMeta 实现 datasource.StatusCarrier（roadmap 1-2-5）。
func (r *StockResearch) SetFallbackMeta(fallback bool, status datasource.Status, reason, asOf string) {
	r.Fallback = fallback
	r.Status = status
	r.Reason = reason
	if r.AsOf == "" {
		r.AsOf = asOf
	}
}
