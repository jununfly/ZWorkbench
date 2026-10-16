// Package buildguard holds the mechanical guards for ADR 0015's dependency
// boundary (roadmap 1-1-1).
//
// ADR 0015 keeps the deviation from C32 bounded: the Go runtime stays free of
// cgo and of third-party native dependencies, Node/Electron lives in
// `app/electron` as a build-time devDependency only, and the Python core stays
// zero dependency. The Python half of that boundary is guarded by
// `tests/test_zero_dependency_guard.py`; this package is the Go half.
//
// A boundary nobody can check silently erodes, so these tests assert it
// mechanically:
//
//   - `app/go.mod` may only require modules on the explicit pure-Go allowlist.
//     The allowlist is fail-closed: a new dependency is a test failure until it
//     is added here together with the reason it is cgo-free.
//   - no Go source under `app/` uses cgo (`import "C"` or `#cgo` directives).
//   - `app/electron/package.json` declares Electron as a devDependency and no
//     runtime dependency at all.
//   - `CGO_ENABLED=0 go build ./...` compiles (opt-in, see TestCgoFreeBuild).
package buildguard

import (
	"encoding/json"
	"go/parser"
	"go/token"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// appRoot resolves to `app/` from this package's directory (app/internal/buildguard).
func appRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	return filepath.Clean(filepath.Join(dir, "..", ".."))
}

// pureGoAllowlist is the exhaustive set of modules `app/go.mod` may require.
// The value is the recorded reason each entry is cgo-free; keeping the reason
// next to the entry is what makes "add a dependency" a deliberate act rather
// than an invisible drift.
var pureGoAllowlist = map[string]string{
	"github.com/google/uuid":               "pure Go UUID generation, no cgo",
	"github.com/mattn/go-isatty":           "pure Go tty detection via syscall, no cgo",
	"github.com/dustin/go-humanize":        "pure Go formatting helpers, no cgo",
	"github.com/ncruces/go-strftime":       "pure Go strftime translation of SQLite's C format strings, no cgo",
	"github.com/remyoudompheng/bigfft":     "pure Go big-int FFT used by modernc mathutil, no cgo",
	"golang.org/x/sys":                     "pure Go syscall layer (Unix syscalls, no cgo)",
	"modernc.org/libc":                     "modernc: C stdlib transpiled to Go, no cgo",
	"modernc.org/mathutil":                 "modernc: pure Go math primitives, no cgo",
	"modernc.org/memory":                   "modernc: pure Go allocator, no cgo",
	"modernc.org/sqlite":                   "modernc: SQLite transpiled to Go, no cgo (1-5-5 D1)",
}

// parseGoModRequires returns the module paths declared by require directives:
// both the single-line form (`require m v`) and the block form, and both with
// and without a trailing `// indirect` comment.
func parseGoModRequires(content string) []string {
	var out []string
	inBlock := false
	for _, raw := range strings.Split(content, "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "//") {
			continue
		}
		if line == "require (" {
			inBlock = true
			continue
		}
		if inBlock && line == ")" {
			inBlock = false
			continue
		}
		if inBlock {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				out = append(out, fields[0])
			}
			continue
		}
		if strings.HasPrefix(line, "require ") {
			fields := strings.Fields(strings.TrimPrefix(line, "require "))
			if len(fields) >= 2 {
				out = append(out, fields[0])
			}
		}
	}
	return out
}

// allowlisted reports whether a module path is on the allowlist, plus why.
func allowlisted(path string) (bool, string) {
	if reason, ok := pureGoAllowlist[path]; ok {
		return true, reason
	}
	return false, ""
}

func TestParseGoModRequires(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want []string
	}{
		{
			name: "single line",
			in:   "module x\n\ngo 1.26\n\nrequire github.com/google/uuid v1.6.0\n",
			want: []string{"github.com/google/uuid"},
		},
		{
			name: "block with indirect comment",
			in:   "require (\n\tmodernc.org/sqlite v1.60.1 // indirect\n\tgolang.org/x/sys v0.48.0 // indirect\n)\n",
			want: []string{"modernc.org/sqlite", "golang.org/x/sys"},
		},
		{
			name: "block without comment and trailing blank",
			in:   "require (\n\ta/b v1.0.0\n\n\tc/d v2.0.0\n)\n",
			want: []string{"a/b", "c/d"},
		},
		{
			name: "no require at all",
			in:   "module x\n\ngo 1.26\n",
			want: nil,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := parseGoModRequires(tc.in)
			if len(got) != len(tc.want) {
				t.Fatalf("parseGoModRequires() = %v, want %v", got, tc.want)
			}
			for i := range got {
				if got[i] != tc.want[i] {
					t.Fatalf("parseGoModRequires()[%d] = %q, want %q", i, got[i], tc.want[i])
				}
			}
		})
	}
}

func TestAllowlistRejectsUnknownModule(t *testing.T) {
	// Fail-closed: an unrecorded module is rejected even when it happens to be
	// pure Go, so adding one always shows up as a deliberate allowlist edit.
	for _, path := range []string{
		"github.com/mattn/go-sqlite3", // cgo SQLite driver
		"github.com/some/newdep",
		"modernc.org/sqlite2",
	} {
		if ok, _ := allowlisted(path); ok {
			t.Fatalf("allowlisted(%q) = true, want false (not on allowlist)", path)
		}
	}
	for path, wantReason := range pureGoAllowlist {
		ok, reason := allowlisted(path)
		if !ok {
			t.Fatalf("allowlisted(%q) = false, want true", path)
		}
		if strings.TrimSpace(reason) == "" {
			t.Fatalf("allowlist entry %q has no recorded reason", path)
		}
		if wantReason != reason {
			t.Fatalf("allowlist entry %q reason = %q, want %q", path, reason, wantReason)
		}
	}
}

func TestGoModOnlyRequiresAllowlistedPureGoModules(t *testing.T) {
	root := appRoot(t)
	raw, err := os.ReadFile(filepath.Join(root, "go.mod"))
	if err != nil {
		t.Fatalf("read go.mod: %v", err)
	}
	requires := parseGoModRequires(string(raw))
	if len(requires) == 0 {
		t.Fatalf("go.mod declares no require directive; the guard would pass vacuously")
	}
	for _, path := range requires {
		ok, reason := allowlisted(path)
		if !ok {
			t.Errorf("go.mod requires %q, which is not on the pure-Go allowlist; "+
				"if it is cgo-free, add it to pureGoAllowlist with the reason", path)
			continue
		}
		t.Logf("allowed %s: %s", path, reason)
	}
}

// TestNoCgoInGoSources parses every Go file under `app/` and rejects
// `import "C"`. cgo is only reachable through that pseudo-import, so an AST
// check is both sufficient and free of the false positives a text search for
// "cgo" would produce (doc comments, build-tag lines, string literals).
func TestNoCgoInGoSources(t *testing.T) {
	skipDirs := map[string]bool{
		"node_modules": true,
		"dist":         true,
		".git":         true,
	}
	root := appRoot(t)
	fset := token.NewFileSet()
	checked := 0
	err := filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if skipDirs[d.Name()] {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(d.Name(), ".go") {
			return nil
		}
		file, err := parser.ParseFile(fset, path, nil, parser.SkipObjectResolution)
		if err != nil {
			t.Errorf("parse %s: %v", path, err)
			return nil
		}
		checked++
		for _, imp := range file.Imports {
			unquoted, err := strconv.Unquote(imp.Path.Value)
			if err != nil {
				unquoted = imp.Path.Value
			}
			if unquoted == "C" {
				t.Errorf("cgo usage found: %s",
					formatOffender(root, path, fset.Position(imp.Pos()).Line, `import "C"`))
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walk app/: %v", err)
	}
	if checked == 0 {
		t.Fatalf("no Go file found under app/; the guard would pass vacuously")
	}
	t.Logf("parsed %d Go files, none imports \"C\"", checked)
}

func formatOffender(root, path string, line int, text string) string {
	rel, err := filepath.Rel(root, path)
	if err != nil {
		rel = path
	}
	return rel + ":" + itoa(line) + ": " + text
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var buf [20]byte
	pos := len(buf)
	for n > 0 {
		pos--
		buf[pos] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[pos:])
}

func TestElectronIsDevDependencyOnly(t *testing.T) {
	root := appRoot(t)
	raw, err := os.ReadFile(filepath.Join(root, "electron", "package.json"))
	if err != nil {
		t.Fatalf("read electron/package.json: %v", err)
	}
	var pkg struct {
		Name            string            `json:"name"`
		Dependencies    map[string]string `json:"dependencies"`
		DevDependencies map[string]string `json:"devDependencies"`
	}
	if err := json.Unmarshal(raw, &pkg); err != nil {
		t.Fatalf("parse electron/package.json: %v", err)
	}
	if len(pkg.Dependencies) != 0 {
		t.Errorf("electron/package.json declares runtime dependencies %v; "+
			"Node/Electron must stay a build-time devDependency (ADR 0015)", pkg.Dependencies)
	}
	if _, ok := pkg.DevDependencies["electron"]; !ok {
		t.Errorf("electron is not a devDependency in electron/package.json")
	}
}

// TestCgoFreeBuild is the "it actually compiles without cgo" half of the guard.
// It shells out to the toolchain, so it is opt-in via ZW_ZERODEP_BUILD=1: the
// default suite must stay hermetic and fast, while CI (or a pre-release check)
// can turn the compile proof on.
func TestCgoFreeBuild(t *testing.T) {
	if os.Getenv("ZW_ZERODEP_BUILD") != "1" {
		t.Skip("set ZW_ZERODEP_BUILD=1 to also prove CGO_ENABLED=0 go build ./...")
	}
	goBin, err := exec.LookPath("go")
	if err != nil {
		t.Skipf("go toolchain not available: %v", err)
	}
	cmd := exec.Command(goBin, "build", "./...")
	cmd.Dir = appRoot(t)
	cmd.Env = append(os.Environ(), "CGO_ENABLED=0")
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("CGO_ENABLED=0 go build ./... failed: %v\n%s", err, out)
	}
}
