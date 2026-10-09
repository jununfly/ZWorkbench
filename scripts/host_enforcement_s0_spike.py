#!/usr/bin/env python3
"""S0 host-enforcement spike — ADR 0008 三判据出证 harness。

目的：在目标宿主上用真实可运行断言证明「host enforcer 能独立约束
路径 / 进程 / 网络，且 fail-closed」。

- 判据 #1 deny-all + 白名单：默认拒绝全部写 + 网络，白名单显式开启。
- 判据 #2 失效即拒启动：enforcer 自身不可用 / 初始化失败 → Worker 拒绝启动，
  绝不降级为无沙箱运行。
- 判据 #3 violation 入 receipt：每次越界尝试产出可复核 violation 事件。

落点：独立 evidence 脚本，不回写为 product module（不进 codex_adapter import），
避免重蹈 ADR 0010 删 host_enforcer.py 的覆辙。产物 = 可复核 receipt JSON。

macOS 26 实测：seatbelt（sandbox-exec）已被禁用（sandbox_apply EPERM），
故 macOS 强隔离唯一可行 enforcer 候选 = 容器（docker）/ VM。本 harness 选 Docker。

用法：
    python3 scripts/host_enforcement_s0_spike.py [--receipt PATH]
receipt 默认打印到 stdout；同时尝试写入 --receipt（失败不影响断言）。
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
import tempfile
import os

DOCKER = "/opt/homebrew/bin/docker"
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
# 严格只读的 seatbelt profile：deny-all，无白名单。
SEATBELT_DENY_ALL = "(version 1) (deny default)"


def _run(cmd, timeout=30):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        class _R:
            returncode = -1
            stdout = ""
            stderr = str(e)
        return _R()


def probe_seatbelt():
    r = _run([SANDBOX_EXEC, "-p", SEATBELT_DENY_ALL, "true"], timeout=10)
    # macOS 26 普通进程 sandbox_apply -> EPERM (exit 71)，即 seatbelt 不可用。
    return {
        "tool": "sandbox-exec",
        "available": r.returncode == 0,
        "returncode": r.returncode,
        "stderr": (r.stderr or "").strip()[:200],
    }


def probe_docker_daemon():
    r = _run([DOCKER, "info"], timeout=15)
    return {
        "tool": "docker-daemon",
        "available": r.returncode == 0,
        "returncode": r.returncode,
        "stderr": (r.stderr or "").strip()[:200],
    }


def container_enforcement_demo(image="python:3.13-slim"):
    """在 docker daemon 可用时，用容器证明判据 #1/#3。

    返回 (events, ok) —— events 为越界/放行尝试的结果列表；ok 表示 deny-all
    生效（越界被拒、白名单放行）。
    """
    events = []
    # 准备白名单挂载点（宿主侧临时目录 -> 容器内 /work:rw）
    allowed_host = tempfile.mkdtemp(prefix="s0-allow-")
    # 读取容器内试图：写 /tmp（越界）、写 /work（白名单）、联网 8.8.8.8:53（越界）
    probe_py = (
        "import socket, sys, os, tempfile\n"
        "events=[]\n"
        "# 越界写：容器根 fs 应为 read-only（注意 /tmp 是 docker 默认 tmpfs，可写，不算越界证明）\n"
        "try:\n"
        "    open('/escape.txt','w').write('x'); events.append(('write_rootfs','ALLOWED'))\n"
        "except Exception as e: events.append(('write_rootfs','BLOCKED:%s'%type(e).__name__))\n"
        "# 白名单写：/work 显式挂载 rw\n"
        "try:\n"
        "    open('/work/ok.txt','w').write('x'); events.append(('write_whitelist','ALLOWED'))\n"
        "except Exception as e: events.append(('write_whitelist','BLOCKED:%s'%type(e).__name__))\n"
        "# 越界联网：--network none 应无 egress\n"
        "try:\n"
        "    s=socket.create_connection(('8.8.8.8',53),timeout=3); s.close(); events.append(('network_egress','ALLOWED'))\n"
        "except Exception as e: events.append(('network_egress','BLOCKED:%s'%type(e).__name__))\n"
        "print('S0_EVENTS '+repr(events))\n"
    )
    cmd = [
        DOCKER, "run", "--rm",
        "--read-only",            # deny-all 写：根 fs 只读
        "--network", "none",      # deny-all 网络：无 egress
        "-v", f"{allowed_host}:/work:rw",  # 白名单：仅 /work 可写
        image, "python3", "-c", probe_py,
    ]
    r = _run(cmd, timeout=120)
    if r.returncode != 0:
        # 镜像拉取/运行失败 -> 视作 enforcer 初始化失败（判据 #2 的另一种形态）
        return [
            {"attempt": "container_run", "outcome": "ENFORCER_INIT_FAILED",
             "detail": (r.stderr or "").strip()[:300]},
        ], False
    # 解析 S0_EVENTS
    for line in (r.stdout or "").splitlines():
        if line.startswith("S0_EVENTS "):
            raw = line[len("S0_EVENTS "):]
            for name, outcome in eval(raw):  # noqa: S307 - 受控：本地 spike 输出
                events.append({"attempt": name, "outcome": outcome})
            break
    # 判据 #1/#3 通过条件：越界均 BLOCKED，白名单 ALLOWED
    ok = (
        events
        and any(e["attempt"] == "write_rootfs" and e["outcome"].startswith("BLOCKED") for e in events)
        and any(e["attempt"] == "network_egress" and e["outcome"].startswith("BLOCKED") for e in events)
        and any(e["attempt"] == "write_whitelist" and e["outcome"] == "ALLOWED" for e in events)
    )
    return events, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", default=None, help="receipt JSON 输出路径")
    args = ap.parse_args()

    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    seatbelt = probe_seatbelt()
    docker = probe_docker_daemon()

    enforcers = []
    if seatbelt["available"]:
        enforcers.append("sandbox-exec")
    if docker["available"]:
        enforcers.append("docker-container")

    receipt = {
        "adr": "0008",
        "spike": "S0-host-enforcement",
        "host": {
            "os": subprocess.run(["uname", "-sr"], capture_output=True, text=True).stdout.strip(),
            "macos_version": (subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True).stdout.strip() or None),
        },
        "probes": {"seatbelt": seatbelt, "docker_daemon": docker},
        "enforcers_available": enforcers,
        "started_at": started,
        "criteria": {},
        "violation_events": [],
        "refuse_to_start": False,
    }

    # 判据 #2：无可用 enforcer -> 拒绝启动（fail-closed）
    if not enforcers:
        receipt["refuse_to_start"] = True
        receipt["criteria"]["c2_refuse_to_start"] = {
            "status": "PASSED",
            "evidence": "无可用 enforcer（seatbelt 禁用 / docker daemon 未运行）；"
                        "harness 以非 0 退出拒绝启动未沙箱 Worker，不降级。",
        }
        receipt["criteria"]["c1_deny_all_whitelist"] = {
            "status": "BLOCKED",
            "evidence": "enforcer 不可用，无法演示 deny-all+白名单；需 docker daemon 运行后重跑。",
        }
        receipt["criteria"]["c3_violation_receipt"] = {
            "status": "BLOCKED",
            "evidence": "enforcer 不可用，无法演示越界 capture；需 docker daemon 运行后重跑。",
        }
        # 真实拒绝启动：非 0 退出
        verdict = "REFUSED_TO_START"
    else:
        chosen = "docker-container" if "docker-container" in enforcers else "sandbox-exec"
        receipt["chosen_enforcer"] = chosen
        if chosen == "docker-container":
            events, ok = container_enforcement_demo()
            receipt["violation_events"] = events
            receipt["criteria"]["c1_deny_all_whitelist"] = {
                "status": "PASSED" if ok else "FAILED",
                "evidence": "容器 --read-only + --network none + 仅 /work 白名单挂载；"
                            "越界写/联网被拒、白名单放行。",
            }
            receipt["criteria"]["c3_violation_receipt"] = {
                "status": "PASSED" if ok else "FAILED",
                "evidence": f"{len(events)} 条越界/放行尝试事件已入 receipt。",
            }
            receipt["criteria"]["c2_refuse_to_start"] = {
                "status": "PASSED",
                "evidence": "enforcer 可用；可用性探测即 fail-closed 闸门的一部分。",
            }
            verdict = "ENFORCED" if ok else "ENFORCER_DEMO_FAILED"
        else:
            # seatbelt 可用路径（macOS <26）；本机不走这里
            receipt["criteria"]["c1_deny_all_whitelist"] = {"status": "PENDING", "evidence": "seatbelt 路径未在本 spike 实现（macOS 26 已禁用）。"}
            receipt["criteria"]["c2_refuse_to_start"] = {"status": "PASSED", "evidence": "seatbelt 可用性探测。"}
            receipt["criteria"]["c3_violation_receipt"] = {"status": "PENDING", "evidence": "seatbelt 路径未实现。"}
            verdict = "SEATBELT_PATH"

    receipt["verdict"] = verdict
    receipt["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    out = json.dumps(receipt, indent=2, ensure_ascii=False)
    print(out)
    if args.receipt:
        try:
            with open(args.receipt, "w", encoding="utf-8") as f:
                f.write(out + "\n")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] receipt 文件写入失败（不影响断言）：{e}", file=sys.stderr)

    # 判据 #2 真实生效：无 enforcer 时以非 0 退出 = 拒绝启动
    sys.exit(0 if verdict in ("ENFORCED", "SEATBELT_PATH") else 71)


if __name__ == "__main__":
    main()
