#!/usr/bin/env python3
"""验证 roadmap 中「completed」节点不存在「状态先于代码」的 desync。

判定规则（见 AGENTS.md §7「路线图节点状态不早于实现代码」）：
  对某含 F-number 的 completed 节点，其 status 首次翻成 completed 的提交为 F_commit。
  节点 id 是唯一键（F-number 因复用不具唯一性）；分类：
    - 节点 id 命中的代码提交是 F_commit 的【后代】→ 真 desync（代码晚于状态翻转）
    - 节点 id 命中的代码提交是 F_commit 的【祖先】，或 F_commit 自身即触碰代码目录
      （代码与状态同提交 / 打包提交），或 F-number 命中祖先代码 → 同步 OK
    - 以上皆无                                → UNVERIFIED（多为打包提交未打标签，需人工确认；不计入失败）
  另支持 --allow <node_id...> 把已知历史 desync（如已记入治理 roadmap 的 F6/F12）排除出失败集。

退出码：0 = 无真 desync（UNVERIFIED 仅告警）；1 = 存在真 desync（供 closeout / hook 阻断）。
依赖 git（仅读历史，不写）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True)
    return out.stdout


def load_roadmap(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def f_numbers(label: str) -> list[str]:
    return re.findall(r"F\d+", label or "")


def word_boundary(token: str) -> re.Pattern[str]:
    return re.compile(r"(?<![0-9-])" + re.escape(token) + r"(?![0-9-])")


def first_completed_commit(roadmap_path: str, node_id: str) -> str | None:
    """从旧到新遍历改动过 roadmap 的提交，返回节点首次变 completed 的 commit hash。"""
    log = git("log", "--reverse", "--format=%H", "--", roadmap_path).splitlines()
    for commit in log:
        commit = commit.strip()
        if not commit:
            continue
        raw = git("show", f"{commit}:{roadmap_path}")
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        node = data.get("nodes", {}).get(node_id)
        if node and node.get("status") == "completed":
            return commit
    return None


def code_commits(src_dir: str) -> list[tuple[str, str]]:
    """返回 (hash, subject) 列表：所有触碰 src_dir 的提交（当前可达历史）。"""
    out = git("log", "--format=%H%x1f%s", "--", src_dir).splitlines()
    result = []
    for line in out:
        if not line.strip():
            continue
        h, _, s = line.partition("\x1f")
        result.append((h.strip(), s.strip()))
    return result


def is_ancestor(ancestor: str, descendant: str) -> bool:
    rc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
    ).returncode
    return rc == 0


def commit_touches_code(commit: str, code_dir: str) -> bool:
    files = git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines()
    return any(f.startswith(code_dir + "/") or f == code_dir for f in files)


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify roadmap completed nodes are code-backed.")
    ap.add_argument("roadmap", help="path to roadmap JSON")
    ap.add_argument("--code-dir", default="src", help="code directory to inspect (default: src)")
    ap.add_argument("--allow", nargs="*", default=[], help="node ids to exclude from failure")
    args = ap.parse_args()

    roadmap_path = args.roadmap
    data = load_roadmap(roadmap_path)
    nodes = data.get("nodes", {})
    code = code_commits(args.code_dir)

    desynced: list[tuple[str, str, str]] = []
    unverified: list[tuple[str, str]] = []
    synced = 0
    checked = 0

    for node_id, node in nodes.items():
        if node_id == "1":
            continue
        if node.get("status") != "completed":
            continue
        fs = f_numbers(node.get("label", ""))
        if not fs:
            continue
        checked += 1

        f_commit = first_completed_commit(roadmap_path, node_id)
        if not f_commit:
            unverified.append((node_id, node.get("label", "")))
            continue

        node_re = word_boundary(node_id)
        f_res = [word_boundary(f) for f in fs]
        flip_self_code = commit_touches_code(f_commit, args.code_dir)
        node_before = False   # 节点 id 命中且为 flip 的祖先（同步）
        node_after = False    # 节点 id 命中且为 flip 的后代（真 desync）
        f_before = False      # F-number 命中且为 flip 的祖先（仅辅助确认同步）
        after_hashes = []
        for h, subject in code:
            has_node = node_re.search(subject)
            has_f = any(r.search(subject) for r in f_res)
            if not (has_node or has_f):
                continue
            if has_node:
                if is_ancestor(h, f_commit):
                    node_before = True
                elif is_ancestor(f_commit, h):
                    node_after = True
                    after_hashes.append(h)
            if has_f and is_ancestor(h, f_commit):
                f_before = True

        if node_after and node_id not in args.allow:
            latest = ""
            for h in after_hashes:
                if not latest or is_ancestor(latest, h):
                    latest = h
            desynced.append(
                (node_id, node.get("label", ""),
                 f"节点 id 命中的代码提交 {latest[:8]} 晚于 status 翻转 {f_commit[:8]}")
            )
        elif flip_self_code or node_before or f_before:
            synced += 1
            why = "状态翻转提交自身含代码" if flip_self_code else ("节点 id 命中祖先代码" if node_before else "F-number 命中祖先代码")
            print(f"  ✓ {node_id} {node.get('label', '')[:40]} — {why}")
        else:
            unverified.append((node_id, node.get("label", "")))

    print(f"校验 {checked} 个含 F-number 的 completed 节点（roadmap: {roadmap_path}）")
    print(f"  同步 OK: {synced}  真 desync: {len(desynced)}  待人工确认(UNVERIFIED): {len(unverified)}")
    for nid, label in unverified:
        print(f"  ? {nid} {label} — UNVERIFIED：无命中节点 token 的代码提交（疑似打包提交未打标签，需人工确认）")

    if not desynced:
        print("✓ 无真 desync（状态翻转时对应实现代码已提交）。")
        return 0

    print(f"✗ 发现 {len(desynced)} 处真 desync（代码晚于状态翻转）：")
    for nid, label, reason in desynced:
        print(f"  - {nid} {label}\n      {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
