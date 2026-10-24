package datasource

import (
	"context"
	"errors"
	"strings"
	"testing"
)

// fakeResp 是测试用的 StatusCarrier 实现（ADR 0017; formerly roadmap 1-2-5 回退语义单测）。
type fakeResp struct {
	Fallback bool
	Status   Status
	Reason   string
	AsOf     string
	Source   string
}

func (r *fakeResp) SetFallbackMeta(fallback bool, status Status, reason, asOf string) {
	r.Fallback = fallback
	r.Status = status
	r.Reason = reason
	if r.AsOf == "" {
		r.AsOf = asOf
	}
}

type fakeSource struct {
	name string
	resp *fakeResp
	err  error
}

func (s fakeSource) Name() string { return s.name }

func (s fakeSource) Fetch(_ context.Context) (*fakeResp, error) {
	return s.resp, s.err
}

// TestFallbackStatusOK 首选源命中：新鲜数据，无回退，Status=ok。
func TestFallbackStatusOK(t *testing.T) {
	primary := fakeSource{name: "p", resp: &fakeResp{Source: "p"}}
	chain := NewFallbackChain[*fakeResp](primary)
	v, err := chain.Fetch(context.Background())
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if v.Status != StatusOK {
		t.Fatalf("status=%q want ok", v.Status)
	}
	if v.Fallback {
		t.Fatalf("fallback 应为 false（首选源命中）")
	}
}

// TestFallbackStatusUnconfigured 首选源未配置（ErrUnconfigured）→ 回退且 Status=unconfigured（良性，不报警）。
func TestFallbackStatusUnconfigured(t *testing.T) {
	primary := fakeSource{name: "p", err: ErrUnconfigured}
	secondary := fakeSource{name: "s", resp: &fakeResp{Source: "s"}}
	chain := NewFallbackChain[*fakeResp](primary, secondary)
	v, err := chain.Fetch(context.Background())
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if !v.Fallback {
		t.Fatalf("fallback 应为 true（走了回退）")
	}
	if v.Status != StatusUnconfigured {
		t.Fatalf("status=%q want unconfigured", v.Status)
	}
	if v.Reason == "" {
		t.Fatalf("unconfigured 也应给可读原因")
	}
}

// TestFallbackStatusSourceFailed 首选源已配置但失败 → 回退且 Status=source_failed（必须当错误处理）。
func TestFallbackStatusSourceFailed(t *testing.T) {
	primary := fakeSource{name: "p", err: errors.New("connection refused")}
	secondary := fakeSource{name: "s", resp: &fakeResp{Source: "s"}}
	chain := NewFallbackChain[*fakeResp](primary, secondary)
	v, err := chain.Fetch(context.Background())
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if v.Status != StatusSourceFailed {
		t.Fatalf("status=%q want source_failed", v.Status)
	}
	if !strings.Contains(v.Reason, "connection refused") {
		t.Fatalf("reason=%q 应含原始错误，便于前端告警", v.Reason)
	}
}

// TestFallbackAllFail 全失败链返回错误，不静默成功。
func TestFallbackAllFail(t *testing.T) {
	primary := fakeSource{name: "p", err: ErrUnconfigured}
	secondary := fakeSource{name: "s", err: errors.New("boom")}
	_, err := NewFallbackChain[*fakeResp](primary, secondary).Fetch(context.Background())
	if err == nil {
		t.Fatalf("全失败链应返回错误")
	}
	if !strings.Contains(err.Error(), "sources failed") {
		t.Fatalf("错误应含 sources failed，得到 %q", err.Error())
	}
}
