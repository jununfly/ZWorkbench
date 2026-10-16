package datasource

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

func TestDefaultConfigIsDisabled(t *testing.T) {
	c := DefaultConfig()
	if c.Enabled {
		t.Fatalf("默认必须关闭：未配置时不该打外网")
	}
	if c.Usable() {
		t.Fatalf("默认配置不可用")
	}
}

func TestConfigUsableRequiresBothEnabledAndBaseURL(t *testing.T) {
	cases := []struct {
		name string
		cfg  Config
		want bool
	}{
		{"关+无地址", Config{}, false},
		{"开+无地址", Config{Enabled: true}, false},
		{"关+有地址", Config{BaseURL: "https://x"}, false},
		{"开+有地址", Config{Enabled: true, BaseURL: "https://x"}, true},
		{"开+空白地址", Config{Enabled: true, BaseURL: "   "}, false},
	}
	for _, c := range cases {
		if got := c.cfg.Usable(); got != c.want {
			t.Errorf("%s: Usable()=%v, want %v", c.name, got, c.want)
		}
	}
}

func TestLoadFromEnvOverrides(t *testing.T) {
	t.Setenv("ZW_DATASOURCE_ENABLED", "true")
	t.Setenv("ZW_DATASOURCE_BASE_URL", "https://api.example.com")
	t.Setenv("ZW_DATASOURCE_TOKEN", "t-1")
	t.Setenv("ZW_DATASOURCE_TIMEOUT_SEC", "9")

	got := LoadFromEnv(DefaultConfig())
	if !got.Enabled {
		t.Errorf("env 未覆盖 enabled")
	}
	if got.BaseURL != "https://api.example.com" {
		t.Errorf("base_url=%q", got.BaseURL)
	}
	if got.Token != "t-1" {
		t.Errorf("token=%q", got.Token)
	}
	if got.TimeoutSec != 9 {
		t.Errorf("timeout_sec=%d, want 9", got.TimeoutSec)
	}
}

func TestLoadFromEnvEmptyDoesNotOverride(t *testing.T) {
	base := Config{Enabled: true, BaseURL: "https://keep", TimeoutSec: 7}
	got := LoadFromEnv(base)
	if got.BaseURL != "https://keep" || got.TimeoutSec != 7 || !got.Enabled {
		t.Fatalf("空 env 必须原样保留：%+v", got)
	}
}

func TestLoadFromEnvRejectsNonPositiveTimeout(t *testing.T) {
	t.Setenv("ZW_DATASOURCE_TIMEOUT_SEC", "0")
	got := LoadFromEnv(DefaultConfig())
	if got.TimeoutSec != defaultTimeoutSec {
		t.Fatalf("非法超时必须回退默认：got %d want %d", got.TimeoutSec, defaultTimeoutSec)
	}
}

func TestTimeoutFallsBackToDefault(t *testing.T) {
	empty := Config{}
	if got := empty.Timeout(); got != defaultTimeoutSec*time.Second {
		t.Fatalf("Timeout()=%v, want %v", got, defaultTimeoutSec*time.Second)
	}
	two := Config{TimeoutSec: 2}
	if got := two.Timeout(); got != 2*time.Second {
		t.Fatalf("Timeout()=%v, want 2s", got)
	}
}

func TestClassify(t *testing.T) {
	if got := Classify(nil); got != StatusOK {
		t.Errorf("nil → %v, want ok", got)
	}
	if got := Classify(ErrUnconfigured); got != StatusUnconfigured {
		t.Errorf("ErrUnconfigured → %v, want unconfigured", got)
	}
	wrapped := errors.New("timeout")
	if got := Classify(wrapped); got != StatusSourceFailed {
		t.Errorf("普通错误 → %v, want source_failed", got)
	}
	if got := Classify(errors.New("x: " + ErrUnconfigured.Error())); got != StatusSourceFailed {
		t.Errorf("文本相同但没包装 → %v, want source_failed（必须靠 errors.Is 判定）", got)
	}
}

func TestEndpoint(t *testing.T) {
	r := Remote{Name: "n", Path: "market/overview", Cfg: Config{Enabled: true, BaseURL: "https://api.example.com/"}}
	if got, want := r.Endpoint(), "https://api.example.com/market/overview"; got != want {
		t.Errorf("Endpoint()=%q, want %q", got, want)
	}
	withQ := r
	withQ.Query = url.Values{"code": []string{"600000"}}
	if got, want := withQ.Endpoint(), "https://api.example.com/market/overview?code=600000"; got != want {
		t.Errorf("带查询参数 Endpoint()=%q, want %q", got, want)
	}
	off := Remote{Cfg: DefaultConfig()}
	if got := off.Endpoint(); got != "" {
		t.Errorf("未配置时 Endpoint()=%q, want 空串", got)
	}
}

// countingTransport 记录是否真的发起了网络请求。
type countingTransport struct {
	calls int
	rt    http.RoundTripper
}

func (c *countingTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	c.calls++
	return c.rt.RoundTrip(r)
}

func TestFetchJSONUnconfiguredDoesNotHitNetwork(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{}`))
	}))
	defer srv.Close()

	ct := &countingTransport{rt: http.DefaultTransport}
	r := Remote{
		Name:   "remote-eastmoney",
		Path:   "/market/overview",
		Cfg:    Config{Enabled: true, BaseURL: srv.URL}, // 地址配了但开关关
		Client: &http.Client{Transport: ct},
	}
	r.Cfg.Enabled = false

	var dst map[string]any
	err := r.FetchJSON(context.Background(), &dst)
	if !errors.Is(err, ErrUnconfigured) {
		t.Fatalf("err=%v, want ErrUnconfigured", err)
	}
	if ct.calls != 0 {
		t.Fatalf("未配置却发起了 %d 次网络请求", ct.calls)
	}
	if got := Classify(err); got != StatusUnconfigured {
		t.Fatalf("Classify=%v, want unconfigured", got)
	}
}

func TestFetchJSONSuccess(t *testing.T) {
	var gotPath, gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		_, _ = w.Write([]byte(`{"name":"上证指数","value":3200.5}`))
	}))
	defer srv.Close()

	r := Remote{Name: "remote-eastmoney", Path: "/market/overview",
		Cfg: Config{Enabled: true, BaseURL: srv.URL, Token: "tok"}}

	var dst struct {
		Name  string  `json:"name"`
		Value float64 `json:"value"`
	}
	if err := r.FetchJSON(context.Background(), &dst); err != nil {
		t.Fatalf("FetchJSON: %v", err)
	}
	if dst.Name != "上证指数" || dst.Value != 3200.5 {
		t.Errorf("dst=%+v", dst)
	}
	if gotPath != "/market/overview" {
		t.Errorf("path=%q", gotPath)
	}
	if gotAuth != "Bearer tok" {
		t.Errorf("auth=%q, want Bearer tok", gotAuth)
	}
}

func TestFetchJSONNon2xxIsSourceFailed(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	r := Remote{Name: "n", Path: "/x", Cfg: Config{Enabled: true, BaseURL: srv.URL}}
	var dst map[string]any
	err := r.FetchJSON(context.Background(), &dst)
	if err == nil {
		t.Fatal("非 2xx 必须报错")
	}
	if got := Classify(err); got != StatusSourceFailed {
		t.Fatalf("Classify=%v, want source_failed（已配置就不能算未配置）", got)
	}
}

func TestFetchJSONDecodeError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`not-json`))
	}))
	defer srv.Close()

	r := Remote{Name: "n", Path: "/x", Cfg: Config{Enabled: true, BaseURL: srv.URL}}
	var dst map[string]any
	err := r.FetchJSON(context.Background(), &dst)
	if !errors.Is(err, ErrDecode) {
		t.Fatalf("err=%v, want ErrDecode", err)
	}
}

func TestFetchJSONTimeoutIsSourceFailed(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		time.Sleep(300 * time.Millisecond)
		_, _ = w.Write([]byte(`{}`))
	}))
	defer srv.Close()

	r := Remote{Name: "n", Path: "/x", Cfg: Config{Enabled: true, BaseURL: srv.URL, TimeoutSec: 1}}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()

	var dst map[string]any
	err := r.FetchJSON(ctx, &dst)
	if err == nil {
		t.Fatal("超时的上游必须报错")
	}
	if got := Classify(err); got != StatusSourceFailed {
		t.Fatalf("Classify=%v, want source_failed", got)
	}
}

func TestFetchJSONRejectsOversizedBody(t *testing.T) {
	// 单个 JSON 值本身超过 maxResponseBytes → 被 io.LimitReader 截断 → 解码必然失败。
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"pad":"` + strings.Repeat("x", maxResponseBytes) + `"}`))
	}))
	defer srv.Close()

	r := Remote{Name: "n", Path: "/x", Cfg: Config{Enabled: true, BaseURL: srv.URL}}
	var dst map[string]any
	err := r.FetchJSON(context.Background(), &dst)
	if err == nil {
		t.Fatal("超限响应体必须被截断并解码失败，而不是无限读进内存")
	}
	if !errors.Is(err, ErrDecode) {
		t.Fatalf("err=%v, want ErrDecode", err)
	}
}
