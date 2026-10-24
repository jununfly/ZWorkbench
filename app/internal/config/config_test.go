package config

import (
	"testing"
)

func TestAddrBindsLoopback(t *testing.T) {
	c := &Config{Port: "18080"}
	if got := c.Addr(); got != "127.0.0.1:18080" {
		t.Fatalf("Addr 期望 127.0.0.1:18080，得到 %q", got)
	}
}

func TestLoadDefaults(t *testing.T) {
	t.Setenv("ZW_PORT", "")
	t.Setenv("ZW_TOKEN", "")
	t.Setenv("ZW_DB", "")
	c := Load()
	if c.Port != "18080" {
		t.Fatalf("默认端口应为 18080，得到 %q", c.Port)
	}
	if c.DB != "mem" {
		t.Fatalf("默认 DB 应为 mem，得到 %q", c.DB)
	}
	if c.Token == "" {
		t.Fatalf("未设 ZW_TOKEN 应自动生成 token")
	}
	if len(c.Token) != 64 {
		t.Fatalf("token 应为 64 位 hex，得到长度 %d", len(c.Token))
	}
	for _, r := range c.Token {
		if !((r >= '0' && r <= '9') || (r >= 'a' && r <= 'f') || (r >= 'A' && r <= 'F')) {
			t.Fatalf("token 应为 hex 串，得到 %q", c.Token)
		}
	}
}

func TestSetLLMRoundTrip(t *testing.T) {
	c := &Config{}
	want := LLMConfig{Enabled: true, Model: "gpt-4o", APIKey: "sk-x", BaseURL: "https://x"}
	c.SetLLM(want)
	if got := c.LLM(); got != want {
		t.Fatalf("LLM 往返不一致：%+v vs %+v", got, want)
	}
}

func TestSaveLoadLLMRoundTrip(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", dir+"/config.json")
	c := &Config{}
	c.SetLLM(LLMConfig{Enabled: true, Model: "deepseek", APIKey: "sk-test", BaseURL: "https://api.deepseek.com/v1"})
	if err := c.SaveLLM(); err != nil {
		t.Fatalf("SaveLLM 失败：%v", err)
	}
	var c2 Config
	c2.LoadLLM()
	got := c2.LLM()
	if !got.Enabled || got.Model != "deepseek" || got.APIKey != "sk-test" || got.BaseURL != "https://api.deepseek.com/v1" {
		t.Fatalf("LoadLLM 往返不一致：%+v", got)
	}
}

func TestDataSourceDefaultsOffAndRoundTrip(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", dir+"/config.json")
	c := &Config{}
	if ds := c.DataSource(); ds.Enabled {
		t.Fatalf("默认数据源必须关闭（1-2-1 D2）")
	}
	if c.DataSource().Usable() {
		t.Fatalf("默认数据源不应 usable")
	}
	want := DataSourceConfig{Enabled: true, BaseURL: "https://api.example.com", Token: "t", TimeoutSec: 8}
	c.SetDataSource(want)
	if err := c.SaveDataSource(); err != nil {
		t.Fatalf("SaveDataSource 失败：%v", err)
	}
	var c2 Config
	c2.LoadDataSource()
	got := c2.DataSource()
	if !got.Enabled || got.BaseURL != want.BaseURL || got.Token != want.Token || got.TimeoutSec != want.TimeoutSec {
		t.Fatalf("LoadDataSource 往返不一致：%+v", got)
	}
}

// TestDataFilesRoundTrip 导入路径段（ADR 0017; formerly roadmap 1-2-3 D9）必须能持久化并读回，
// 且不能被 LLM / 数据源段落的保存抹掉。
func TestDataFilesRoundTrip(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", dir+"/config.json")
	c := &Config{}
	if p := c.MasteryPath(); p != "" {
		t.Fatalf("默认导入路径应为空（未导入），得到 %q", p)
	}
	c.SetDataFiles(DataFiles{MasteryPath: dir + "/mastery.json"})
	if err := c.SaveDataSource(); err != nil {
		t.Fatalf("SaveDataSource 失败：%v", err)
	}
	var c2 Config
	c2.LoadDataSource()
	if got := c2.MasteryPath(); got != dir+"/mastery.json" {
		t.Fatalf("导入路径往返不一致，得到 %q", got)
	}
}

// TestMasteryPathEnvOverride ZW_MASTERY_PATH 覆盖 config.json（与数据源同覆盖顺序）。
func TestMasteryPathEnvOverride(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", dir+"/config.json")
	c := &Config{}
	c.SetDataFiles(DataFiles{MasteryPath: dir + "/from-file.json"})
	if err := c.SaveDataSource(); err != nil {
		t.Fatalf("SaveDataSource 失败：%v", err)
	}
	t.Setenv("ZW_MASTERY_PATH", dir+"/from-env.json")
	var c2 Config
	c2.LoadDataSource()
	if got := c2.MasteryPath(); got != dir+"/from-env.json" {
		t.Fatalf("ZW_MASTERY_PATH 应覆盖 config.json，得到 %q", got)
	}
}

// TestSaveLLMDoesNotWipeDataFiles 三段共写：存 LLM 不能把导入路径抹掉。
func TestSaveLLMDoesNotWipeDataFiles(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", dir+"/config.json")
	c := &Config{}
	c.SetDataFiles(DataFiles{MasteryPath: dir + "/mastery.json"})
	if err := c.SaveDataSource(); err != nil {
		t.Fatalf("SaveDataSource 失败：%v", err)
	}
	c2 := &Config{}
	c2.LoadDataSource()
	c2.SetLLM(LLMConfig{Enabled: true, Model: "deepseek"})
	if err := c2.SaveLLM(); err != nil {
		t.Fatalf("SaveLLM 失败：%v", err)
	}
	var c3 Config
	c3.LoadDataSource()
	if got := c3.MasteryPath(); got != dir+"/mastery.json" {
		t.Fatalf("保存 LLM 把导入路径抹掉了，得到 %q", got)
	}
}

func TestSaveDataSourceDoesNotWipeLLM(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", dir+"/config.json")
	c := &Config{}
	c.SetLLM(LLMConfig{Enabled: true, Model: "deepseek", APIKey: "sk-x", BaseURL: "https://api.deepseek.com/v1"})
	if err := c.SaveLLM(); err != nil {
		t.Fatalf("SaveLLM 失败：%v", err)
	}
	c.SetDataSource(DataSourceConfig{Enabled: true, BaseURL: "https://api.example.com"})
	if err := c.SaveDataSource(); err != nil {
		t.Fatalf("SaveDataSource 失败：%v", err)
	}
	var c2 Config
	c2.LoadLLM()
	if !c2.LLM().Enabled || c2.LLM().APIKey != "sk-x" {
		t.Fatalf("保存数据源把 LLM 配置抹掉了：%+v", c2.LLM())
	}
	c2.LoadDataSource()
	if !c2.DataSource().Enabled || c2.DataSource().BaseURL != "https://api.example.com" {
		t.Fatalf("数据源配置未保留：%+v", c2.DataSource())
	}
}
