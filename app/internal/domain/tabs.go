package domain

// Tab 是工作台多 tab 注册表的一项；stock 只是其中之一（zw 是多页工作台）。
type Tab struct {
	ID    string `json:"id"`
	Title string `json:"title"`
	Group string `json:"group"` // 业务分组，便于侧边栏分类
}

// DefaultTabs 返回初始 tab 列表（占位 + stock 系列）。
// 新增 tab = 在此加一项 + 前端加组件 + Go 加对应 domain stub（微进度切片）。
func DefaultTabs() []Tab {
	return []Tab{
		{ID: "stock-overview", Title: "行情总览", Group: "stock"},
		{ID: "stock-research", Title: "个股分级研究", Group: "stock"},
		{ID: "stock-limitup", Title: "超短连板", Group: "stock"},
		{ID: "coding-evidence", Title: "编码证据", Group: "core"},
		{ID: "settings", Title: "设置 / LLM", Group: "system"},
	}
}
