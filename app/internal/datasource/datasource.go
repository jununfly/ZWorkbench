// Package datasource 统一 7 个业务包（market/research/limitup/review/inspection/
// optimization/mastery）远程数据源的契约与配置开关（ADR 0017; formerly roadmap 1-2-1）。
//
// 在此之前，7 个包各自持有一个 RemoteStubSource，固定返回同一句
// "remote source not wired yet (stub)"，既没有统一的开关，也没有统一的失败语义，
// 导致 C36 回退永远被触发且无法区分「没配」和「配了但坏了」。
//
// 本包只承载与领域无关的部分：配置、开关、超时、鉴权、HTTP GET + JSON 解码、
// 失败分类。业务包只保留「源名 + 路径 + 查询参数 + 领域结构」，不再重复实现。
//
// 纯 stdlib，零外部依赖（符合 ADR 0015：Go 运行时零 cgo 依赖）。
package datasource

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"reflect"
	"strconv"
	"strings"
	"time"
)

// defaultTimeoutSec 是未显式配置时的默认超时。远程源超时必须回退到本地快照，
// 不能让一次慢请求把整个 tab 拖死。
const defaultTimeoutSec = 5

// maxResponseBytes 限制单响应体积，避免异常上游把进程内存打满。
const maxResponseBytes = 4 << 20

// Status 是远程源结果分类（ADR 0017; formerly roadmap 1-2-5 的语义收敛基础）。
// 关键不变量：未配置 ≠ 源失败 ≠ 陈旧快照，三者都不可以被当作成功，
// 也不可以被一律当作同一种失败报警。
type Status string

const (
	// StatusOK 远程源命中。
	StatusOK Status = "ok"
	// StatusUnconfigured 开关未开或 base_url 缺失。这是「没配」，不是故障，不该报警。
	StatusUnconfigured Status = "unconfigured"
	// StatusSourceFailed 已配置但请求失败（超时 / 非 2xx / 解码失败）。这是真故障。
	StatusSourceFailed Status = "source_failed"
	// StatusStaleSnapshot 命中本地种子快照（远程不可用）。1-2-5 接入：由调用方在
	// 回退链命中本地源时标注，本包自身不产生该状态。
	StatusStaleSnapshot Status = "stale_snapshot"
)

var (
	// ErrUnconfigured 远程源未启用。语义是「没配」而不是「配了坏了」。
	// 调用方（FallbackChain）应静默回退，不要把它当成上游故障。
	ErrUnconfigured = errors.New("data source not configured")
	// ErrDecode 已配置且拿到了响应，但响应体不是期望的 JSON 结构。
	ErrDecode = errors.New("data source response decode failed")
)

// Config 是「设置 / 数据源」页可编辑的远程源配置，持久化到 config.json 的
// data_source 段，并可由 ZW_DATASOURCE_* 环境变量覆盖。
type Config struct {
	BaseURL    string `json:"base_url"`
	Token      string `json:"token"`
	Enabled    bool   `json:"enabled"`
	TimeoutSec int    `json:"timeout_sec"`
}

// DefaultConfig 默认关闭（1-2-1 D2）：未配置时远程侧语义为「未配置」，
// 保证既有 C36 本地回退行为零回归——不接真源也永远是本地快照，不会突然打外网。
func DefaultConfig() Config {
	return Config{Enabled: false, TimeoutSec: defaultTimeoutSec}
}

// LoadFromEnv 用 ZW_DATASOURCE_* 覆盖给定配置。空串表示不覆盖（沿用 config.json）。
// ZW_DATASOURCE_ENABLED 接受 1/true/TRUE/yes/on。
func LoadFromEnv(base Config) Config {
	if v := strings.TrimSpace(os.Getenv("ZW_DATASOURCE_ENABLED")); v != "" {
		base.Enabled = strings.EqualFold(v, "1") || strings.EqualFold(v, "true") ||
			strings.EqualFold(v, "yes") || strings.EqualFold(v, "on")
	}
	if v := strings.TrimSpace(os.Getenv("ZW_DATASOURCE_BASE_URL")); v != "" {
		base.BaseURL = v
	}
	if v := strings.TrimSpace(os.Getenv("ZW_DATASOURCE_TOKEN")); v != "" {
		base.Token = v
	}
	if v := strings.TrimSpace(os.Getenv("ZW_DATASOURCE_TIMEOUT_SEC")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			base.TimeoutSec = n
		}
	}
	if base.TimeoutSec <= 0 {
		base.TimeoutSec = defaultTimeoutSec
	}
	return base
}

// Usable 判定远程源是否真的可用：开关开 **且** base_url 非空。
// 只开开关不配地址仍然是「未配置」，不能因为 Enabled=true 就去打一个空 URL。
func (c Config) Usable() bool {
	return c.Enabled && strings.TrimSpace(c.BaseURL) != ""
}

// Timeout 返回超时时长（非法值回退默认）。
func (c Config) Timeout() time.Duration {
	if c.TimeoutSec <= 0 {
		return defaultTimeoutSec * time.Second
	}
	return time.Duration(c.TimeoutSec) * time.Second
}

// Classify 把远程源的错误归到 Status。nil 表示远程命中（StatusOK）。
// 除 ErrUnconfigured 外的一切错误（超时、非 2xx、解码失败、连接拒绝）
// 一律是 StatusSourceFailed——已配置就该为失败负责。
func Classify(err error) Status {
	switch {
	case err == nil:
		return StatusOK
	case errors.Is(err, ErrUnconfigured):
		return StatusUnconfigured
	default:
		return StatusSourceFailed
	}
}

// Remote 是统一远程源契约的载体：7 个业务包各持有一个，补充「源名 + 路径 +
// 查询参数」后共用同一套开关/超时/鉴权/失败分类语义。
type Remote struct {
	// Name 是证据字段，命中时写入领域结构的 Source（如 "remote-eastmoney"）。
	Name string
	// Path 是相对 BaseURL 的路径（如 "/market/overview"）。
	Path string
	// Query 是可选查询参数（个股研究等按 code 取数的场景）。
	Query url.Values
	// Cfg 是统一的远程源配置。
	Cfg Config
	// Client 可选 HTTP 客户端；nil 时用 http.DefaultClient（测试注入用）。
	Client *http.Client
}

// Endpoint 返回完整 URL；未配置时返回空串。仅用于开关自检与日志，不发起请求。
func (r Remote) Endpoint() string {
	if !r.Cfg.Usable() {
		return ""
	}
	u := strings.TrimRight(strings.TrimSpace(r.Cfg.BaseURL), "/") + normalizePath(r.Path)
	if len(r.Query) > 0 {
		u += "?" + r.Query.Encode()
	}
	return u
}

// FetchJSON 执行一次带超时的 GET，并把响应体解码进 dst。
//
// 失败语义：
//   - 未配置（开关关 / base_url 空）→ ErrUnconfigured，**不发起任何网络请求**；
//   - 非 2xx / 传输失败 / 超时 → 包装后返回（Classify → StatusSourceFailed）；
//   - 2xx 但结构不匹配 → ErrDecode（Classify → StatusSourceFailed）。
func (r Remote) FetchJSON(ctx context.Context, dst any) error {
	if !r.Cfg.Usable() {
		return fmt.Errorf("%w: %s", ErrUnconfigured, r.Name)
	}
	ctx, cancel := context.WithTimeout(ctx, r.Cfg.Timeout())
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, r.Endpoint(), nil)
	if err != nil {
		return fmt.Errorf("build request for %s: %w", r.Name, err)
	}
	req.Header.Set("Accept", "application/json")
	if tok := strings.TrimSpace(r.Cfg.Token); tok != "" {
		req.Header.Set("Authorization", "Bearer "+tok)
	}

	client := r.Client
	if client == nil {
		client = http.DefaultClient
	}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("%s request failed: %w", r.Name, err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		return fmt.Errorf("%s returned status %d", r.Name, resp.StatusCode)
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, maxResponseBytes)).Decode(dst); err != nil {
		return fmt.Errorf("%w: %s: %v", ErrDecode, r.Name, err)
	}
	return nil
}

// normalizePath 保证路径以 "/" 开头；空路径视为根。
func normalizePath(p string) string {
	p = strings.TrimSpace(p)
	if p == "" {
		return "/"
	}
	if !strings.HasPrefix(p, "/") {
		return "/" + p
	}
	return p
}

// StatusCarrier 让回退链在命中结果上写入语义状态（ADR 0017; formerly roadmap 1-2-5）。
// 各业务包的响应结构（MarketOverview/StockResearch/...）都实现它，
// 使 7 个包的回退语义收敛到同一套字段与同一套分类逻辑。
type StatusCarrier interface {
	// SetFallbackMeta 写入回退标记与语义状态。
	//   - fallback=true 表示命中的不是首选源（数据可能陈旧，见 StatusStaleSnapshot）；
	//   - status 取 Status 四值枚举；reason 仅在非 ok 时给出人类可读原因；
	//   - asOf 为结果时间戳（RFC3339），空时由调用方补。
	SetFallbackMeta(fallback bool, status Status, reason, asOf string)
}

// Source 是统一「多源回退」的契约（ADR 0017; formerly roadmap 1-2-5 收敛点）。
// T 是领域响应指针类型（如 *MarketOverview），必须实现 StatusCarrier 以便回退链写入语义状态。
// 7 个业务包的 RemoteSource/LocalSnapshotSource/ImportedFileSource 都结构性满足它。
type Source[T StatusCarrier] interface {
	Name() string
	Fetch(ctx context.Context) (T, error)
}

// FallbackChain 按序尝试源，返回首个成功；非首选源命中即标注 fallback（C36 回退语义）。
// 同时把回退的「为什么」写入响应的 Status/Reason，区分未配置 / 源失败 / 陈旧快照（1-2-5）。
// 这是 7 包回退循环的唯一真相源：任何语义改动只在此一处，不再各包各写一遍。
type FallbackChain[T StatusCarrier] struct{ sources []Source[T] }

// NewFallbackChain 构造回退链（顺序即优先级）。
func NewFallbackChain[T StatusCarrier](sources ...Source[T]) *FallbackChain[T] {
	return &FallbackChain[T]{sources: sources}
}

// Fetch 尝试所有源，返回第一个成功结果；同时标注是否走了回退与回退的语义原因。
func (c *FallbackChain[T]) Fetch(ctx context.Context) (T, error) {
	var primaryErr error
	var zero T
	for i, s := range c.sources {
		v, err := s.Fetch(ctx)
		if err == nil && !isNil(v) {
			asOf := time.Now().Format(time.RFC3339)
			if i == 0 {
				// 首选源命中：新鲜数据，无回退。
				v.SetFallbackMeta(false, StatusOK, "", asOf)
			} else {
				// 非首选源命中：用【首选源】的错误分类回退原因，
				// 避免把次要源的错误误归因到主状态。
				st, reason := ClassifyFallback(primaryErr)
				v.SetFallbackMeta(true, st, reason, asOf)
			}
			return v, nil
		}
		if i == 0 {
			primaryErr = err
		}
	}
	if primaryErr == nil {
		primaryErr = fmt.Errorf("no sources configured")
	}
	return zero, fmt.Errorf("all %d sources failed: %v", len(c.sources), primaryErr)
}

// isNil 判断任意可空值是否为 nil（T 是类型参数，不能用 v != nil 直接比较）。
// 仅对指针/接口/切片/映射/通道/函数做 IsNil，其他类型一律视为非空。
func isNil(v any) bool {
	if v == nil {
		return true
	}
	rv := reflect.ValueOf(v)
	switch rv.Kind() {
	case reflect.Ptr, reflect.Interface, reflect.Slice, reflect.Map, reflect.Chan, reflect.Func:
		return rv.IsNil()
	}
	return false
}

// ClassifyFallback 把首选源的错误分类为回退状态与原因（1-2-5）。
// nil 表示首选源命中（调用方不应传入）；ErrUnconfigured → 未配置（良性，不报警）；
// 其余一律 → 源失败（已配置就该为失败负责，前端必须当错误处理，不得伪装成成功）。
func ClassifyFallback(primaryErr error) (Status, string) {
	if primaryErr == nil {
		return StatusOK, ""
	}
	if errors.Is(primaryErr, ErrUnconfigured) {
		return StatusUnconfigured, "实时数据源未配置，已回退本地快照"
	}
	return StatusSourceFailed, primaryErr.Error()
}
