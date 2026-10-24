package optimization

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
	"github.com/jununfly/ZWorkbench/app/internal/inspection"
)

// seedAssessMark 标记「建议来自本地种子、非实时」，对齐 inspection(C11) 的诚实标注
// （1-2-4 D12）：优化方案整体是建议，外部不提供真实可执行动作，不能把建议伪装成已执行。
const seedAssessMark = " [本地种子·非实时]"

// realHoldingMark 标记「该 target 的当前仓位已用真实持仓覆盖」（与种子建议区分）。
const realHoldingMark = " [基于真实持仓]"

// ImportedFileSource 从本地 portfolio JSON 导入真实持仓输入（ADR 0017; formerly roadmap 1-2-4 D12）。
//
// 与 inspection 共用同一 portfolio 文件（config 单点注入）。优化方案本身是建议，
// 真实输入只用于把各 target 的「当前仓位 from_weight」对齐到用户的真实持仓——
// 命中则覆盖并标记，未命中（如「新增」标的）保持种子原样，不伪造现状。
type ImportedFileSource struct {
	// Path 是导入文件路径，由调用方显式注入（1-2-1 D3）：包内不隐式读环境变量。
	Path string
}

// NewImportedFileSource 构造导入文件源。
func NewImportedFileSource(path string) ImportedFileSource {
	return ImportedFileSource{Path: path}
}

func (ImportedFileSource) Name() string { return "imported-portfolio" }

// Fetch 读取真实持仓文件，叠加内嵌种子的优化建议。
//
// 失败语义（对齐 1-2-5 三分类，fail-closed）：
//   - 路径为空 → datasource.ErrUnconfigured（「没导入」，不是故障，静默回退内嵌快照）；
//   - 路径非空但读不到 / JSON 坏 / 无持仓 → 明确错误（真故障，带路径与原因）。
func (s ImportedFileSource) Fetch(_ context.Context) (*OptimizationPlan, error) {
	path := strings.TrimSpace(s.Path)
	if path == "" {
		return nil, fmt.Errorf("%w: imported-portfolio", datasource.ErrUnconfigured)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("imported portfolio file %q unreadable: %w", path, err)
	}
	var pf inspection.PortfolioFile
	if err := json.Unmarshal(data, &pf); err != nil {
		return nil, fmt.Errorf("imported portfolio file %q parse failed: %w", path, err)
	}
	if len(pf.Holdings) == 0 {
		return nil, fmt.Errorf("imported portfolio file %q has no holdings", path)
	}

	// 建议部分来自内嵌种子（标记非实时）；以真实持仓覆盖各 target 的当前仓位。
	seed, err := parseSeedPlan()
	if err != nil {
		return nil, err
	}
	plan := *seed
	byCode := make(map[string]inspection.Holding, len(pf.Holdings))
	for _, h := range pf.Holdings {
		byCode[h.Code] = h
	}
	for i := range plan.Targets {
		t := &plan.Targets[i]
		if h, ok := byCode[t.Code]; ok {
			t.Name = h.Name
			t.FromWeight = h.Weight
			t.Reason = strings.TrimSpace(t.Reason) + realHoldingMark
		}
	}
	plan.Conditions = strings.TrimSpace(plan.Conditions) + seedAssessMark
	plan.Source = "imported-portfolio"
	if strings.TrimSpace(pf.AsOf) != "" {
		plan.AsOf = pf.AsOf
	} else {
		plan.AsOf = time.Now().Format(time.RFC3339)
	}
	return &plan, nil
}
