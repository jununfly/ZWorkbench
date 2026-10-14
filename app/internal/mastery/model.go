// Package mastery 镜像 easy-stock「游资心法与AI Copilot C19」的领域模型（C36 多源适配）。
// 纯 stdlib，零外部依赖（符合 ADR 0015：Go 运行时零 cgo 依赖）。
package mastery

// Figure 一位游资人物：派别 / 心法 / 解读。
type Figure struct {
	Name    string `json:"name"`
	School  string `json:"school"` // 派别
	Tenet   string `json:"tenet"`  // 心法
	Insight string `json:"insight"`
}

// MasteryLibrary 游资心法库（C19 最小切片）：人物资料与心法。
// AsOf/Source/Fallback 是 C36 证据字段。
type MasteryLibrary struct {
	AsOf     string    `json:"as_of"`
	Source   string    `json:"source"`
	Fallback bool      `json:"fallback"`
	Figures  []Figure  `json:"figures"`
}
