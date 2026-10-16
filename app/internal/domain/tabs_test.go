package domain

import (
	"testing"
)

func TestDefaultTabsRegistry(t *testing.T) {
	tabs := DefaultTabs()
	if len(tabs) != 10 {
		t.Fatalf("默认 tab 应 10 个，得到 %d", len(tabs))
	}
	seen := map[string]bool{}
	validGroups := map[string]bool{"stock": true, "portfolio": true, "learn": true, "core": true, "system": true, "agent": true}
	for _, tb := range tabs {
		if tb.ID == "" || tb.Title == "" {
			t.Fatalf("tab 缺 ID/Title：%+v", tb)
		}
		if seen[tb.ID] {
			t.Fatalf("tab ID 重复：%s", tb.ID)
		}
		seen[tb.ID] = true
		if !validGroups[tb.Group] {
			t.Fatalf("tab %s 的 Group %q 不在合法分组", tb.ID, tb.Group)
		}
	}
	for _, must := range []string{"coding-evidence", "stock-overview", "settings", "chat"} {
		if !seen[must] {
			t.Fatalf("缺少关键 tab：%s", must)
		}
	}
}
