package config

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"os"
	"sync"
)

// Config 持有本地服务的端口、一次性鉴权 token、证据库路径，以及 LLM provider 配置。
type Config struct {
	Port  string
	Token string
	DB    string
	// EvidenceDB 是证据库（runs/events/effects…）路径；空串 = 内存库（重启即空）。
	// 见 roadmap 1-5-6-3 决策：默认不落盘，避免以 cwd 为基准污染工作目录；
	// 持久化默认路径需单独立项（data dir 决策），C26 的 durability 要求列为 follow-up。
	EvidenceDB string
	// WebDir 是前端 dist 目录（1-1-3）。空串表示交给 webstatic 自行按候选路径解析。
	WebDir string
	llm LLMConfig
	mu  sync.RWMutex
}

// LLMConfig 是「设置 / LLM」页可编辑的 provider 配置，持久化到 config.json。
// API key 明文存本地单用户桌面文件——记录为已知风险（1-5-4 D2）。
type LLMConfig struct {
	BaseURL string `json:"base_url"`
	APIKey  string `json:"api_key"`
	Model   string `json:"model"`
	Enabled bool   `json:"enabled"`
}

// Load 从环境变量读取服务配置，并从 config.json 读取 LLM 配置。
func Load() *Config {
	port := os.Getenv("ZW_PORT")
	if port == "" {
		port = "18080"
	}
	token := os.Getenv("ZW_TOKEN")
	if token == "" {
		token = randomToken()
	}
	db := os.Getenv("ZW_DB")
	if db == "" {
		db = "mem"
	}
	// ZW_EVIDENCE_DB 未设置 → 内存证据库；显式给路径才落 SQLite 文件。
	evidenceDB := os.Getenv("ZW_EVIDENCE_DB")
	// ZW_WEB_DIR（1-1-3）：打包后由 Electron 注入 resources 下的 web/dist；
	// 未设置时 webstatic 按候选路径自行解析。
	webDir := os.Getenv("ZW_WEB_DIR")
	c := &Config{Port: port, Token: token, DB: db, EvidenceDB: evidenceDB, WebDir: webDir}
	c.LoadLLM()
	return c
}

// LLM 返回当前 LLM 配置快照（并发安全）。
func (c *Config) LLM() LLMConfig {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.llm
}

// SetLLM 原子写入 LLM 配置（并发安全）。
func (c *Config) SetLLM(l LLMConfig) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.llm = l
}

// llmPath 返回 config.json 路径（env ZW_CONFIG 覆盖，默认 cwd ./config.json）。
func (c *Config) llmPath() string {
	p := os.Getenv("ZW_CONFIG")
	if p == "" {
		p = "config.json"
	}
	return p
}

// LoadLLM 从 config.json 读取 LLM 配置；文件缺失/损坏时静默忽略（视为未配置）。
func (c *Config) LoadLLM() {
	data, err := os.ReadFile(c.llmPath())
	if err != nil {
		return
	}
	var f struct {
		LLM LLMConfig `json:"llm"`
	}
	if err := json.Unmarshal(data, &f); err != nil {
		return
	}
	c.SetLLM(f.LLM)
}

// SaveLLM 将 LLM 配置写回 config.json（权限 0600）。
func (c *Config) SaveLLM() error {
	l := c.LLM()
	f := struct {
		LLM LLMConfig `json:"llm"`
	}{LLM: l}
	data, err := json.MarshalIndent(f, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(c.llmPath(), data, 0o600)
}

// Addr 绑定 loopback，避免暴露到外部网络。
func (c *Config) Addr() string {
	return "127.0.0.1:" + c.Port
}

func randomToken() string {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "dev-token"
	}
	return hex.EncodeToString(b)
}
