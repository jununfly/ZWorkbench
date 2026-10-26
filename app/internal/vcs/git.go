// Package vcs 提供版本控制系统（当前仅 git）的轻量只读探测。
// 设计目标：fail-closed——任何失败（无 git 二进制 / 非仓库 / 超时 / 被信号打断）
// 都返回 "unknown"，绝不 panic、绝不向上抛错，便于上层 API 永不 500。
package vcs

import (
	"context"
	"os/exec"
	"strings"
	"time"
)

// UnknownBranch 是探测失败时的统一回退值（ADR 0019）。
const UnknownBranch = "unknown"

// CurrentBranch 返回 dir 所在 git 仓库的当前分支名（短名，如 "main"）。
// dir 为空或非 git 仓库或 git 不可用时返回 UnknownBranch。
func CurrentBranch(dir string) string {
	return CurrentBranchCtx(context.Background(), dir)
}

// CurrentBranchCtx 是 CurrentBranch 的带超时上下文版本。
func CurrentBranchCtx(ctx context.Context, dir string) string {
	if dir == "" {
		return UnknownBranch
	}
	// 限制探测耗时，避免挂死在异常文件系统上。
	cctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	// 优先用 symbolic-ref 取当前分支名：对「无提交的空分支」也能正确返回分支名
	// （rev-parse --abbrev-ref HEAD 在 unborn 分支上返回 "HEAD"，会被误判）。
	cmd := exec.CommandContext(cctx, "git", "-C", dir, "symbolic-ref", "--short", "-q", "HEAD")
	out, err := cmd.Output()
	if err != nil {
		// detached HEAD 或 git 不可用：回退 unknown。
		return UnknownBranch
	}
	branch := strings.TrimSpace(string(out))
	if branch == "" {
		return UnknownBranch
	}
	return branch
}

// Toplevel 返回 dir 所在 git 仓库的顶层目录绝对路径（git rev-parse --show-toplevel）。
// 非 git 仓库或 git 不可用时返回 ("", false)。用于把「当前仓库」自动登记为默认被管理仓库（ADR 0019）。
func Toplevel(dir string) (string, bool) {
	if dir == "" {
		dir = "."
	}
	cctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	cmd := exec.CommandContext(cctx, "git", "-C", dir, "rev-parse", "--show-toplevel")
	out, err := cmd.Output()
	if err != nil {
		return "", false
	}
	p := strings.TrimSpace(string(out))
	if p == "" {
		return "", false
	}
	return p, true
}
