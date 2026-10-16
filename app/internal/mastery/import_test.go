package mastery

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

// writeImport 在临时目录写一个导入文件，返回路径。
func writeImport(t *testing.T, body string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "mastery.json")
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatalf("写导入文件失败：%v", err)
	}
	return p
}

const sampleImportJSON = `{"as_of":"2026-10-16T10:00:00+08:00","figures":[
{"name":"赵老哥","school":"打板/龙头","tenet":"只做龙头，不做杂毛。","insight":"情绪周期比个股重要。"},
{"name":"作手新一","school":"连板/分歧","tenet":"买在分歧，卖在一致。","insight":"中位股最危险。"}]}`

// TestImportedFileSourceUnconfigured 路径为空=「没导入」，语义是未配置而非故障。
func TestImportedFileSourceUnconfigured(t *testing.T) {
	_, err := NewImportedFileSource("").Fetch(context.Background())
	if !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("空路径应返回 ErrUnconfigured，得到 %v", err)
	}
	if _, err := NewImportedFileSource("   ").Fetch(context.Background()); !errors.Is(err, datasource.ErrUnconfigured) {
		t.Fatalf("空白路径同样应视为未配置，得到 %v", err)
	}
}

func TestImportedFileSourceLoads(t *testing.T) {
	p := writeImport(t, sampleImportJSON)
	lib, err := NewImportedFileSource(p).Fetch(context.Background())
	if err != nil {
		t.Fatalf("导入失败：%v", err)
	}
	if lib.Source != "imported-file" {
		t.Fatalf("Source 应为 imported-file，得到 %q", lib.Source)
	}
	if len(lib.Figures) != 2 || lib.Figures[0].Name != "赵老哥" {
		t.Fatalf("导入内容错误：%+v", lib.Figures)
	}
	if lib.AsOf != "2026-10-16T10:00:00+08:00" {
		t.Fatalf("文件自带 AsOf 应被保留，得到 %q", lib.AsOf)
	}
}

// TestImportedFileSourceFillsAsOf 文件没写 as_of 时补当前时间（不留空）。
func TestImportedFileSourceFillsAsOf(t *testing.T) {
	p := writeImport(t, `{"figures":[{"name":"A","tenet":"t","insight":"i"}]}`)
	lib, err := NewImportedFileSource(p).Fetch(context.Background())
	if err != nil {
		t.Fatalf("导入失败：%v", err)
	}
	if strings.TrimSpace(lib.AsOf) == "" {
		t.Fatalf("AsOf 缺失时应自动补当前时间")
	}
}

// TestImportedFileSourceFailureModes 三类故障都必须 fail-closed 并带上路径与原因，
// 不能静默回退到内嵌快照假装导入成功。
func TestImportedFileSourceFailureModes(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "nope.json")
	badJSON := writeImport(t, `{"figures":[`)
	empty := writeImport(t, `{"figures":[]}`)
	noName := writeImport(t, `{"figures":[{"tenet":"t"}]}`)

	cases := []struct {
		name    string
		path    string
		wantMsg string
	}{
		{"文件不存在", missing, "unreadable"},
		{"JSON 损坏", badJSON, "parse failed"},
		{"figures 为空", empty, "no figures"},
		{"条目缺 name", noName, "missing name"},
	}
	for _, c := range cases {
		_, err := NewImportedFileSource(c.path).Fetch(context.Background())
		if err == nil {
			t.Fatalf("%s 应失败（fail-closed），却返回成功", c.name)
		}
		if !strings.Contains(err.Error(), c.wantMsg) {
			t.Fatalf("%s 错误信息应含 %q，得到 %q", c.name, c.wantMsg, err.Error())
		}
		if !strings.Contains(err.Error(), c.path) {
			t.Fatalf("%s 错误信息应带文件路径，得到 %q", c.name, err.Error())
		}
	}
}
