package mastery

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

// ImportedFileSource 从本地 JSON 文件导入游资心法库（roadmap 1-2-3 D9）。
//
// 为什么不是「真实源」：游资心法（人物 / 派别 / 心法 / 解读）是民间经验知识，
// 没有任何公开结构化接口提供它。硬接一个源等于编数据，所以本包的可信来源
// 就是 zj 自己的导入文件；内嵌快照只是离线兜底。
type ImportedFileSource struct {
	// Path 是导入文件路径，由调用方显式注入（1-2-1 D3）：包内不隐式读环境变量。
	Path string
}

// NewImportedFileSource 构造导入文件源。
func NewImportedFileSource(path string) ImportedFileSource {
	return ImportedFileSource{Path: path}
}

func (ImportedFileSource) Name() string { return "imported-file" }

// Fetch 读取并校验导入文件。
//
// 失败语义（对齐 1-2-5 三分类，fail-closed）：
//   - 路径为空 → datasource.ErrUnconfigured（「没导入」，不是故障，静默回退内嵌快照）；
//   - 路径非空但读不到 / JSON 坏 / figures 空 / 条目缺 name → 明确错误（真故障，
//     返回带路径与原因的信息，让调用方看得见，而不是静默回退假装导入成功）。
func (s ImportedFileSource) Fetch(_ context.Context) (*MasteryLibrary, error) {
	path := strings.TrimSpace(s.Path)
	if path == "" {
		return nil, fmt.Errorf("%w: imported-file", datasource.ErrUnconfigured)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("imported mastery file %q unreadable: %w", path, err)
	}
	var lib MasteryLibrary
	if err := json.Unmarshal(data, &lib); err != nil {
		return nil, fmt.Errorf("imported mastery file %q parse failed: %w", path, err)
	}
	if len(lib.Figures) == 0 {
		return nil, fmt.Errorf("imported mastery file %q has no figures", path)
	}
	for i, f := range lib.Figures {
		if strings.TrimSpace(f.Name) == "" {
			return nil, fmt.Errorf("imported mastery file %q figure[%d] missing name", path, i)
		}
	}
	lib.Source = "imported-file"
	if strings.TrimSpace(lib.AsOf) == "" {
		lib.AsOf = time.Now().Format(time.RFC3339)
	}
	return &lib, nil
}
