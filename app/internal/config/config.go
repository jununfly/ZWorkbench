package config

import (
	"crypto/rand"
	"encoding/hex"
	"os"
)

// Config 持有本地服务的端口、一次性鉴权 token、证据库路径。
type Config struct {
	Port  string
	Token string
	DB    string
}

// Load 从环境变量读取，缺失时给安全默认值（token 随机生成）。
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
	return &Config{Port: port, Token: token, DB: db}
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
