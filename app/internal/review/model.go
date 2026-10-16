// Package review 镜像 easy-stock「大V自动复盘 C10」的领域模型（C36 多源适配）。
// 纯 stdlib，零外部依赖（符合 ADR 0015：Go 运行时零 cgo 依赖）。
package review

import "github.com/jununfly/ZWorkbench/app/internal/datasource"

// AuthorView 一位市场作者的当日观点。
type AuthorView struct {
	Name string `json:"name"`
	View string `json:"view"`
	Date string `json:"date"`
}

// ReviewDigest 大V观点共识聚合（C10 最小切片）：共识 / 分歧 / 盘面事实 / 次日验证条件。
// AsOf/Source/Fallback 是 C36 证据字段。
type ReviewDigest struct {
	AsOf       string           `json:"as_of"`
	Source     string           `json:"source"`
	Fallback   bool             `json:"fallback"`
	Status     datasource.Status `json:"status"`    // 语义状态：ok/unconfigured/source_failed（1-2-5）
	Reason     string           `json:"reason,omitempty"` // 非 ok 时的可读原因（1-2-5）
	Consensus  string           `json:"consensus"`  // 今日大V观点共识：共同关注方向
	Divergence string           `json:"divergence"` // 主要分歧
	Facts      string           `json:"facts"`      // 盘面事实
	NextVerify string           `json:"next_verify"` // 次日需验证的条件
	Authors    []AuthorView     `json:"authors"`
}

// SetFallbackMeta 实现 datasource.StatusCarrier（roadmap 1-2-5）。
func (r *ReviewDigest) SetFallbackMeta(fallback bool, status datasource.Status, reason, asOf string) {
	r.Fallback = fallback
	r.Status = status
	r.Reason = reason
	if r.AsOf == "" {
		r.AsOf = asOf
	}
}
