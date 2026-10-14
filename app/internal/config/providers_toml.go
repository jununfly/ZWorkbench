package config

import (
	"os"
	"strings"
)

// ParseProvidersToml 读取 Codex 风格的 provider 配置文件（zw-providers.toml 同构），
// 抽取当前激活的 model_provider 并映射为 LLMConfig。
//
// 手写最小 TOML 解析（仅覆盖该 schema），不引入第三方库——保持 ADR 0015 零外部依赖。
// 映射规则：
//   - base_url 经 normalizeArkBaseURL 归一到 Ark 标准 OpenAI 兼容 chat 端点（/api/v3）
//   - experimental_bearer_token（或 api_key）→ APIKey（Ark 用 Authorization: Bearer）
//   - 顶层 model / model_provider → Model
//   - 解析成功即视为已启用
func ParseProvidersToml(path string) (LLMConfig, bool) {
	tables, err := parseTomlTables(path)
	if err != nil {
		return LLMConfig{}, false
	}
	top := tables[""]
	mp := top["model_provider"]
	if mp == "" {
		mp = top["model"]
	}
	if mp == "" {
		return LLMConfig{}, false
	}
	sect, ok := tables["model_providers."+mp]
	if !ok {
		return LLMConfig{}, false
	}
	base := normalizeArkBaseURL(sect["base_url"])
	key := sect["experimental_bearer_token"]
	if key == "" {
		key = sect["api_key"]
	}
	model := top["model"]
	if model == "" {
		model = mp
	}
	if base == "" || key == "" {
		return LLMConfig{}, false
	}
	return LLMConfig{
		BaseURL: base,
		APIKey:  key,
		Model:   model,
		Enabled: true,
	}, true
}

// parseTomlTables 返回 section(可能是 "" 顶层) → key → value 的映射。
// 支持 [a.b.c] 嵌套表头与 # 注释；值仅做去引号处理，不解析类型。
func parseTomlTables(path string) (map[string]map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	tables := map[string]map[string]string{}
	cur := ""
	tables[cur] = map[string]string{}
	for _, raw := range strings.Split(string(data), "\n") {
		line := strings.TrimSpace(stripInlineComment(raw))
		if line == "" {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section := strings.TrimSpace(line[1 : len(line)-1])
			cur = section
			if _, ok := tables[cur]; !ok {
				tables[cur] = map[string]string{}
			}
			continue
		}
		eq := strings.Index(line, "=")
		if eq < 0 {
			continue
		}
		k := strings.TrimSpace(line[:eq])
		v := unquoteVal(strings.TrimSpace(line[eq+1:]))
		tables[cur][k] = v
	}
	return tables, nil
}

// stripInlineComment 去掉不在字符串内的 # 注释。
func stripInlineComment(s string) string {
	inStr := false
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c == '"' {
			inStr = !inStr
		} else if c == '#' && !inStr {
			return strings.TrimRight(s[:i], " \t")
		}
	}
	return s
}

// unquoteVal 去基础字符串引号并处理 \" 与 \\ 转义。
func unquoteVal(s string) string {
	if len(s) >= 2 && s[0] == '"' && s[len(s)-1] == '"' {
		inner := s[1 : len(s)-1]
		inner = strings.ReplaceAll(inner, `\"`, `"`)
		inner = strings.ReplaceAll(inner, `\\`, `\`)
		return inner
	}
	return s
}

// normalizeArkBaseURL 将 Ark 的 Codex coding 端点（/api/coding/v3，走 Responses API）
// 归一到标准 OpenAI 兼容 Chat Completions 端点（/api/v3）。其他 base_url 原样返回。
func normalizeArkBaseURL(raw string) string {
	raw = strings.TrimRight(raw, "/")
	if strings.HasSuffix(raw, "/api/coding/v3") {
		return strings.TrimSuffix(raw, "/api/coding/v3") + "/api/v3"
	}
	if i := strings.Index(raw, "/api/coding/v3/"); i >= 0 {
		return strings.Replace(raw, "/api/coding/v3/", "/api/v3/", 1)
	}
	return raw
}
