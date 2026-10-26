// envprobe 只读探测执行环境此刻的可达性，**绝不驱动执行**。
//
// ADR 0019 Follow-up ② 的前置契约把两件事刻意分开：
//   - 授权（environment 是否属于该仓库的白名单）由 api 层强制，非法即 400 fail-closed；
//   - 可达性（此刻能不能连上）由本包只读探测，仅作展示/提示，**不阻断 run 记账**。
//
// 分离的理由：证据包（internal/evidence）是记账侧（durable owner），职责是
// 「记下发生了什么」而不是「决定能不能发生」。环境暂时不可达不应让 run 无法记账，
// 否则会把执行可用性耦合进证据链，破坏 fail-closed 的边界。
//
// 零依赖：仅标准库（os/exec、net），不引入 docker SDK / container runtime SDK，
// 以通过 buildguard 的零依赖守卫（go.mod ⊆ allowlist，无 cgo）。
package envprobe

import (
	"context"
	"net"
	"os/exec"
	"strings"
	"sync"
	"time"
)

// 环境种类（由环境名按约定归一化得到，无需扩展 config schema）。
const (
	KindLocal     = "local"
	KindContainer = "container"
	KindRemote    = "remote"
	KindUnknown   = "unknown"
)

// ProbeTimeout 是单个环境探测的上限，避免拖慢 /api/context。
const ProbeTimeout = 2 * time.Second

// Status 是单个环境的探测结果（只读快照，可安全序列化给前端）。
type Status struct {
	Name      string `json:"name"`
	Kind      string `json:"kind"`
	Available bool   `json:"available"`
	Reason    string `json:"reason"`
}

// Kind 把环境名归一化成种类。
// 约定：local / container（或 docker）/ remote[:endpoint]；其余归为 unknown。
// 用名字编码种类，避免为「环境种类」再加一层 config schema。
func Kind(name string) string {
	n := strings.ToLower(strings.TrimSpace(name))
	switch {
	case n == "":
		return KindUnknown
	case n == KindLocal:
		return KindLocal
	case n == "container", n == "docker",
		strings.HasPrefix(n, "container:"), strings.HasPrefix(n, "docker:"):
		return KindContainer
	case n == KindRemote, strings.HasPrefix(n, "remote:"):
		return KindRemote
	default:
		return KindUnknown
	}
}

// 包级依赖抽出来便于测试注入（与项目「宿主地址抽包级 var 便于 httptest」同风格）。
var (
	lookPath    = exec.LookPath
	runCommand  = func(ctx context.Context, name string, args ...string) ([]byte, error) {
		return exec.CommandContext(ctx, name, args...).CombinedOutput()
	}
	dialTimeout = net.DialTimeout
)

// Probe 探测单个环境。任何失败都封闭为 Available=false + 可读 reason，绝不 panic。
func Probe(name string) Status {
	st := Status{Name: name, Kind: Kind(name)}
	switch st.Kind {
	case KindLocal:
		st.Available = true
		st.Reason = "本地工作区，无需外部依赖"
	case KindContainer:
		p, err := lookPath("docker")
		if err != nil || p == "" {
			st.Reason = "未找到 docker CLI"
			return st
		}
		ctx, cancel := context.WithTimeout(context.Background(), ProbeTimeout)
		defer cancel()
		out, err := runCommand(ctx, p, "info", "--format", "{{.ServerVersion}}")
		if err != nil {
			st.Reason = "docker daemon 不可用"
			return st
		}
		v := strings.TrimSpace(string(out))
		if v == "" {
			st.Reason = "docker daemon 无版本信息"
			return st
		}
		st.Available = true
		st.Reason = "docker daemon " + v
	case KindRemote:
		ep := remoteEndpoint(name)
		if ep == "" {
			st.Reason = "缺少远端端点（期望 remote:tcp://host:port 或 remote:host:port）"
			return st
		}
		c, err := dialTimeout("tcp", ep, ProbeTimeout)
		if err != nil {
			st.Reason = "端点不可达"
			return st
		}
		_ = c.Close()
		st.Available = true
		st.Reason = "端点可达"
	default:
		st.Reason = "未知环境种类（支持 local / container / remote:<endpoint>）"
	}
	return st
}

// ProbeAll 并发探测多个环境，返回顺序与输入一致。
func ProbeAll(names []string) []Status {
	out := make([]Status, len(names))
	var wg sync.WaitGroup
	for i, n := range names {
		wg.Add(1)
		go func(i int, n string) {
			defer wg.Done()
			out[i] = Probe(n)
		}(i, n)
	}
	wg.Wait()
	return out
}

// remoteEndpoint 从 remote[:endpoint] 里取出 host:port（容忍 tcp:// 前缀）。
func remoteEndpoint(name string) string {
	n := strings.TrimSpace(name)
	i := strings.Index(n, ":")
	if i < 0 {
		return ""
	}
	ep := strings.TrimSpace(n[i+1:])
	ep = strings.TrimPrefix(ep, "tcp://")
	ep = strings.TrimPrefix(ep, "//")
	return ep
}
