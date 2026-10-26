package config

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/datasource"
)

// DataSourceConfig 是「设置 / 数据源」页可编辑的远程源配置（ADR 0017; formerly roadmap 1-2-1）。
// 类型别名：配置形态由 datasource 包定义，config 只负责持久化与 env 覆盖。
type DataSourceConfig = datasource.Config

// DataFiles 是「本地可导入数据集」的文件路径段（ADR 0017; formerly roadmap 1-2-3 D9 / 1-2-4 D13）。
// 与 DataSource（远程源）分开：一个是网络端点，一个是本地文件，失败语义不同。
type DataFiles struct {
	// MasteryPath 是游资心法库导入文件路径；空串表示未导入（回退内嵌快照）。
	MasteryPath string `json:"mastery_path"`
	// PortfolioPath 是持仓导入文件路径（真实持仓输入，1-2-4 D11/D12）；
	// 空串表示未导入（inspection/optimization 回退内嵌快照）。
	PortfolioPath string `json:"portfolio_path"`
}

// RepoSpec 是被管理仓库（ADR 0019; 编码证据上下文维度）。
// 一个 ZW 实例可登记多个被管理仓库，新建证据 run 时选择其一作为语境。
type RepoSpec struct {
	// Name 是仓库在 UI/API 中的展示名（如 "ZWorkbench"），全局唯一。
	Name string `json:"name"`
	// Path 是仓库本地路径；空串表示未知（current_branch 回退 unknown）。
	Path string `json:"path"`
	// Environments 是该仓库可选的执行环境枚举；至少含 "local"。
	Environments []string `json:"environments"`
}

// ManagedRepos 是被管理仓库列表的持久化形态（ADR 0019）。
type ManagedRepos struct {
	Repos []RepoSpec `json:"repos"`
}

// NormalizedEnvironments 返回该仓库规范化后的环境枚举：去空白、去空串、保序去重；
// 为空时回退 ["local"]（与 /api/context 的补默认口径一致）。
// 供「环境白名单」校验与 /api/context 输出共用，避免两处各自实现导致口径漂移。
func (r RepoSpec) NormalizedEnvironments() []string {
	out := make([]string, 0, len(r.Environments))
	seen := make(map[string]struct{}, len(r.Environments))
	for _, e := range r.Environments {
		e = strings.TrimSpace(e)
		if e == "" {
			continue
		}
		if _, dup := seen[e]; dup {
			continue
		}
		seen[e] = struct{}{}
		out = append(out, e)
	}
	if len(out) == 0 {
		return []string{"local"}
	}
	return out
}

// AllowsEnvironment 判断给定环境是否落在该仓库的白名单内。
// 空环境名视为「未声明环境」，一律不允许——由调用方决定「未声明」是否跳过校验，
// 本方法只回答白名单本身（不做默认放行，保持 fail-closed）。
func (r RepoSpec) AllowsEnvironment(env string) bool {
	env = strings.TrimSpace(env)
	if env == "" {
		return false
	}
	for _, e := range r.NormalizedEnvironments() {
		if e == env {
			return true
		}
	}
	return false
}

// FindRepo 按展示名精确查找被管理仓库；找不到返回 false。
func (m ManagedRepos) FindRepo(name string) (RepoSpec, bool) {
	name = strings.TrimSpace(name)
	if name == "" {
		return RepoSpec{}, false
	}
	for _, r := range m.Repos {
		if strings.TrimSpace(r.Name) == name {
			return r, true
		}
	}
	return RepoSpec{}, false
}

// 执行档位相关常量（ADR 0020 首刀）。
const (
	// DefaultExecutionTimeout 是档位未声明 timeout_sec 时的执行上限。
	// 与 Python CLI 的 run 默认 300s 对齐，避免两处对「一次执行能跑多久」口径不一。
	DefaultExecutionTimeout = 300 * time.Second
	// MaxExecutionTimeout 是档位 timeout_sec 的硬上限：再长会让 HTTP 侧与
	// 证据回看都失去意义，也容易掩盖挂死。
	MaxExecutionTimeout = 3600 * time.Second
)

// shellMetaChars 是命令里一律禁止出现的字符。
//
// 理由：执行器用 os/exec 直接 exec 目标程序、**从不经过 shell**，所以这些字符
// 不会带来注入；但让一个写着 `go; rm -rf` 的档位通过校验，等于让配置读起来
// 像 shell 而实际行为不同 —— 这种「读起来和跑起来不一样」是整个 epic 最该
// 避免的歧义，因此一律在配置层拒绝，而不是留给运行时解释。
const shellMetaChars = ";|&$`><()\\'\"\n\r\t"

// ExecutionProfile 是预置执行档位（ADR 0020）：一次执行请求只能引用档位名，
// 不能携带任意 argv。这是本 epic 的安全边界 —— HTTP 面永远拿不到「跑任意命令」
// 的能力，只能从配置白名单里挑一个。
type ExecutionProfile struct {
	// Name 是档位在 UI/API 中的引用键，全局唯一。
	Name string `json:"name"`
	// Command 是固定可执行文件：裸名走 PATH（LookPath），或绝对路径。
	Command string `json:"command"`
	// Args 是固定参数，按原样传给程序，不经过 shell 解析。
	Args []string `json:"args"`
	// Environments 是该档位允许执行的环境；首刀只接受 local。
	// 声明 container/remote 会被 Validate 拒绝 —— 不静默声称支持尚未实现的能力。
	Environments []string `json:"environments"`
	// TimeoutSec 是单次执行超时秒数；<=0 走 DefaultExecutionTimeout。
	TimeoutSec int `json:"timeout_sec"`
	// Workdir 是相对被管理仓库 Path 的工作目录；空 = 仓库根，绝对路径 = 原样。
	Workdir string `json:"workdir"`
}

// Validate 校验档位自洽性。fail-closed：任何「看起来能跑但跑不起来」的配置
// 都在这里当场拒绝，不留给运行时。
func (p ExecutionProfile) Validate() error {
	name := strings.TrimSpace(p.Name)
	if name == "" {
		return fmt.Errorf("execution profile: name 不能为空")
	}
	cmd := strings.TrimSpace(p.Command)
	if cmd == "" {
		return fmt.Errorf("execution profile %q: command 不能为空", name)
	}
	if strings.ContainsAny(cmd, " \t\n\r") {
		return fmt.Errorf("execution profile %q: command 不能包含空白（参数请放进 args）", name)
	}
	if strings.ContainsAny(cmd, shellMetaChars) {
		return fmt.Errorf("execution profile %q: command 不能包含 shell 元字符 %q", name, cmd)
	}
	for i, a := range p.Args {
		if strings.ContainsAny(a, "\n\r") {
			return fmt.Errorf("execution profile %q: args[%d] 不能包含换行", name, i)
		}
	}
	if p.TimeoutSec < 0 {
		return fmt.Errorf("execution profile %q: timeout_sec 不能为负（0 表示用默认 %v）", name, DefaultExecutionTimeout)
	}
	if time.Duration(p.TimeoutSec)*time.Second > MaxExecutionTimeout {
		return fmt.Errorf("execution profile %q: timeout_sec 不能超过 %v", name, MaxExecutionTimeout)
	}
	for _, env := range p.Environments {
		e := strings.TrimSpace(env)
		if e == "" {
			continue
		}
		if e != "local" {
			return fmt.Errorf("execution profile %q: environment %q 未实现（ADR 0020 首刀只支持 local；container/remote 见后续切片）", name, e)
		}
	}
	return nil
}

// EffectiveTimeout 返回实际执行上限：未声明用默认值。
func (p ExecutionProfile) EffectiveTimeout() time.Duration {
	if p.TimeoutSec <= 0 {
		return DefaultExecutionTimeout
	}
	d := time.Duration(p.TimeoutSec) * time.Second
	if d > MaxExecutionTimeout {
		return MaxExecutionTimeout
	}
	return d
}

// AllowsEnvironment 判断该档位是否允许在给定环境执行。
// 未声明则回退「只允许 local」，与首刀只有本地执行器的事实一致（fail-closed）。
func (p ExecutionProfile) AllowsEnvironment(env string) bool {
	env = strings.TrimSpace(env)
	if env == "" {
		return false
	}
	allowed := make(map[string]struct{}, len(p.Environments))
	for _, e := range p.Environments {
		if e = strings.TrimSpace(e); e != "" {
			allowed[e] = struct{}{}
		}
	}
	if len(allowed) == 0 {
		return env == "local"
	}
	_, ok := allowed[env]
	return ok
}

// ResolveDir 解析执行工作目录：空 Workdir → 仓库路径；相对 → 拼到仓库路径；
// 绝对 → 原样。仓库路径也为空时返回空串，由执行层决定是否拒绝。
func (p ExecutionProfile) ResolveDir(repoPath string) string {
	repoPath = strings.TrimSpace(repoPath)
	wd := strings.TrimSpace(p.Workdir)
	switch {
	case wd == "":
		return repoPath
	case filepath.IsAbs(wd):
		return wd
	case repoPath == "":
		return ""
	default:
		return filepath.Join(repoPath, wd)
	}
}

// ExecutionProfiles 是执行档位列表的持久化形态（ADR 0020）。
type ExecutionProfiles struct {
	Profiles []ExecutionProfile `json:"profiles"`
}

// Validate 校验整张列表：逐个自洽 + 名字不重复（Name 是执行请求的唯一引用键，
// 重名会让「跑哪个」变成未定义行为）。
func (m ExecutionProfiles) Validate() error {
	seen := make(map[string]struct{}, len(m.Profiles))
	for _, p := range m.Profiles {
		if err := p.Validate(); err != nil {
			return err
		}
		name := strings.TrimSpace(p.Name)
		if _, dup := seen[name]; dup {
			return fmt.Errorf("execution profile %q: 名字重复（必须全局唯一）", name)
		}
		seen[name] = struct{}{}
	}
	return nil
}

// FindProfile 按名字精确查找档位（容忍首尾空白）；找不到返回 false。
func (m ExecutionProfiles) FindProfile(name string) (ExecutionProfile, bool) {
	name = strings.TrimSpace(name)
	if name == "" {
		return ExecutionProfile{}, false
	}
	for _, p := range m.Profiles {
		if strings.TrimSpace(p.Name) == name {
			return p, true
		}
	}
	return ExecutionProfile{}, false
}

// Config 持有本地服务的端口、一次性鉴权 token、证据库路径、LLM provider 配置、
// 统一远程数据源开关，以及本地导入数据集路径。
type Config struct {
	Port  string
	Token string
	DB    string
	// EvidenceDB 是证据库（runs/events/effects…）路径；空串 = 内存库（重启即空）。
	// 见 ADR 0016 (formerly roadmap 1-5-6-3) 决策：默认不落盘，避免以 cwd 为基准污染工作目录；
	// 持久化默认路径需单独立项（data dir 决策），C26 的 durability 要求列为 follow-up。
	EvidenceDB string
	// WebDir 是前端 dist 目录（1-1-3）。空串表示交给 webstatic 自行按候选路径解析。
	WebDir string
	llm    LLMConfig
	ds     DataSourceConfig
	df     DataFiles
	mr     ManagedRepos
	ep     ExecutionProfiles
	mu     sync.RWMutex
}

// persistFile 是 config.json 的完整形态。各段落共用一次保存，
// 避免「存 LLM 把数据源配置抹掉」这类静默丢配置。
type persistFile struct {
	LLM               LLMConfig         `json:"llm"`
	DataSource        DataSourceConfig  `json:"data_source"`
	DataFiles         DataFiles         `json:"data_files"`
	ManagedRepos      ManagedRepos      `json:"managed_repos"`
	ExecutionProfiles ExecutionProfiles `json:"execution_profiles"`
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
	c := &Config{
		Port: port, Token: token, DB: db, EvidenceDB: evidenceDB, WebDir: webDir,
		ds: datasource.DefaultConfig(),
	}
	c.load()
	return c
}

// ManagedRepos 返回被管理仓库列表快照（并发安全，ADR 0019）。
func (c *Config) ManagedRepos() ManagedRepos {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.mr
}

// SetManagedRepos 原子写入被管理仓库列表（并发安全，ADR 0019）。
func (c *Config) SetManagedRepos(m ManagedRepos) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.mr = m
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

// DataSource 返回当前远程数据源配置快照（并发安全）。
// 顺序：内置默认（关闭）→ config.json → ZW_DATASOURCE_* env 覆盖。
func (c *Config) DataSource() DataSourceConfig {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.ds
}

// SetDataSource 原子写入远程数据源配置（并发安全）。
func (c *Config) SetDataSource(d DataSourceConfig) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.ds = d
}

// DataFiles 返回当前本地导入数据集路径快照（并发安全）。
// 顺序：空 → config.json 的 data_files 段 → ZW_MASTERY_PATH env 覆盖。
func (c *Config) DataFiles() DataFiles {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.df
}

// MasteryPath 返回游资心法导入文件路径（便捷读取）。
func (c *Config) MasteryPath() string { return strings.TrimSpace(c.DataFiles().MasteryPath) }

// PortfolioPath 返回持仓导入文件路径（便捷读取，1-2-4 D13）。
func (c *Config) PortfolioPath() string { return strings.TrimSpace(c.DataFiles().PortfolioPath) }

// SetDataFiles 原子写入本地导入数据集路径（并发安全）。
func (c *Config) SetDataFiles(d DataFiles) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.df = d
}

// ExecutionProfiles 返回预置执行档位快照（并发安全，ADR 0020）。
func (c *Config) ExecutionProfiles() ExecutionProfiles {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.ep
}

// SetExecutionProfiles 原子写入预置执行档位（并发安全）。
func (c *Config) SetExecutionProfiles(e ExecutionProfiles) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.ep = e
}

// SaveExecutionProfiles 将预置执行档位写回 config.json（权限 0600，ADR 0020）。
func (c *Config) SaveExecutionProfiles() error { return c.save() }

// llmPath 返回 config.json 路径（env ZW_CONFIG 覆盖，默认 cwd ./config.json）。
func (c *Config) llmPath() string {
	p := os.Getenv("ZW_CONFIG")
	if p == "" {
		p = "config.json"
	}
	return p
}

// load 从 config.json 读取全部可持久化段落（LLM + 数据源）；
// 文件缺失/损坏时静默忽略（视为未配置，沿用默认值）。
// env 覆盖只在最后生效一次，保证「env > 文件 > 默认」。
func (c *Config) load() {
	// 三个段落一起读，任一环节缺失都只影响该段（不影响其它段落的默认值）。
	data, err := os.ReadFile(c.llmPath())
	if err != nil {
		c.SetDataSource(datasource.LoadFromEnv(c.DataSource()))
		c.SetDataFiles(loadDataFilesFromEnv(c.DataFiles()))
		// 即使无 config.json，env 覆盖仍应生效（与数据源/导入路径一致）。
		c.SetManagedRepos(loadManagedReposFromEnv(c.ManagedRepos()))
		c.SetExecutionProfiles(loadExecutionProfilesFromEnv(c.ExecutionProfiles()))
		return
	}
	var f persistFile
	if err := json.Unmarshal(data, &f); err != nil {
		c.SetDataSource(datasource.LoadFromEnv(c.DataSource()))
		c.SetDataFiles(loadDataFilesFromEnv(c.DataFiles()))
		return
	}
	c.SetLLM(f.LLM)
	ds := f.DataSource
	if ds.TimeoutSec <= 0 {
		ds.TimeoutSec = datasource.DefaultConfig().TimeoutSec
	}
	c.SetDataSource(datasource.LoadFromEnv(ds))
	c.SetDataFiles(loadDataFilesFromEnv(f.DataFiles))
	c.SetManagedRepos(loadManagedReposFromEnv(f.ManagedRepos))
	c.SetExecutionProfiles(loadExecutionProfilesFromEnv(f.ExecutionProfiles))
}

// loadDataFilesFromEnv 用 ZW_MASTERY_PATH / ZW_PORTFOLIO_PATH 覆盖给定的导入路径：
// env 优先于 config.json，与数据源配置的覆盖顺序保持一致。
func loadDataFilesFromEnv(base DataFiles) DataFiles {
	if v := strings.TrimSpace(os.Getenv("ZW_MASTERY_PATH")); v != "" {
		base.MasteryPath = v
	}
	if v := strings.TrimSpace(os.Getenv("ZW_PORTFOLIO_PATH")); v != "" {
		base.PortfolioPath = v
	}
	return base
}

// loadManagedReposFromEnv 用 ZW_MANAGED_REPOS（JSON 数组）覆盖被管理仓库列表：
// env 优先于 config.json（ADR 0019）。非法 JSON 静默忽略，沿用文件/默认值。
func loadManagedReposFromEnv(base ManagedRepos) ManagedRepos {
	v := strings.TrimSpace(os.Getenv("ZW_MANAGED_REPOS"))
	if v == "" {
		return base
	}
	var repos []RepoSpec
	if err := json.Unmarshal([]byte(v), &repos); err != nil {
		return base
	}
	return ManagedRepos{Repos: repos}
}

// loadExecutionProfilesFromEnv 用 ZW_EXEC_PROFILES（JSON 数组）覆盖执行档位列表：
// env 优先于 config.json（与 ZW_MANAGED_REPOS 同序）。非法 JSON 静默忽略。
func loadExecutionProfilesFromEnv(base ExecutionProfiles) ExecutionProfiles {
	v := strings.TrimSpace(os.Getenv("ZW_EXEC_PROFILES"))
	if v == "" {
		return base
	}
	var profiles []ExecutionProfile
	if err := json.Unmarshal([]byte(v), &profiles); err != nil {
		return base
	}
	return ExecutionProfiles{Profiles: profiles}
}

// LoadLLM 从 config.json 读取 LLM 配置（兼容入口，内部读取完整文件）。
func (c *Config) LoadLLM() { c.load() }

// LoadDataSource 从 config.json 读取数据源配置（env 覆盖仍生效）。
func (c *Config) LoadDataSource() { c.load() }

// save 把各段配置一起写回 config.json（权限 0600）。
// 必须整体写：分开写会让「保存 LLM」把数据源开关抹掉，属于静默丢配置。
func (c *Config) save() error {
	f := persistFile{
		LLM:               c.LLM(),
		DataSource:        c.DataSource(),
		DataFiles:         c.DataFiles(),
		ManagedRepos:      c.ManagedRepos(),
		ExecutionProfiles: c.ExecutionProfiles(),
	}
	data, err := json.MarshalIndent(f, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(c.llmPath(), data, 0o600)
}

// SaveLLM 将 LLM 配置写回 config.json（权限 0600）。
func (c *Config) SaveLLM() error { return c.save() }

// SaveDataSource 将数据源配置写回 config.json（权限 0600）。
func (c *Config) SaveDataSource() error { return c.save() }

// SaveManagedRepos 将被管理仓库列表写回 config.json（权限 0600，ADR 0019）。
func (c *Config) SaveManagedRepos() error { return c.save() }

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
