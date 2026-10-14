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
	llm            LLMConfig
	providerConfig string // 启动注入的外部 provider TOML 路径（ZW_PROVIDER_CONFIG）
	mu             sync.RWMutex
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
	c := &Config{Port: port, Token: token, DB: db}
	c.LoadLLM()
	// 复用外部 provider 配置（如 zw-providers.toml）：若 ZW_PROVIDER_CONFIG 指向可读文件，
	// 启动即合并进 LLM 配置（覆盖 config.json 中的 llm）。运行时 PUT /api/config 仍可覆盖。
	if pc := os.Getenv("ZW_PROVIDER_CONFIG"); pc != "" {
		if llm, ok := ParseProvidersToml(pc); ok {
			c.SetLLM(llm)
			c.providerConfig = pc
		}
	}
	return c
}

// ProviderConfig 返回启动时所用的 provider TOML 路径（空表示未用外部文件）。
func (c *Config) ProviderConfig() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.providerConfig
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
