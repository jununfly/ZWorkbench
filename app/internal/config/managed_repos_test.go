package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestManagedReposPersistence(t *testing.T) {
	dir := t.TempDir()
	os.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))
	defer os.Unsetenv("ZW_CONFIG")

	// 用 Load 取默认（空 managed repos），再写入并回读。
	c := Load()
	if len(c.ManagedRepos().Repos) != 0 {
		t.Fatalf("默认应为空 managed repos，实际 %d", len(c.ManagedRepos().Repos))
	}

	want := ManagedRepos{Repos: []RepoSpec{
		{Name: "ZWorkbench", Path: "/repo/zw", Environments: []string{"local", "container"}},
	}}
	c.SetManagedRepos(want)
	if err := c.SaveManagedRepos(); err != nil {
		t.Fatalf("SaveManagedRepos: %v", err)
	}

	// 重新 Load（同路径）应读到持久化值。
	c2 := Load()
	got := c2.ManagedRepos()
	if len(got.Repos) != 1 {
		t.Fatalf("持久化后应有 1 个仓库，实际 %d", len(got.Repos))
	}
	if got.Repos[0].Name != "ZWorkbench" || got.Repos[0].Path != "/repo/zw" {
		t.Fatalf("仓库内容不符：%#v", got.Repos[0])
	}
	if len(got.Repos[0].Environments) != 2 || got.Repos[0].Environments[1] != "container" {
		t.Fatalf("环境枚举不符：%#v", got.Repos[0].Environments)
	}
}

func TestManagedReposEnvOverride(t *testing.T) {
	dir := t.TempDir()
	os.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))
	defer os.Unsetenv("ZW_CONFIG")

	env := `[{"name":"EnvRepo","path":"/e","environments":["local"]}]`
	os.Setenv("ZW_MANAGED_REPOS", env)
	defer os.Unsetenv("ZW_MANAGED_REPOS")

	c := Load()
	got := c.ManagedRepos()
	if len(got.Repos) != 1 || got.Repos[0].Name != "EnvRepo" {
		t.Fatalf("env 覆盖未生效：%#v", got.Repos)
	}
}

func TestManagedReposBadEnvIgnored(t *testing.T) {
	dir := t.TempDir()
	os.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))
	defer os.Unsetenv("ZW_CONFIG")
	os.Setenv("ZW_MANAGED_REPOS", "not-json")
	defer os.Unsetenv("ZW_MANAGED_REPOS")

	// 非法 JSON 必须静默忽略，不 panic。
	c := Load()
	if c == nil {
		t.Fatal("Load 不应因坏 env 返回 nil")
	}
}
