package inspection

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

// seedAssessMark 标记「主观评估来自本地种子、非实时」，对齐 review(C10) 的
// NextVerify 诚实标注（1-2-4 D11）：外部不提供持仓巡检的评分判断，不能把种子
// 评分伪装成实时结论。
const seedAssessMark = " [本地种子·非实时]"

// ImportedFileSource 从本地 portfolio JSON 导入真实持仓输入（roadmap 1-2-4 D11）。
//
// 为什么不是「真实源」：持仓是私有数据，没有任何公开结构化接口提供它；硬接一个
// 源等于编数据。所以本包的可信事实来源就是 zj 自己的持仓导出文件（JSON），内嵌
// 种子快照只兜底评估部分（四维评分/风险等级）与离线场景。
//
// 文件形态：{ as_of, cash, total_assets, holdings: [ {code,name,weight,cost,price,pnl_pct} ] }。
type ImportedFileSource struct {
	// Path 是导入文件路径，由调用方显式注入（1-2-1 D3）：包内不隐式读环境变量。
	Path string
}

// NewImportedFileSource 构造导入文件源。
func NewImportedFileSource(path string) ImportedFileSource {
	return ImportedFileSource{Path: path}
}

func (ImportedFileSource) Name() string { return "imported-portfolio" }

// Fetch 读取并校验真实持仓文件，叠加内嵌种子的主观评估部分。
//
// 失败语义（对齐 1-2-5 三分类，fail-closed）：
//   - 路径为空 → datasource.ErrUnconfigured（「没导入」，不是故障，静默回退内嵌快照）；
//   - 路径非空但读不到 / JSON 坏 / 缺 total_assets|cash / 无持仓 → 明确错误
//     （真故障，返回带路径与原因的信息，让调用方看得见，而不是静默回退假装成功）。
func (s ImportedFileSource) Fetch(_ context.Context) (*InspectionReport, error) {
	path := strings.TrimSpace(s.Path)
	if path == "" {
		return nil, fmt.Errorf("%w: imported-portfolio", datasource.ErrUnconfigured)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("imported portfolio file %q unreadable: %w", path, err)
	}
	var pf PortfolioFile
	if err := json.Unmarshal(data, &pf); err != nil {
		return nil, fmt.Errorf("imported portfolio file %q parse failed: %w", path, err)
	}
	if pf.TotalAssets <= 0 {
		return nil, fmt.Errorf("imported portfolio file %q missing total_assets", path)
	}
	if len(pf.Holdings) == 0 {
		return nil, fmt.Errorf("imported portfolio file %q has no holdings", path)
	}

	// 事实字段来自真实文件；评估字段来自内嵌种子（标记非实时）。
	seed, err := parseSeedReport()
	if err != nil {
		return nil, err
	}
	rep := *seed
	rep.TotalAssets = pf.TotalAssets
	rep.Cash = pf.Cash
	rep.Holdings = append([]Holding(nil), pf.Holdings...)
	rep.Pnl = computePnl(pf)
	for i := range rep.Dimensions {
		rep.Dimensions[i].Basis = strings.TrimSpace(rep.Dimensions[i].Basis) + seedAssessMark
	}
	rep.Source = "imported-portfolio"
	if strings.TrimSpace(pf.AsOf) != "" {
		rep.AsOf = pf.AsOf
	} else {
		rep.AsOf = time.Now().Format(time.RFC3339)
	}
	return &rep, nil
}

// PortfolioFile 是真实持仓导入文件的形态（1-2-4 D11）。
type PortfolioFile struct {
	AsOf        string    `json:"as_of"`
	Cash        float64   `json:"cash"`
	TotalAssets float64   `json:"total_assets"`
	Holdings    []Holding `json:"holdings"`
}

// computePnl 用真实持仓加权计算组合盈亏：Σ(权重% × 总资产 × 盈亏%)。
func computePnl(pf PortfolioFile) float64 {
	var pnl float64
	for _, h := range pf.Holdings {
		pnl += (h.Weight / 100) * pf.TotalAssets * (h.PnlPct / 100)
	}
	return pnl
}
