package envprobe

import (
	"context"
	"errors"
	"net"
	"testing"
	"time"
)

func TestKind(t *testing.T) {
	cases := []struct{ in, want string }{
		{"local", KindLocal},
		{"LOCAL", KindLocal},
		{" local ", KindLocal},
		{"container", KindContainer},
		{"docker", KindContainer},
		{"container:golang:1.26", KindContainer},
		{"remote", KindRemote},
		{"remote:tcp://127.0.0.1:22", KindRemote},
		{"staging", KindUnknown},
		{"", KindUnknown},
	}
	for _, c := range cases {
		if got := Kind(c.in); got != c.want {
			t.Errorf("Kind(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestProbeLocalAlwaysAvailable(t *testing.T) {
	st := Probe("local")
	if !st.Available {
		t.Fatalf("local 应恒可用，实际 %#v", st)
	}
	if st.Kind != KindLocal {
		t.Fatalf("Kind 应为 local，实际 %q", st.Kind)
	}
}

func TestProbeUnknownKindNotAvailable(t *testing.T) {
	st := Probe("staging")
	if st.Available {
		t.Fatalf("未知种类不应可用，实际 %#v", st)
	}
	if st.Kind != KindUnknown {
		t.Fatalf("Kind 应为 unknown，实际 %q", st.Kind)
	}
	if st.Reason == "" {
		t.Fatal("不可用必须带可读 reason")
	}
}

func TestProbeContainerNoDockerCLI(t *testing.T) {
	orig := lookPath
	defer func() { lookPath = orig }()
	lookPath = func(string) (string, error) { return "", errors.New("not found") }

	st := Probe("container")
	if st.Available {
		t.Fatalf("无 docker CLI 不应可用，实际 %#v", st)
	}
	if st.Reason != "未找到 docker CLI" {
		t.Fatalf("reason 不符：%q", st.Reason)
	}
}

func TestProbeContainerDaemonDown(t *testing.T) {
	origLook, origRun := lookPath, runCommand
	defer func() { lookPath, runCommand = origLook, origRun }()
	lookPath = func(string) (string, error) { return "/usr/local/bin/docker", nil }
	runCommand = func(context.Context, string, ...string) ([]byte, error) {
		return nil, errors.New("Cannot connect to the Docker daemon")
	}

	st := Probe("container")
	if st.Available {
		t.Fatalf("daemon 不可用时不应可用，实际 %#v", st)
	}
	if st.Reason != "docker daemon 不可用" {
		t.Fatalf("reason 不符：%q", st.Reason)
	}
}

func TestProbeContainerDaemonUp(t *testing.T) {
	origLook, origRun := lookPath, runCommand
	defer func() { lookPath, runCommand = origLook, origRun }()
	lookPath = func(string) (string, error) { return "/usr/local/bin/docker", nil }
	runCommand = func(context.Context, string, ...string) ([]byte, error) {
		return []byte("27.0.3\n"), nil
	}

	st := Probe("container")
	if !st.Available {
		t.Fatalf("daemon 可用时应可用，实际 %#v", st)
	}
	if st.Reason != "docker daemon 27.0.3" {
		t.Fatalf("reason 不符：%q", st.Reason)
	}
}

// TestProbeRemoteBareUsesSSHCLI 校验 bare "remote"（无端点）按新设计只检查
// ssh CLI 可用性作为可达性提示：有 ssh 即可用，缺 ssh 才不可用。真实远端连通性
// 由执行器在确认执行时按 profile 的 remote 段实测，不在只读探测里提前猜。
func TestProbeRemoteBareUsesSSHCLI(t *testing.T) {
	orig := lookPath
	defer func() { lookPath = orig }()

	// 有 ssh CLI → 可用
	lookPath = func(string) (string, error) { return "/usr/bin/ssh", nil }
	st := Probe("remote")
	if !st.Available {
		t.Fatalf("有 ssh CLI 时 bare remote 应可用，实际 %#v", st)
	}
	if st.Reason != "ssh CLI 可用" {
		t.Fatalf("reason 不符：%q", st.Reason)
	}

	// 缺 ssh CLI → 不可用
	lookPath = func(string) (string, error) { return "", errors.New("not found") }
	st = Probe("remote")
	if st.Available {
		t.Fatalf("缺 ssh CLI 时 bare remote 不应可用，实际 %#v", st)
	}
	if st.Reason == "" {
		t.Fatal("不可用必须带可读 reason")
	}
}

func TestProbeRemoteUnreachable(t *testing.T) {
	orig := dialTimeout
	defer func() { dialTimeout = orig }()
	dialTimeout = func(string, string, time.Duration) (net.Conn, error) {
		return nil, errors.New("connection refused")
	}

	st := Probe("remote:tcp://127.0.0.1:1")
	if st.Available {
		t.Fatalf("不可达不应可用，实际 %#v", st)
	}
	if st.Reason != "端点不可达" {
		t.Fatalf("reason 不符：%q", st.Reason)
	}
}

func TestRemoteEndpoint(t *testing.T) {
	cases := []struct{ in, want string }{
		{"remote:tcp://10.0.0.1:22", "10.0.0.1:22"},
		{"remote:10.0.0.1:22", "10.0.0.1:22"},
		{"remote:", ""},
		{"local", ""},
	}
	for _, c := range cases {
		if got := remoteEndpoint(c.in); got != c.want {
			t.Errorf("remoteEndpoint(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestProbeAllPreservesOrder(t *testing.T) {
	orig := lookPath
	defer func() { lookPath = orig }()
	lookPath = func(string) (string, error) { return "", errors.New("not found") }

	got := ProbeAll([]string{"local", "container", "remote:"})
	if len(got) != 3 {
		t.Fatalf("长度不符：%d", len(got))
	}
	for i, want := range []string{"local", "container", "remote:"} {
		if got[i].Name != want {
			t.Fatalf("顺序错位：index %d 期望 %q 实际 %q", i, want, got[i].Name)
		}
	}
	if !got[0].Available {
		t.Fatal("local 应可用")
	}
	if got[1].Available || got[2].Available {
		t.Fatal("container（无 CLI）/ remote（无端点）不应可用")
	}
}
