// Package optimization 镜像 easy-stock「AI持仓优化 C12」的领域模型（C36 多源适配）。
// 纯 stdlib，零外部依赖（符合 ADR 0015：Go 运行时零 cgo 依赖）。
package optimization

import "github.com/jununfly/ZWorkbench/app/internal/datasource"

// Target 一只股票的优化动作：减持 / 保持 / 新增，附起始与目标仓位与理由。
type Target struct {
	Code       string  `json:"code"`
	Name       string  `json:"name"`
	Action     string  `json:"action"`      // 减持 / 保持 / 新增
	FromWeight float64 `json:"from_weight"`
	ToWeight   float64 `json:"to_weight"`
	Reason     string  `json:"reason"`
}

// OptimizationPlan AI持仓优化方案（C12 最小切片）：原 / 目标同次复评 + 逐股对照 + 条件。
// AsOf/Source/Fallback 是 C36 证据字段。
type OptimizationPlan struct {
	AsOf           string           `json:"as_of"`
	Source         string           `json:"source"`
	Fallback       bool             `json:"fallback"`
	Status         datasource.Status `json:"status"`    // 语义状态：ok/unconfigured/source_failed（1-2-5）
	Reason         string           `json:"reason,omitempty"` // 非 ok 时的可读原因（1-2-5）
	OriginalScore  float64          `json:"original_score"`
	OptimizedScore float64          `json:"optimized_score"`
	Improvement    float64          `json:"improvement"`
	Targets        []Target         `json:"targets"`
	Conditions     string           `json:"conditions"` // 入场 / 退出条件
}

// SetFallbackMeta 实现 datasource.StatusCarrier（ADR 0017; formerly roadmap 1-2-5）。
func (r *OptimizationPlan) SetFallbackMeta(fallback bool, status datasource.Status, reason, asOf string) {
	r.Fallback = fallback
	r.Status = status
	r.Reason = reason
	if r.AsOf == "" {
		r.AsOf = asOf
	}
}
